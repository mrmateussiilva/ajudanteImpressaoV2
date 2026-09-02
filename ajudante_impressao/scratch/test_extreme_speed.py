import time
import numpy as np
import cv2
import numba
from PIL import Image, ImageDraw
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ajudante_impressao.algorithms.packing import (
    _alpha_mask,
    _rotate_image,
    _build_stamp_kernel,
    _stamp_reserved,
    _collides_fast,
    _ensure_height,
    _find_row_transitions_fast,
    MaskVariant,
    PackedPiece,
    _dedupe_candidates,
    _score_candidate,
)
from ajudante_impressao.scratch.test_optimized_packing import _fast_score_contact

@numba.njit(fastmath=True, nogil=True)
def _collides_coarse(
    scaled_occ: np.ndarray,
    scaled_mask: np.ndarray,
    x: int, y: int,
    max_y: int,
) -> bool:
    if y >= max_y:
        return False
    occ_h, occ_w = scaled_occ.shape
    h, w = scaled_mask.shape
    if y < 0 or x < 0 or y + h > occ_h or x + w > occ_w:
        return True
    check_h = min(h, max_y - y)
    if check_h <= 0:
        return False
    for r in range(check_h):
        for c in range(w):
            if scaled_mask[r, c] != 0 and scaled_occ[y + r, x + c] != 0:
                return True
    return False

# Structure for precomputed mask variant
class FastVariant:
    __slots__ = ("image", "mask", "scaled_mask", "scaled_mask_f", "mask_sum", "area", "angle", "w", "h", "sw", "sh")
    def __init__(self, image, mask, angle, scale=8):
        self.image = image
        self.mask = mask
        self.angle = angle
        self.h, self.w = mask.shape
        self.area = int(mask.sum())
        self.sw = max(1, self.w // scale)
        self.sh = max(1, self.h // scale)
        small = cv2.resize(mask, (self.sw, self.sh), interpolation=cv2.INTER_AREA)
        self.scaled_mask = (small > 0).astype(np.uint8)
        self.scaled_mask_f = self.scaled_mask.astype(np.float32)
        self.mask_sum = float(self.scaled_mask_f.sum())

def test_speed():
    # Warmup Numba
    dummy = np.zeros((10, 10), dtype=np.uint8)
    _collides_coarse(dummy, dummy, 0, 0, 10)
    _fast_score_contact(dummy, 0, 0, 5, 5, 1, 1, 10)

    # 4 imagens 2000x2800
    images = []
    for i in range(4):
        img = Image.new("RGBA", (2000, 2800), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pts = [(100, 100), (1900, 200), (1800, 2700), (200, 2600), (1000, 1400)]
        draw.polygon(pts, fill=((i*60)%255, 100, 200, 255))
        images.append(img)

    max_width = 4921
    spacing = 12
    margin = 20
    scale = 8

    print("Pré-computando variantes...")
    t0 = time.time()
    all_variants = []
    for img in images:
        vars_for_img = []
        for angle in [0, 90, 270]:
            rot_img = img if angle == 0 else _rotate_image(img, angle)
            from ajudante_impressao.algorithms.image_ops import trim_empty_borders
            rot_img = trim_empty_borders(rot_img)
            mask = _alpha_mask(rot_img)
            vars_for_img.append(FastVariant(rot_img, mask, angle, scale=scale))
        all_variants.append(vars_for_img)
    print(f"Variantes preparadas em {time.time() - t0:.3f}s")

    # Vamos testar o layout de 4 peças
    t0 = time.time()
    # Canvas
    occ = np.zeros((12000, max_width), dtype=np.uint8)
    scaled_occ = np.zeros((12000 // scale, max_width // scale), dtype=np.uint8)
    max_y_used = margin
    stamp_kernel = _build_stamp_kernel(spacing)

    placed_pieces = []
    for piece_variants in all_variants:
        best_choice = None
        for variant in piece_variants:
            mask = variant.mask
            s_mask = variant.scaled_mask
            w, h = variant.w, variant.h
            sw, sh = variant.sw, variant.sh

            search_h = max_y_used + spacing + h + 8
            s_search_h = search_h // scale

            # 1. Candidatos de fronteira
            candidates = [(margin, margin)]
            for p in placed_pieces:
                candidates.append((p[1] + p[3] + spacing, p[2]))
                candidates.append((p[1], p[2] + p[4] + spacing))
                candidates.append((margin, p[2] + p[4] + spacing))
                candidates.append((max_width - margin - w, p[2]))
                candidates.append((max_width - margin - w, p[2] + p[4] + spacing))

            # 2. Match template no grid reduzido se houver espaço
            if scaled_occ[:s_search_h, :].any() and variant.mask_sum >= 1.0:
                s_occ_slice = scaled_occ[:s_search_h, :].astype(np.float32)
                free_c = 1.0 - (s_occ_slice > 0).astype(np.float32)
                if free_c.shape[0] > sh and free_c.shape[1] > sw:
                    res = cv2.matchTemplate(free_c, variant.scaled_mask_f, cv2.TM_CCORR)
                    res_norm = res / variant.mask_sum
                    for thresh in (0.999, 0.95, 0.85):
                        ys_c, xs_c = np.where(res_norm >= thresh)
                        if len(ys_c) > 0:
                            for cy, cx in zip(ys_c[:32], xs_c[:32]):
                                candidates.append((int(cx * scale), int(cy * scale)))
                            break

            # 3. Avaliar candidatos com coarse check + fine check
            for cx, cy in candidates:
                if cx < margin or cy < margin or cx + w > max_width - margin or cy + h > search_h:
                    continue
                # Coarse check
                if _collides_coarse(scaled_occ, s_mask, cx // scale, cy // scale, s_search_h):
                    continue
                # Fine check
                if _collides_fast(occ, mask, cx, cy, search_h):
                    continue

                score = _score_candidate(mask, cx, cy, max_width, margin, max_y_used, variant.area)
                contact, pocket_bonus = _fast_score_contact(occ, cx, cy, w, h, spacing, margin, max_width)
                angle_penalty = 0 if variant.angle in (0, 90, 270) else 1
                final_score = (score[0], score[1], angle_penalty, -pocket_bonus, -contact, score[2], score[3], score[4], score[5])

                if best_choice is None or final_score < best_choice["score"]:
                    best_choice = {
                        "variant": variant,
                        "x": cx, "y": cy,
                        "score": final_score,
                    }

        if best_choice is None:
            v = piece_variants[0]
            best_choice = {"variant": v, "x": margin, "y": max_y_used + spacing}

        chosen_v = best_choice["variant"]
        bx, by = best_choice["x"], best_choice["y"]
        placed_pieces.append((chosen_v, bx, by, chosen_v.w, chosen_v.h))

        # Stamp em ambos
        _stamp_reserved(occ, chosen_v.mask, bx, by, spacing, margin, max_width, stamp_kernel)
        _stamp_reserved(
            scaled_occ, chosen_v.scaled_mask,
            bx // scale, by // scale,
            max(0, spacing // scale), margin // scale, max_width // scale,
            None
        )
        max_y_used = max(max_y_used, by + chosen_v.h)

    t1 = time.time()
    print(f"4 imagens empacotadas em {t1-t0:.4f}s! Altura total: {max_y_used + margin}px")

if __name__ == "__main__":
    test_speed()

from __future__ import annotations

from typing import List

import cv2
import numpy as np
from PIL import Image

try:
    import numba
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

from .image_ops import fit_width, resize_to_height, trim_empty_borders


def pack_images_gallery(images: List[Image.Image], max_width: int, spacing: int, margin: int, row_height: int, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared: List[Image.Image] = []

    for img in images:
        img = trim_empty_borders(img)
        if allow_rotate:
            # Se for mais largo que o rolo mas couber em pé, rotaciona
            if img.width > usable_width and img.height <= usable_width:
                img = img.rotate(90, expand=True)
            # Se for muito alto e couber deitado, rotaciona para economizar altura
            elif img.height > img.width * 1.5 and img.height <= usable_width:
                img = img.rotate(90, expand=True)
        prepared.append(img)

    prepared.sort(key=lambda im: (im.width * im.height), reverse=True)
    rows: List[List[Image.Image]] = []
    current_row: List[Image.Image] = []
    current_width = 0

    for img in prepared:
        w = img.width
        extra = w if not current_row else w + spacing
        if current_row and current_width + extra > usable_width:
            rows.append(current_row)
            current_row = [img]
            current_width = img.width
        else:
            current_row.append(img)
            current_width += extra

    if current_row:
        rows.append(current_row)

    placed = []
    y = margin
    for row_imgs in rows:
        total_w = sum(im.width for im in row_imgs)
        gaps = spacing * (len(row_imgs) - 1)
        row_total = total_w + gaps
        scaled_row = row_imgs  # Sem redimensionamento automático

        row_h = max(im.height for im in scaled_row)
        total_w = sum(im.width for im in scaled_row)
        gaps = spacing * (len(scaled_row) - 1)
        row_total = total_w + gaps
        x = margin
        if row_total < usable_width:
            x += (usable_width - row_total) // 2

        for im in scaled_row:
            placed.append((im, x, y))
            x += im.width + spacing
        y += row_h + spacing

    final_height = y - spacing + margin if placed else margin * 2
    return placed, max_width, final_height


def pack_images_fast(images: List[Image.Image], max_width: int, spacing: int, margin: int, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared = []

    for img in images:
        img = trim_empty_borders(img)
        if allow_rotate:
            # Prioridade 1: Rotacionar se for mais largo que o rolo
            if img.width > usable_width and img.height <= usable_width:
                img = img.rotate(90, expand=True)
            # Prioridade 2: Rotacionar se for muito alto para economizar altura
            elif img.height > img.width and img.height <= usable_width:
                rotated = img.rotate(90, expand=True)
                if rotated.width <= usable_width:
                    img = rotated
        prepared.append(img)

    prepared.sort(key=lambda im: (im.height, im.width), reverse=True)
    rows = []
    placed = []

    for img in prepared:
        w, h = img.size
        best_row_index = None
        best_waste = None

        for i, row in enumerate(rows):
            available = max_width - margin - row["x"]
            if w <= available:
                waste = available - w
                if best_waste is None or waste < best_waste:
                    best_waste = waste
                    best_row_index = i

        if best_row_index is not None:
            row = rows[best_row_index]
            x = row["x"]
            y = row["y"]
            placed.append((img, x, y))
            row["x"] += w + spacing
            row["h"] = max(row["h"], h)
        else:
            new_y = rows[-1]["y"] + rows[-1]["h"] + spacing if rows else margin
            rows.append({"x": margin + w + spacing, "y": new_y, "h": h})
            placed.append((img, margin, new_y))

    final_height = margin
    for row in rows:
        final_height = max(final_height, row["y"] + row["h"])
    final_height += margin
    return placed, max_width, final_height


def pack_images_tight(images: List[Image.Image], max_width: int, spacing: int, margin: int, step: int = 8, allow_rotate: bool = False, performance_mode: str = "balanced"):
    usable_width = max_width - 2 * margin
    prepared = []

    for img in images:
        variants = [img]
        if allow_rotate:
            rot = img.rotate(90, expand=True)
            if rot.width <= usable_width:
                variants.append(rot)
        prepared.append({"variants": variants})

    prepared.sort(key=lambda item: (item["variants"][0].width * item["variants"][0].height, item["variants"][0].height, item["variants"][0].width), reverse=True)

    profile = np.full(max_width, margin, dtype=np.int32)
    placed = []
    max_y_used = margin

    step = max(1, step)
    fine_step = 1 if performance_mode in ("quality", "balanced") else 2
    lookahead = 3 if performance_mode in ("quality", "balanced") else 1

    remaining = prepared.copy()

    while remaining:
        best_overall_choice = None
        best_piece_index = -1
        current_lookahead = min(len(remaining), lookahead)

        for i in range(current_lookahead):
            piece = remaining[i]
            best_choice = None

            for variant in piece["variants"]:
                w, h = variant.size
                x_start = margin
                x_end = max_width - margin - w
                if x_end < x_start:
                    x_end = x_start

                best_x = margin
                best_y = None
                best_bottom = None

                for x in range(x_start, x_end + 1, step):
                    y = int(profile[x:x + w].max())
                    bottom = y + h
                    if best_bottom is None or bottom < best_bottom or (bottom == best_bottom and y < best_y):
                        best_x = x
                        best_y = y
                        best_bottom = bottom

                if step > fine_step:
                    fine_start = max(x_start, best_x - step)
                    fine_end = min(x_end, best_x + step)
                    for x in range(fine_start, fine_end + 1, fine_step):
                        y = int(profile[x:x + w].max())
                        bottom = y + h
                        if bottom < best_bottom or (bottom == best_bottom and y < best_y):
                            best_x = x
                            best_y = y
                            best_bottom = bottom

                if best_y is None:
                    best_x = margin
                    best_y = max_y_used + spacing
                    best_bottom = best_y + h

                choice_score = (best_bottom, best_y, -(w * h))
                if best_choice is None or choice_score < best_choice["score"]:
                    best_choice = {"variant": variant, "x": best_x, "y": best_y, "bottom": best_bottom, "score": choice_score}

            if best_overall_choice is None or best_choice["score"] < best_overall_choice["score"]:
                best_overall_choice = best_choice
                best_piece_index = i

        remaining.pop(best_piece_index)
        variant = best_overall_choice["variant"]
        best_x = best_overall_choice["x"]
        best_y = best_overall_choice["y"]
        w, h = variant.size

        cx, cy = best_x, best_y
        for _ in range(3):
            moved = False
            while cx - 1 >= margin:
                y_left = int(profile[cx - 1 : cx - 1 + w].max())
                if y_left <= cy:
                    cx -= 1
                    moved = True
                else:
                    break
            while cy - 1 >= margin and cy - 1 >= int(profile[cx : cx + w].max()):
                cy -= 1
                moved = True
            if not moved:
                break

        best_x, best_y = cx, cy
        best_bottom = best_y + h

        placed.append((variant, best_x, best_y))
        max_y_used = max(max_y_used, best_bottom)

        reserve_start = max(margin, best_x - spacing)
        reserve_end = min(max_width - margin, best_x + w + spacing)
        profile[reserve_start:reserve_end] = np.maximum(profile[reserve_start:reserve_end], best_bottom + spacing)

    final_height = max_y_used + margin
    return placed, max_width, final_height


def _alpha_mask(img: Image.Image) -> np.ndarray:
    mask = np.array(img.getchannel("A"), dtype=np.uint8)
    return (mask > 0).astype(np.uint8)


def _quantize(value: int, step: int, minimum: int) -> int:
    if value <= minimum:
        return minimum
    return minimum + ((value - minimum + step - 1) // step) * step


# ─── OPT 4: rotação via cv2 (3-5x mais rápido que PIL para 90/180/270) ────────
_CV2_ROT_MAP = {
    90:  cv2.ROTATE_90_COUNTERCLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_CLOCKWISE,
}

def _rotate_image(img: Image.Image, angle: int) -> Image.Image:
    """Rotaciona imagem RGBA. Usa cv2 para 90/180/270, PIL para ângulos oblíquos."""
    if angle in _CV2_ROT_MAP:
        arr = np.array(img)
        rotated_arr = cv2.rotate(arr, _CV2_ROT_MAP[angle])
        return Image.fromarray(rotated_arr)
    # Ângulos oblíquos: PIL (mais lento, mas raramente chamado)
    return img.rotate(angle, expand=True)


def _prepare_mask_variants(img: Image.Image, usable_width: int, allow_rotate: bool, performance_mode: str = "balanced") -> list[dict]:
    img = trim_empty_borders(img)
    angle_candidates = [0]
    if allow_rotate:
        if performance_mode == "quality":
            angle_candidates.extend([90, 180, 270, 15, -15, 30, -30, 45, 135, 225, 315, 60, -60])
        elif performance_mode == "balanced":
            angle_candidates.extend([90, 180, 270, 45, 135, 225, 315])
        else:  # fast
            angle_candidates.extend([90, 180, 270])

    # OPT 4: Para imagens muito retangulares (preenchimento > 85%), ângulos oblíquos
    # não oferecem vantagem real — pular para acelerar o processo
    if allow_rotate and performance_mode == "quality":
        base_mask = _alpha_mask(img)
        alpha_density = base_mask.sum() / max(1, img.width * img.height)
        if alpha_density > 0.85:
            # Imagem quase retangular — ângulos oblíquos são inúteis
            angle_candidates = [a for a in angle_candidates if a in (0, 90, 180, 270)]

    variants: list[dict] = []
    seen: set[tuple[int, int, int]] = set()

    for angle in angle_candidates:
        if angle == 0:
            variant = img
        else:
            variant = trim_empty_borders(_rotate_image(img, angle))

        if variant.width > usable_width or variant.width <= 0 or variant.height <= 0:
            continue

        mask = _alpha_mask(variant)
        alpha_area = int(mask.sum())
        signature = (variant.width, variant.height, alpha_area)
        if alpha_area <= 0 or signature in seen:
            continue
        seen.add(signature)
        variants.append({"image": variant, "mask": mask, "area": alpha_area})

    variants.sort(key=lambda item: (item["area"], item["image"].height, item["image"].width), reverse=True)
    return variants


def _ensure_height(occupancy: np.ndarray, min_height: int) -> np.ndarray:
    if min_height <= occupancy.shape[0]:
        return occupancy
    # OPT 6: Crescimento mais agressivo para evitar realocações frequentes
    growth = max(min_height + 2048, occupancy.shape[0] * 2)
    expanded = np.zeros((growth, occupancy.shape[1]), dtype=np.uint8)
    expanded[: occupancy.shape[0], :] = occupancy
    return expanded


# ─── OPT 1: Construção do kernel de stamp (calculado uma vez por spacing) ──────
def _build_stamp_kernel(spacing: int) -> np.ndarray:
    """Kernel circular para dilatação com espaçamento. Cacheado externamente."""
    y_idx, x_idx = np.ogrid[-spacing:spacing + 1, -spacing:spacing + 1]
    return (x_idx ** 2 + y_idx ** 2 <= spacing ** 2).astype(np.uint8)


if HAS_NUMBA:
    # ─── OPT 2 (Numba): Binary search no nudge gravity ────────────────────────
    @numba.njit(nogil=True)
    def _collides_jit(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, max_y_used: int) -> bool:
        if y >= max_y_used:
            return False
        h, w = mask.shape
        for i in range(h):
            if y + i >= max_y_used:
                break
            for j in range(w):
                if mask[i, j] > 0 and occupancy[y + i, x + j] > 0:
                    return True
        return False

    @numba.njit(nogil=True)
    def _nudge_gravity_jit(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, margin: int, max_occ_y: int) -> tuple[int, int]:
        cx, cy = x, y
        for _ in range(4):
            moved = False

            # Binary search vertical (cima)
            lo, hi = margin, cy
            while lo < hi:
                mid = (lo + hi) // 2
                if _collides_jit(occupancy, mask, cx, mid, max_occ_y):
                    lo = mid + 1
                else:
                    hi = mid
            if lo < cy:
                cy = lo
                moved = True

            # Binary search horizontal (esquerda)
            lo, hi = margin, cx
            while lo < hi:
                mid = (lo + hi) // 2
                if _collides_jit(occupancy, mask, mid, cy, max_occ_y):
                    lo = mid + 1
                else:
                    hi = mid
            if lo < cx:
                cx = lo
                moved = True

            # Diagonal (1 passo por vez — difícil de binary-search bidimensional)
            while cy - 1 >= margin and cx - 1 >= margin and not _collides_jit(occupancy, mask, cx - 1, cy - 1, max_occ_y):
                cy -= 1
                cx -= 1
                moved = True

            if not moved:
                break
        return cx, cy

    @numba.njit(nogil=True)
    def _evaluate_batch_jit(occupancy: np.ndarray, mask: np.ndarray, candidates: np.ndarray, max_y_used: int, max_occ_y: int, max_width: int, margin: int):
        num = len(candidates)
        scores = np.full((num, 5), 99999999, dtype=np.int32)
        h_mask = mask.shape[0]
        w_mask = mask.shape[1]

        for i in range(num):
            fx, fy = candidates[i]
            if not _collides_jit(occupancy, mask, fx, fy, max_occ_y):
                bottom = fy + h_mask
                center_dist = abs(fx + w_mask // 2 - max_width // 2)
                space_right = max_width - margin - (fx + w_mask)
                fragmentation_penalty = 1 if (0 < space_right < 50) else 0

                scores[i, 0] = max(bottom, max_y_used)
                scores[i, 1] = fy
                scores[i, 2] = fragmentation_penalty
                scores[i, 3] = bottom
                scores[i, 4] = -center_dist

        best_idx = -1
        best_val = (99999999, 99999999, 99999999, 99999999, 99999999)
        for i in range(num):
            s = (scores[i, 0], scores[i, 1], scores[i, 2], scores[i, 3], scores[i, 4])
            if s < best_val:
                best_val = s
                best_idx = i
        return best_idx, best_val

else:
    _collides_jit = None
    _nudge_gravity_jit = None
    _evaluate_batch_jit = None


# ─── OPT 7: _collides sem re-check de HAS_NUMBA a cada chamada ────────────────
# A função é definida depois do bloco if/else acima, então já sabe se JIT existe.
if HAS_NUMBA and _collides_jit is not None:
    def _collides(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, max_occ_y: int) -> bool:
        h, w = mask.shape
        if y < 0 or x < 0 or y + h > occupancy.shape[0] or x + w > occupancy.shape[1]:
            return True
        if y >= max_occ_y:
            return False
        return _collides_jit(occupancy, mask, x, y, max_occ_y)
else:
    def _collides(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, max_occ_y: int) -> bool:
        if y >= max_occ_y:
            return False
        h, w = mask.shape
        if y < 0 or x < 0 or y + h > occupancy.shape[0] or x + w > occupancy.shape[1]:
            return True
        check_h = min(h, max_occ_y - y)
        if check_h <= 0:
            return False
        # OPT 7: cv2.countNonZero evita alocação de array temporário vs np.any
        region = occupancy[y:y + check_h, x:x + w] & mask[:check_h, :]
        return cv2.countNonZero(region) > 0


def _stamp_reserved(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, spacing: int, margin: int, max_width: int, stamp_kernel: np.ndarray | None = None) -> None:
    # OPT 1: Usa kernel pré-calculado se fornecido
    if spacing > 0:
        if stamp_kernel is None:
            stamp_kernel = _build_stamp_kernel(spacing)
        padded = cv2.copyMakeBorder(mask, spacing, spacing, spacing, spacing, cv2.BORDER_CONSTANT, value=0)
        dilated = cv2.dilate(padded, stamp_kernel)
    else:
        dilated = mask
        spacing = 0

    h, w = dilated.shape
    ox = x - spacing
    oy = y - spacing
    occ_h, occ_w = occupancy.shape

    src_x0 = 0
    src_y0 = 0
    src_x1 = w
    src_y1 = h

    dst_x0 = ox
    dst_y0 = oy
    dst_x1 = ox + w
    dst_y1 = oy + h

    left_bound = margin
    right_bound = max_width - margin

    if dst_x0 < left_bound:
        src_x0 += (left_bound - dst_x0)
        dst_x0 = left_bound
    if dst_x1 > right_bound:
        src_x1 -= (dst_x1 - right_bound)
        dst_x1 = right_bound

    if dst_y0 < margin:
        src_y0 += (margin - dst_y0)
        dst_y0 = margin
    if dst_y1 > occ_h:
        src_y1 -= (dst_y1 - occ_h)
        dst_y1 = occ_h

    if src_x0 < src_x1 and src_y0 < src_y1:
        occupancy[dst_y0:dst_y1, dst_x0:dst_x1] |= dilated[src_y0:src_y1, src_x0:src_x1]


def _score_candidate(mask: np.ndarray, x: int, y: int, max_width: int, margin: int, max_y_used: int, area: int) -> tuple:
    bottom = y + mask.shape[0]
    increases_height = 1 if bottom > max_y_used else 0
    height_increase = max(0, bottom - max_y_used)
    center_dist = abs(x + mask.shape[1] // 2 - max_width // 2)
    space_right = max_width - margin - (x + mask.shape[1])
    fragmentation_penalty = 1 if (0 < space_right < 50) else 0
    return (increases_height, height_increase, fragmentation_penalty, -area, y, bottom, -center_dist)


def pack_images_masked(images: List[Image.Image], max_width: int, spacing: int, margin: int, step: int = 8, allow_rotate: bool = False, progress_cb=None, performance_mode: str = "balanced"):
    usable_width = max_width - 2 * margin
    
    from concurrent.futures import ThreadPoolExecutor
    from functools import partial
    
    _prep_fn = partial(_prepare_mask_variants,
                       usable_width=usable_width,
                       allow_rotate=allow_rotate,
                       performance_mode=performance_mode)
    
    with ThreadPoolExecutor(max_workers=min(len(images), 8)) as ex:
        all_variants = list(ex.map(_prep_fn, images))
        
    prepared = []
    for variants in all_variants:
        if not variants:
            continue
        primary = variants[0]
        prepared.append(
            {
                "variants": variants,
                "sort_key": (
                    primary["area"],
                    max(item["image"].height for item in variants),
                    max(item["image"].width for item in variants),
                ),
            }
        )

    prepared.sort(key=lambda item: item["sort_key"], reverse=True)

    # OPT 6: Pré-alocar occupancy com estimativa pessimista da altura final
    total_alpha_area = sum(p["variants"][0]["area"] for p in prepared)
    estimated_height = int(total_alpha_area / max(1, usable_width) * 1.6) + margin * 4
    initial_height = max(64, margin * 2 + 1, estimated_height)
    occupancy = np.zeros((initial_height, max_width), dtype=np.uint8)

    placed = []
    step = max(1, step)
    max_y_used = margin

    # OPT 1: Kernel de stamp pré-calculado uma única vez
    stamp_kernel = _build_stamp_kernel(spacing) if spacing > 0 else None

    total_count = len(prepared)
    remaining = prepared.copy()

    if performance_mode == "quality":
        lookahead = 5
    elif performance_mode == "balanced":
        lookahead = 3
    else:
        lookahead = 1

    processed_count = 0
    # OPT 3: Flag para evitar np.any(occupancy) no loop interno
    occupancy_is_empty = True

    while remaining:
        if progress_cb:
            progress_cb(processed_count, total_count)

        best_overall_choice = None
        best_piece_index = -1

        current_lookahead = min(len(remaining), lookahead)

        for i in range(current_lookahead):
            piece = remaining[i]
            best_choice = None
            max_occ_y = max_y_used + spacing

            for variant in piece["variants"]:
                img = variant["image"]
                mask = variant["mask"]
                w, h = img.size
                variant_best = None

                # Garantir que a área de busca seja suficiente
                search_h = max_y_used + spacing + h + step
                occupancy = _ensure_height(occupancy, search_h)

                # OPT 3: Atalho para occupancy vazio (primeira peça) — sem np.any
                if occupancy_is_empty and w <= max_width - 2 * margin:
                    score = _score_candidate(mask, margin, margin, max_width, margin, max_y_used, variant["area"])
                    variant_best = {"image": img, "mask": mask, "x": margin, "y": margin, "score": score}
                    if best_choice is None or variant_best["score"] < best_choice["score"]:
                        best_choice = variant_best
                    continue  # próxima variante — posição ótima já encontrada

                # --- BUSCA MULTI-ESCALA (COARSE-TO-FINE) ---
                if performance_mode == "quality":
                    if w < max_width * 0.15 or h < 150:
                        factor = 1
                    else:
                        factor = 2
                elif performance_mode == "balanced":
                    if w < max_width * 0.15 or h < 150:
                        factor = 2
                    else:
                        factor = 4
                else:  # fast
                    factor = 4

                try:
                    if factor > 1:
                        mask_f = mask.astype(np.float32)
                        occ_slice = occupancy[:search_h, :]
                        occ_f = occ_slice.astype(np.float32)
                        mask_c = cv2.resize(mask_f, (0, 0), fx=1 / factor, fy=1 / factor, interpolation=cv2.INTER_AREA)
                        occ_c = cv2.resize(occ_f, (0, 0), fx=1 / factor, fy=1 / factor, interpolation=cv2.INTER_AREA)
                        res_c = cv2.matchTemplate(occ_c, mask_c, cv2.TM_CCORR)

                        mask_sum = max(1.0, mask_c.sum())
                        res_c_norm = res_c / mask_sum
                        # OPT 3: usa occ_filled apenas com referência ao max_y_used (sem percorrer o array)
                        occ_filled = max_y_used > margin + 10
                        coarse_thresh = 0.05 if occ_filled else 0.02
                        MAX_CANDIDATES_PER_ROW = 8
                        found_any_in_coarse = False

                        for cy in range(margin // factor, res_c_norm.shape[0]):
                            base_y = cy * factor
                            min_y = base_y - factor
                            min_bottom = min_y + h

                            if variant_best is not None:
                                best_bottom = variant_best["score"][5]
                                best_y_sc = variant_best["score"][4]
                                if min_bottom > best_bottom:
                                    break
                                if min_bottom == best_bottom and min_y > best_y_sc:
                                    break

                            row_c = res_c_norm[cy, (margin // factor) : (max_width - w) // factor + 1]
                            all_promising = np.where(row_c <= coarse_thresh)[0]
                            if all_promising.size > MAX_CANDIDATES_PER_ROW:
                                top_indices = np.argsort(row_c[all_promising])[:MAX_CANDIDATES_PER_ROW]
                                promising_cx_indices = all_promising[top_indices]
                            else:
                                promising_cx_indices = all_promising

                            if promising_cx_indices.size > 0:
                                found_any_in_coarse = True

                                batch = []
                                fine_step = max(2, step // 2)

                                for pcx in promising_cx_indices:
                                    base_x = (margin // factor + pcx) * factor
                                    base_y = cy * factor
                                    for fy in range(max(margin, base_y - factor), base_y + factor + 1, fine_step):
                                        for fx in range(max(margin, base_x - factor), min(max_width - margin - w, base_x + factor + 1), fine_step):
                                            batch.append((fx, fy))

                                if batch and HAS_NUMBA and _evaluate_batch_jit is not None:
                                    idx, raw_score = _evaluate_batch_jit(occupancy, mask, np.array(batch, dtype=np.int32), max_y_used, max_occ_y, max_width, margin)
                                    if idx != -1:
                                        bottom = raw_score[3]
                                        fy_sc = raw_score[1]
                                        minus_center_dist = raw_score[4]
                                        fragmentation_penalty = raw_score[2]
                                        increases_height = 1 if bottom > max_y_used else 0
                                        height_increase = max(0, bottom - max_y_used)
                                        score = (increases_height, height_increase, fragmentation_penalty, -variant["area"], fy_sc, bottom, minus_center_dist)

                                        if variant_best is None or score < variant_best["score"]:
                                            bx, by = batch[idx]
                                            variant_best = {"image": img, "mask": mask, "x": bx, "y": by, "score": score}
                                else:
                                    for fx, fy in batch:
                                        if not _collides(occupancy, mask, fx, fy, max_occ_y):
                                            score = _score_candidate(mask, fx, fy, max_width, margin, max_y_used, variant["area"])
                                            if variant_best is None or score < variant_best["score"]:
                                                variant_best = {"image": img, "mask": mask, "x": fx, "y": fy, "score": score}

                        if not found_any_in_coarse:
                            raise Exception("No coarse match")
                    else:
                        # Busca direta para peças pequenas (factor=1)
                        y_limit = max_y_used + spacing
                        for fy in range(margin, y_limit + 1, step):
                            found_at_fy = False
                            for fx in range(margin, max_width - margin - w + 1, step):
                                if not _collides(occupancy, mask, fx, fy, max_occ_y):
                                    score = _score_candidate(mask, fx, fy, max_width, margin, max_y_used, variant["area"])
                                    if variant_best is None or score < variant_best["score"]:
                                        variant_best = {"image": img, "mask": mask, "x": fx, "y": fy, "score": score}
                                        found_at_fy = True
                            # OPT 5: Early-exit se encontramos posição que não aumenta altura
                            if found_at_fy and variant_best["score"][0] == 0:
                                break

                except Exception:
                    # Fallback — usa step para ambos os eixos para evitar loop lento
                    fallback_step = max(step, 4)
                    fy_limit = max_y_used + spacing + h + fallback_step
                    fy = margin
                    while fy <= fy_limit:
                        fx = margin
                        found_at_fy = False
                        while fx + w <= max_width - margin:
                            if not _collides(occupancy, mask, fx, fy, max_occ_y):
                                score = _score_candidate(mask, fx, fy, max_width, margin, max_y_used, variant["area"])
                                if variant_best is None or score < variant_best["score"]:
                                    variant_best = {"image": img, "mask": mask, "x": fx, "y": fy, "score": score}
                                found_at_fy = True
                                break
                            fx += fallback_step
                        if found_at_fy:
                            break
                        fy += fallback_step

                if variant_best is not None:
                    if best_choice is None or variant_best["score"] < best_choice["score"]:
                        best_choice = variant_best

            if best_choice is None:
                fallback = piece["variants"][0]
                img = fallback["image"]
                mask = fallback["mask"]
                x = margin
                y = max_y_used + spacing
                occupancy = _ensure_height(occupancy, y + img.height + spacing + margin + step)
                while x + img.width <= max_width - margin:
                    if not _collides(occupancy, mask, x, y, max_occ_y):
                        break
                    x += step
                best_choice = {"image": img, "mask": mask, "x": x, "y": y, "score": _score_candidate(mask, x, y, max_width, margin, max_y_used, fallback["area"])}

            if best_overall_choice is None or best_choice["score"] < best_overall_choice["score"]:
                best_overall_choice = best_choice
                best_piece_index = i

        # Ao final do lookahead, usamos a melhor peça encontrada
        piece_to_place = remaining.pop(best_piece_index)
        processed_count += 1

        img = best_overall_choice["image"]
        mask = best_overall_choice["mask"]
        x = best_overall_choice["x"]
        y = best_overall_choice["y"]

        # --- REFINAMENTO DE GRAVIDADE (NUDGE) com binary search ---
        if HAS_NUMBA and _nudge_gravity_jit is not None:
            max_occ_y = max_y_used + spacing
            x, y = _nudge_gravity_jit(occupancy, mask, x, y, margin, max_occ_y)
        else:
            # OPT 2 (Python): Binary search vertical + horizontal
            max_occ_y = max_y_used + spacing
            for _ in range(4):
                moved = False

                # Binary search vertical (cima)
                lo, hi = margin, y
                while lo < hi:
                    mid = (lo + hi) // 2
                    if _collides(occupancy, mask, x, mid, max_occ_y):
                        lo = mid + 1
                    else:
                        hi = mid
                if lo < y:
                    y = lo
                    moved = True

                # Binary search horizontal (esquerda)
                lo, hi = margin, x
                while lo < hi:
                    mid = (lo + hi) // 2
                    if _collides(occupancy, mask, mid, y, max_occ_y):
                        lo = mid + 1
                    else:
                        hi = mid
                if lo < x:
                    x = lo
                    moved = True

                # Diagonal (1 passo por vez)
                while y - 1 >= margin and x - 1 >= margin and not _collides(occupancy, mask, x - 1, y - 1, max_occ_y):
                    y -= 1
                    x -= 1
                    moved = True

                if not moved:
                    break

        placed.append((img, x, y))
        # OPT 1: Passa o kernel pré-calculado para _stamp_reserved
        _stamp_reserved(occupancy, mask, x, y, spacing, margin, max_width, stamp_kernel)
        max_y_used = max(max_y_used, y + img.height)
        # OPT 3: Atualiza a flag após a primeira peça ser estampada
        occupancy_is_empty = False

    final_height = max_y_used + margin
    return placed, max_width, final_height


if HAS_NUMBA:
    @numba.njit(nogil=True, parallel=True)
    def _blend_canvas_jit(canvas: np.ndarray, img: np.ndarray, x: int, y: int):
        h, w = img.shape[:2]
        ch, cw = canvas.shape[:2]
        y1, x1 = min(y + h, ch), min(x + w, cw)
        ih, iw = y1 - y, x1 - x
        if ih <= 0 or iw <= 0:
            return

        for i in numba.prange(ih):
            for j in range(iw):
                alpha = img[i, j, 3]
                if alpha == 255:
                    canvas[y + i, x + j] = img[i, j]
                elif alpha > 0:
                    a = alpha / 255.0
                    inv_a = 1.0 - a
                    for c in range(3):
                        new_val = img[i, j, c] * a + canvas[y + i, x + j, c] * inv_a
                        canvas[y + i, x + j, c] = np.uint8(new_val)
                    canvas[y + i, x + j, 3] = max(alpha, canvas[y + i, x + j, 3])


def build_canvas(packed, width, height):
    canvas_arr = np.zeros((height, width, 4), dtype=np.uint8)
    canvas_arr[:, :, :3] = 255  # Fundo branco
    canvas_arr[:, :, 3] = 255   # Alpha opaco para o fundo

    for img, x, y in packed:
        img_arr = np.array(img) if img.mode == "RGBA" else np.array(img.convert("RGBA"))
        if HAS_NUMBA:
            _blend_canvas_jit(canvas_arr, img_arr, x, y)
        else:
            h_img, w_img = img_arr.shape[:2]
            y1, x1 = min(y + h_img, height), min(x + w_img, width)
            h_fit, w_fit = y1 - y, x1 - x
            if h_fit <= 0 or w_fit <= 0:
                continue

            src = img_arr[:h_fit, :w_fit]
            dst = canvas_arr[y:y1, x:x1]
            a = src[:, :, 3:4].astype(np.uint16)
            ia = np.uint16(255) - a
            blended = (src[:, :, :3].astype(np.uint16) * a + dst[:, :, :3].astype(np.uint16) * ia + 127) >> 8
            canvas_arr[y:y1, x:x1, :3] = blended.astype(np.uint8)
            canvas_arr[y:y1, x:x1, 3] = np.maximum(dst[:, :, 3], src[:, :, 3])

    return Image.fromarray(canvas_arr, "RGBA")

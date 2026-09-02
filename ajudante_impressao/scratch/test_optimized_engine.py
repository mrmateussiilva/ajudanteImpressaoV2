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
    _prepare_mask_variants,
)

# Benchmark comparison between current packing and optimized coarse-to-fine packing
def generate_test_images():
    images = []
    for i in range(4):
        img = Image.new("RGBA", (2000, 2800), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pts = [(100, 100), (1900, 200), (1800, 2700), (200, 2600), (1000, 1400)]
        draw.polygon(pts, fill=((i*60)%255, 100, 200, 255))
        images.append(img)
    return images

# Fast Numba Contact Scorer
@numba.njit(fastmath=True, nogil=True)
def _fast_score_contact(
    occupancy: np.ndarray,
    x: int, y: int,
    w: int, h: int,
    spacing: int,
    margin: int,
    max_width: int,
) -> tuple[int, int]:
    occ_h, occ_w = occupancy.shape
    y0 = max(0, y - spacing - 2)
    y1 = min(y + h + spacing + 2, occ_h)
    x0 = max(0, x - spacing - 2)
    x1 = min(x + w + spacing + 2, occ_w)

    raw_contact = 0
    for r in range(y0, y1):
        for c in range(x0, x1):
            if occupancy[r, c] != 0:
                raw_contact += 1

    left_check = (x <= margin)
    if not left_check and x > 0:
        chk_y0 = max(0, y)
        chk_y1 = min(occ_h, y + h)
        chk_x0 = max(0, x - spacing - 4)
        chk_x1 = x
        for r in range(chk_y0, chk_y1):
            for c in range(chk_x0, chk_x1):
                if occupancy[r, c] != 0:
                    left_check = True
                    break
            if left_check:
                break

    right_check = (x + w >= max_width - margin)
    if not right_check and x + w < occ_w:
        chk_y0 = max(0, y)
        chk_y1 = min(occ_h, y + h)
        chk_x0 = x + w
        chk_x1 = min(occ_w, x + w + spacing + 4)
        for r in range(chk_y0, chk_y1):
            for c in range(chk_x0, chk_x1):
                if occupancy[r, c] != 0:
                    right_check = True
                    break
            if right_check:
                break

    top_check = (y <= margin)
    if not top_check and y > 0:
        chk_y0 = max(0, y - spacing - 4)
        chk_y1 = y
        chk_x0 = max(0, x)
        chk_x1 = min(occ_w, x + w)
        for r in range(chk_y0, chk_y1):
            for c in range(chk_x0, chk_x1):
                if occupancy[r, c] != 0:
                    top_check = True
                    break
            if top_check:
                break

    bottom_check = False
    if y + h < occ_h:
        chk_y0 = y + h
        chk_y1 = min(occ_h, y + h + spacing + 4)
        chk_x0 = max(0, x)
        chk_x1 = min(occ_w, x + w)
        for r in range(chk_y0, chk_y1):
            for c in range(chk_x0, chk_x1):
                if occupancy[r, c] != 0:
                    bottom_check = True
                    break
            if bottom_check:
                break

    sides_count = int(left_check) + int(right_check) + int(top_check) + int(bottom_check)
    is_pocket = (left_check or right_check) and (top_check or bottom_check)
    pocket_bonus = sides_count * 1000 if is_pocket else 0
    return raw_contact, pocket_bonus

# Fast Interlocking Pair using Coarse-to-Fine Search
def _fast_create_interlocking_pair(
    img_a: Image.Image,
    img_b: Image.Image,
    spacing: int,
    usable_width: int,
) -> Image.Image | None:
    from ajudante_impressao.algorithms.image_ops import trim_empty_borders
    img_a = trim_empty_borders(img_a)
    img_b_rot = trim_empty_borders(_rotate_image(img_b, 180))

    mask_a = _alpha_mask(img_a)
    mask_b = _alpha_mask(img_b_rot)

    h_a, w_a = mask_a.shape
    h_b, w_b = mask_b.shape

    if w_a + w_b > usable_width:
        return None

    max_h = max(h_a, h_b) + spacing * 2
    max_w = w_a + w_b + spacing * 4

    occupancy = np.zeros((max_h + 32, max_w + 32), dtype=np.uint8)
    stamp_kernel = _build_stamp_kernel(spacing) if spacing > 0 else None
    _stamp_reserved(occupancy, mask_a, 0, 0, spacing, 0, max_w, stamp_kernel)

    # Binary search for collision boundary
    low = max(0, w_a - w_b // 2)
    high = w_a + spacing
    best_x = high

    # Coarse search in steps of 16
    test_x = high
    while test_x >= low:
        if _collides_fast(occupancy, mask_b, test_x, 0, max_h):
            break
        best_x = test_x
        test_x -= 16

    # Fine search
    for fx in range(best_x, max(low, best_x - 16), -2):
        if _collides_fast(occupancy, mask_b, fx, 0, max_h):
            break
        best_x = fx

    pair_w = best_x + w_b
    pair_h = max_h

    if pair_w > usable_width or pair_w <= 0:
        return None

    pair_canvas = Image.new("RGBA", (pair_w, pair_h), (0, 0, 0, 0))
    if img_a.mode != "RGBA":
        img_a = img_a.convert("RGBA")
    if img_b_rot.mode != "RGBA":
        img_b_rot = img_b_rot.convert("RGBA")

    pair_canvas.paste(img_a, (0, 0), img_a.getchannel("A"))
    pair_canvas.paste(img_b_rot, (best_x, 0), img_b_rot.getchannel("A"))
    pair_cropped = trim_empty_borders(pair_canvas)

    area_sep = (w_a * h_a) + (w_b * h_b)
    area_pair = pair_cropped.width * pair_cropped.height

    if area_pair < area_sep * 0.95:
        pair_cropped.info["_original_id"] = img_a.info.get("_original_id", None)
        pair_cropped.info["_original_angle"] = 0
        return pair_cropped

    return None

def test_benchmark():
    images = generate_test_images()
    max_width = 4921
    spacing = 12
    margin = 20
    usable_width = max_width - 2 * margin

    print("Testando interlocking pair otimizado...")
    t0 = time.time()
    pair = _fast_create_interlocking_pair(images[0], images[1], spacing, usable_width)
    print(f"Tempo interlocking: {time.time() - t0:.4f}s (par criado: {pair is not None})")

if __name__ == "__main__":
    test_benchmark()

import time
import numpy as np
import cv2
import numba
from PIL import Image, ImageDraw
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ajudante_impressao.algorithms.packing import _alpha_mask, _rotate_image, _build_stamp_kernel, _stamp_reserved, _collides_fast

# 1. Numba-compiled fast contact scorer
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

def test_fast_contact():
    occ = np.zeros((6000, 4921), dtype=np.uint8)
    occ[100:2000, 100:2000] = 1
    # Warmup Numba
    _fast_score_contact(occ, 2010, 100, 500, 500, 12, 20, 4921)

    t0 = time.time()
    for _ in range(200):
        _fast_score_contact(occ, 2010, 100, 500, 500, 12, 20, 4921)
    t1 = time.time()
    print(f"200 fast contact scores in {t1-t0:.4f}s ({(t1-t0)/200*1000:.3f}ms per call)")

if __name__ == "__main__":
    test_fast_contact()

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import cv2
import numpy as np
from PIL import Image

from .image_ops import trim_empty_borders


# ── Máscara alfa binária ──────────────────────────────────────────────────────
def _alpha_mask(img: Image.Image) -> np.ndarray:
    mask = np.array(img.getchannel("A"), dtype=np.uint8)
    return (mask > 0).astype(np.uint8)


def _quantize(value: int, step: int, minimum: int) -> int:
    if value <= minimum:
        return minimum
    return minimum + ((value - minimum + step - 1) // step) * step


@dataclass(slots=True)
class MaskVariant:
    image: Image.Image
    mask: np.ndarray
    scaled_mask: np.ndarray
    scaled_mask_f: np.ndarray
    mask_sum: float
    area: int
    angle: int
    w: int
    h: int
    sw: int
    sh: int


@dataclass(slots=True)
class PackedPiece:
    image: Image.Image
    mask: np.ndarray
    scaled_mask: np.ndarray
    x: int
    y: int
    w: int
    h: int
    area: int


# ── Rotação via cv2 (3-5x mais rápido que PIL para 90/180/270) ────────────────
_CV2_ROT_MAP = {
    90:  cv2.ROTATE_90_COUNTERCLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_CLOCKWISE,
}

def _rotate_image(img: Image.Image, angle: int) -> Image.Image:
    if angle in _CV2_ROT_MAP:
        arr = np.array(img)
        rotated_arr = cv2.rotate(arr, _CV2_ROT_MAP[angle])
        return Image.fromarray(rotated_arr)
    return img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


def _prepare_mask_variants(
    img: Image.Image,
    usable_width: int,
    allow_rotate: bool,
    performance_mode: str = "balanced",
    scale: int = 8,
) -> list[MaskVariant]:
    original_id = img.info.get("_original_id", None)
    img = trim_empty_borders(img)
    angle_candidates = [0]
    if allow_rotate:
        if performance_mode == "fast":
            angle_candidates.extend([90])
        elif performance_mode == "quality":
            angle_candidates.extend([90, 270, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75])
        else:
            angle_candidates.extend([90, 270])

    variants: list[MaskVariant] = []
    seen: set[tuple[int, int, int]] = set()

    for angle in angle_candidates:
        variant = img if angle == 0 else trim_empty_borders(_rotate_image(img, angle))
        if variant.width > usable_width or variant.width <= 0 or variant.height <= 0:
            continue
        mask = _alpha_mask(variant)
        alpha_area = int(mask.sum())
        signature = (variant.width, variant.height, alpha_area)
        if alpha_area <= 0 or signature in seen:
            continue
        seen.add(signature)
        variant.info["_original_id"] = original_id
        variant.info["_original_angle"] = angle

        w, h = variant.width, variant.height
        sw = max(1, w // scale)
        sh = max(1, h // scale)
        small = cv2.resize(mask, (sw, sh), interpolation=cv2.INTER_AREA)
        scaled_mask = (small > 0).astype(np.uint8)
        scaled_mask_f = scaled_mask.astype(np.float32)
        mask_sum = float(scaled_mask_f.sum())

        variants.append(MaskVariant(
            image=variant,
            mask=mask,
            scaled_mask=scaled_mask,
            scaled_mask_f=scaled_mask_f,
            mask_sum=mask_sum,
            area=alpha_area,
            angle=angle,
            w=w,
            h=h,
            sw=sw,
            sh=sh,
        ))

    variants.sort(key=lambda v: (v.area, v.h, v.w), reverse=True)
    return variants


def _ensure_height(occupancy: np.ndarray, min_height: int) -> np.ndarray:
    if min_height <= occupancy.shape[0]:
        return occupancy
    growth = max(min_height + 2048, occupancy.shape[0] * 2)
    expanded = np.zeros((growth, occupancy.shape[1]), dtype=np.uint8)
    expanded[: occupancy.shape[0], :] = occupancy
    return expanded


def _build_stamp_kernel(spacing: int) -> np.ndarray:
    y_idx, x_idx = np.ogrid[-spacing:spacing + 1, -spacing:spacing + 1]
    return (x_idx ** 2 + y_idx ** 2 <= spacing ** 2).astype(np.uint8)


try:
    import numba

    @numba.njit(fastmath=True, nogil=True)
    def _collides_fast(
        occupancy: np.ndarray,
        mask: np.ndarray,
        x: int, y: int,
        max_occ_y: int,
    ) -> bool:
        if y >= max_occ_y:
            return False
        occ_h, occ_w = occupancy.shape
        h, w = mask.shape
        if y < 0 or x < 0 or y + h > occ_h or x + w > occ_w:
            return True
        check_h = min(h, max_occ_y - y)
        if check_h <= 0:
            return False

        for r in range(check_h):
            occ_row = occupancy[y + r]
            mask_row = mask[r]
            for c in range(w):
                if mask_row[c] != 0 and occ_row[x + c] != 0:
                    return True
        return False

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
            occ_row = scaled_occ[y + r]
            mask_row = scaled_mask[r]
            for c in range(w):
                if mask_row[c] != 0 and occ_row[x + c] != 0:
                    return True
        return False

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
            occ_row = occupancy[r]
            for c in range(x0, x1):
                if occ_row[c] != 0:
                    raw_contact += 1

        left_check = (x <= margin)
        if not left_check and x > 0:
            chk_y0 = max(0, y)
            chk_y1 = min(occ_h, y + h)
            chk_x0 = max(0, x - spacing - 4)
            chk_x1 = x
            for r in range(chk_y0, chk_y1):
                occ_row = occupancy[r]
                for c in range(chk_x0, chk_x1):
                    if occ_row[c] != 0:
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
                occ_row = occupancy[r]
                for c in range(chk_x0, chk_x1):
                    if occ_row[c] != 0:
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
                occ_row = occupancy[r]
                for c in range(chk_x0, chk_x1):
                    if occ_row[c] != 0:
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
                occ_row = occupancy[r]
                for c in range(chk_x0, chk_x1):
                    if occ_row[c] != 0:
                        bottom_check = True
                        break
                if bottom_check:
                    break

        sides_count = int(left_check) + int(right_check) + int(top_check) + int(bottom_check)
        is_pocket = (left_check or right_check) and (top_check or bottom_check)
        pocket_bonus = sides_count * 1000 if is_pocket else 0
        return raw_contact, pocket_bonus

    @numba.njit(fastmath=True, nogil=True)
    def _find_row_transitions_fast(row: np.ndarray, margin: int):
        n = len(row)
        transitions = []
        in_segment = False
        start = 0
        for i in range(n):
            val = row[i]
            if val != 0 and not in_segment:
                in_segment = True
                start = i + margin
            elif val == 0 and in_segment:
                in_segment = False
                transitions.append((start, i + margin))
        if in_segment:
            transitions.append((start, n + margin))
        return transitions

    HAS_NUMBA = True

    # Pre-warm JIT compilation at import time
    _dummy_occ = np.zeros((16, 16), dtype=np.uint8)
    _dummy_mask = np.zeros((4, 4), dtype=np.uint8)
    _collides_fast(_dummy_occ, _dummy_mask, 0, 0, 16)
    _collides_coarse(_dummy_occ, _dummy_mask, 0, 0, 16)
    _fast_score_contact(_dummy_occ, 2, 2, 4, 4, 1, 1, 16)
    _find_row_transitions_fast(np.zeros(16, dtype=np.uint8), 0)

except Exception:
    HAS_NUMBA = False

    def _collides_fast(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, max_occ_y: int) -> bool:
        if y >= max_occ_y:
            return False
        h, w = mask.shape
        if y < 0 or x < 0 or y + h > occupancy.shape[0] or x + w > occupancy.shape[1]:
            return True
        check_h = min(h, max_occ_y - y)
        if check_h <= 0:
            return False
        occ_slice = occupancy[y:y + check_h, x:x + w]
        if not occ_slice.any():
            return False
        return bool((occ_slice & mask[:check_h, :]).any())

    def _collides_coarse(scaled_occ: np.ndarray, scaled_mask: np.ndarray, x: int, y: int, max_y: int) -> bool:
        return _collides_fast(scaled_occ, scaled_mask, x, y, max_y)

    def _fast_score_contact(occupancy: np.ndarray, x: int, y: int, w: int, h: int, spacing: int, margin: int, max_width: int) -> tuple[int, int]:
        h_occ, w_occ = occupancy.shape
        y0 = max(0, y - spacing - 2)
        y1 = min(y + h + spacing + 2, h_occ)
        x0 = max(0, x - spacing - 2)
        x1 = min(x + w + spacing + 2, w_occ)
        raw_contact = int(occupancy[y0:y1, x0:x1].sum())
        left_check = x <= margin or (x > 0 and bool(occupancy[max(0, y):min(h_occ, y + h), max(0, x - spacing - 4):x].any()))
        right_check = (x + w >= max_width - margin) or (x + w < w_occ and bool(occupancy[max(0, y):min(h_occ, y + h), x + w:min(w_occ, x + w + spacing + 4)].any()))
        top_check = y <= margin or (y > 0 and bool(occupancy[max(0, y - spacing - 4):y, max(0, x):min(w_occ, x + w)].any()))
        bottom_check = bool(occupancy[y + h:min(h_occ, y + h + spacing + 4), max(0, x):min(w_occ, x + w)].any())
        sides_count = int(left_check) + int(right_check) + int(top_check) + int(bottom_check)
        is_pocket = (left_check or right_check) and (top_check or bottom_check)
        pocket_bonus = sides_count * 1000 if is_pocket else 0
        return raw_contact, pocket_bonus


def _collides(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, max_occ_y: int) -> bool:
    return _collides_fast(occupancy, mask, x, y, max_occ_y)


def _stamp_reserved(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    spacing: int,
    margin: int,
    max_width: int,
    stamp_kernel: np.ndarray | None = None,
) -> None:
    if spacing > 0:
        if stamp_kernel is None:
            stamp_kernel = _build_stamp_kernel(spacing)
        padded = cv2.copyMakeBorder(mask, spacing, spacing, spacing, spacing, cv2.BORDER_CONSTANT, value=0)
        dilated = cv2.dilate(padded, stamp_kernel)
    else:
        dilated = mask
        spacing = 0

    h, w = dilated.shape
    ox, oy = x - spacing, y - spacing
    occ_h, occ_w = occupancy.shape

    src_x0, src_y0, src_x1, src_y1 = 0, 0, w, h
    dst_x0, dst_y0, dst_x1, dst_y1 = ox, oy, ox + w, oy + h

    left_bound, right_bound = margin, max_width - margin

    if dst_x0 < left_bound:
        src_x0 += left_bound - dst_x0
        dst_x0 = left_bound
    if dst_x1 > right_bound:
        src_x1 -= dst_x1 - right_bound
        dst_x1 = right_bound
    if dst_y0 < margin:
        src_y0 += margin - dst_y0
        dst_y0 = margin
    if dst_y1 > occ_h:
        src_y1 -= dst_y1 - occ_h
        dst_y1 = occ_h

    if src_x0 < src_x1 and src_y0 < src_y1:
        occupancy[dst_y0:dst_y1, dst_x0:dst_x1] |= dilated[src_y0:src_y1, src_x0:src_x1]


def _score_contact(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    spacing: int,
    margin: int = 0,
    max_width: int = 0,
) -> tuple[int, int]:
    return _fast_score_contact(occupancy, x, y, mask.shape[1], mask.shape[0], spacing, margin, max_width)


def _score_candidate(
    mask: np.ndarray,
    x: int, y: int,
    max_width: int,
    margin: int,
    max_y_used: int,
    area: int,
) -> tuple:
    bottom = y + mask.shape[0]
    increases_height = 1 if bottom > max_y_used else 0
    height_increase = max(0, bottom - max_y_used)
    center_dist = abs(x + mask.shape[1] // 2 - max_width // 2)
    space_right = max_width - margin - (x + mask.shape[1])
    fragmentation_penalty = 1 if 0 < space_right < 50 else 0
    return (increases_height, height_increase, fragmentation_penalty, -area, y, bottom, -center_dist)


def _dedupe_candidates(candidates: list[tuple[int, int]], limit: int) -> list[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    deduped: list[tuple[int, int]] = []
    for x, y in candidates:
        key = (int(x), int(y))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
        if len(deduped) >= limit:
            break
    return deduped


def _collect_frontier_candidates(
    occupancy: np.ndarray,
    placed: list[PackedPiece],
    margin: int,
    max_width: int,
    search_h: int,
    piece_w: int,
    piece_h: int,
    step: int,
    spacing: int,
    limit: int = 64,
) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = [(margin, margin)]
    x_limit = max(margin, max_width - margin - piece_w)

    for piece in placed:
        right_x = piece.x + piece.w + spacing
        below_y = piece.y + piece.h + spacing
        candidates.append((right_x, piece.y))
        candidates.append((piece.x, below_y))
        candidates.append((right_x, below_y))
        candidates.append((piece.x + piece.w // 2 - piece_w // 2, piece.y))
        candidates.append((piece.x, piece.y + piece.h // 2 - piece_h // 2))
        candidates.append((margin, below_y))
        candidates.append((max_width - margin - piece_w, piece.y))
        candidates.append((max_width - margin - piece_w, below_y))

    max_y_used = max((piece.y + piece.h for piece in placed), default=margin)
    band_top = max(margin, max_y_used - max(piece_h, step * 6))
    band_bottom = min(search_h, max_y_used + max(piece_h // 2, step * 4))
    row_stride = max(16, step * 2)

    if band_bottom > band_top and HAS_NUMBA:
        for y in range(band_top, band_bottom, row_stride):
            row = occupancy[y, margin:max_width - margin]
            if not row.any():
                continue
            transitions = _find_row_transitions_fast(row, margin)
            for start, end in transitions:
                candidates.append((end + spacing, y))
                candidates.append((end, y))
                candidates.append((max(margin, start - piece_w), y))
                candidates.append((max(margin, start - piece_w // 2), y))
                candidates.append((min(x_limit, end + spacing // 2), y))

    filtered: list[tuple[int, int]] = []
    for x, y in candidates:
        if x < margin or y < margin or x > x_limit or y > search_h:
            continue
        filtered.append((x, y))

    filtered.sort(key=lambda p: (p[1], p[0]))
    return _dedupe_candidates(filtered, limit)


def _refine_candidate(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int,
    y: int,
    min_x: int,
    min_y: int,
    max_occ_y: int,
    max_width: int,
    max_iters: int = 4,
) -> tuple[int, int]:
    step = 8
    for _ in range(max_iters):
        moved = False
        for dx, dy in ((0, -1), (-1, 0), (-1, -1), (1, -1)):
            nx = x + dx * step
            ny = y + dy * step
            if nx < min_x or ny < min_y or nx + mask.shape[1] > max_width:
                continue
            if not _collides_fast(occupancy, mask, nx, ny, max_occ_y):
                x, y = nx, ny
                moved = True
                break
        if not moved:
            if step <= 2:
                break
            step //= 2
    return x, y


def _find_valid_positions_nfp(
    occupancy: np.ndarray,
    scaled_occ: np.ndarray,
    variant: MaskVariant,
    max_width: int,
    margin: int,
    search_h: int,
    step: int = 8,
    spacing: int = 0,
    scale: int = 8,
    top_k: int = 64,
    raster_search: bool = True,
    placed: list[PackedPiece] | None = None,
) -> list[tuple[int, int]]:
    mask = variant.mask
    s_mask = variant.scaled_mask
    w_m, h_m = variant.w, variant.h
    sw_m, sh_m = variant.sw, variant.sh

    if h_m <= 0 or w_m <= 0:
        return [(margin, margin)]

    if not occupancy[:search_h, :].any():
        return [(margin, margin)]

    results: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    if placed is None:
        placed = []

    s_search_h = min(scaled_occ.shape[0], max(1, search_h // scale))
    s_margin = margin // scale

    frontier_limit = min(32, top_k // 2)
    frontier_candidates = _collect_frontier_candidates(
        occupancy=occupancy,
        placed=placed,
        margin=margin,
        max_width=max_width,
        search_h=search_h,
        piece_w=w_m,
        piece_h=h_m,
        step=step,
        spacing=spacing,
        limit=frontier_limit,
    )

    for fx, fy in frontier_candidates:
        if (fx, fy) in seen:
            continue
        seen.add((fx, fy))
        if fx + w_m > max_width - margin or fy + h_m > search_h:
            continue
        # Coarse-check first (nanoseconds)
        if _collides_coarse(scaled_occ, s_mask, fx // scale, fy // scale, s_search_h):
            continue
        # Fine-check
        if not _collides_fast(occupancy, mask, fx, fy, search_h):
            results.append((fx, fy))

    if not raster_search or len(results) >= top_k or not scaled_occ[:s_search_h, :].any():
        return results if results else [(margin, search_h - h_m)]

    # MatchTemplate on precomputed low-res grid
    s_occ_slice = scaled_occ[:s_search_h, :]
    free_c = (s_occ_slice == 0).astype(np.float32)

    if free_c.shape[0] <= sh_m or free_c.shape[1] <= sw_m or variant.mask_sum < 1.0:
        return results if results else [(margin, search_h - h_m)]

    res = cv2.matchTemplate(free_c, variant.scaled_mask_f, cv2.TM_CCORR)
    res_norm = res / variant.mask_sum

    ys_c = xs_c = np.array([], dtype=np.int64)
    for thresh in (0.999, 0.95, 0.85, 0.65):
        ys_c, xs_c = np.where(res_norm >= thresh)
        if len(ys_c) > 0:
            break

    if len(ys_c) == 0:
        return results if results else [(margin, search_h - h_m)]

    x_limit_c = max(1, (max_width - margin - w_m) // scale)
    valid = (ys_c >= s_margin) & (xs_c >= s_margin) & (xs_c <= x_limit_c)
    ys_c, xs_c = ys_c[valid], xs_c[valid]

    if len(ys_c) == 0:
        return results if results else [(margin, search_h - h_m)]

    order = np.lexsort((xs_c, ys_c))
    coarse_candidates = []
    seen_cells = set()
    for cx, cy in zip(xs_c[order].tolist(), ys_c[order].tolist()):
        cell = (cx // 2, cy // 2)
        if cell in seen_cells:
            continue
        seen_cells.add(cell)
        coarse_candidates.append((cx * scale, cy * scale))
        if len(coarse_candidates) >= 32:
            break

    for bx, by in coarse_candidates:
        if bx + w_m > max_width - margin or by + h_m > search_h:
            continue
        if (bx, by) in seen:
            continue
        seen.add((bx, by))
        if _collides_coarse(scaled_occ, s_mask, bx // scale, by // scale, s_search_h):
            continue
        if not _collides_fast(occupancy, mask, bx, by, search_h):
            results.append((bx, by))
            if len(results) >= top_k:
                break

    return results if results else [(margin, search_h - h_m)]


def _nudge_gravity_full(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    min_x: int,
    min_y: int,
    max_occ_y: int,
    max_iters: int = 6,
) -> tuple[int, int]:
    """Desloca a peça em direção ao canto superior-esquerdo com passo decrescente."""
    DIRS = ((0, -1), (-1, 0), (-1, -1), (1, -1))
    step = 4
    for _ in range(max_iters):
        moved = False
        for dx, dy in DIRS:
            nx, ny = x + dx * step, y + dy * step
            if ny < min_y or nx < min_x:
                continue
            if not _collides_fast(occupancy, mask, nx, ny, max_occ_y):
                x, y = nx, ny
                moved = True
                break
        if not moved:
            if step <= 1:
                break
            step = max(1, step // 2)
    return x, y


def _create_interlocking_pair(
    img_a: Image.Image,
    img_b: Image.Image,
    spacing: int,
    usable_width: int,
) -> Image.Image | None:
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

    # Coarse search in steps of 16 followed by fine scan
    low = max(0, w_a - w_b // 2)
    high = w_a + spacing
    best_x = high

    test_x = high
    while test_x >= low:
        if _collides_fast(occupancy, mask_b, test_x, 0, max_h):
            break
        best_x = test_x
        test_x -= 16

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


def _run_single_pass(
    prepared_items: list[dict],
    max_width: int,
    spacing: int,
    margin: int,
    step: int,
    performance_mode: str,
    progress_cb=None,
) -> tuple[list[tuple[Image.Image, int, int]], int, int, int]:
    scale = 8
    usable_width = max_width - 2 * margin
    total_alpha_area = sum(p["variants"][0].area for p in prepared_items)
    estimated_height = int(total_alpha_area / max(1, usable_width) * 1.6) + margin * 4
    initial_height = max(64, margin * 2 + 1, estimated_height)

    occupancy = np.zeros((initial_height, max_width), dtype=np.uint8)
    scaled_occ = np.zeros((max(2, initial_height // scale), max(2, max_width // scale)), dtype=np.uint8)

    placed: list[PackedPiece] = []
    max_y_used = margin
    stamp_kernel = _build_stamp_kernel(spacing) if spacing > 0 else None
    total_count = len(prepared_items)
    candidate_limit = 32 if performance_mode == "fast" else 64
    raster_search = performance_mode != "fast"

    for processed_count, piece in enumerate(prepared_items):
        if progress_cb:
            progress_cb(processed_count, total_count)

        best_choice = None
        max_occ_y = max_y_used + spacing

        for variant in piece["variants"]:
            img = variant.image
            mask = variant.mask
            w, h = variant.w, variant.h
            search_h = max_y_used + spacing + h + step

            occupancy = _ensure_height(occupancy, search_h)
            s_min_h = max(2, search_h // scale)
            if s_min_h > scaled_occ.shape[0]:
                s_growth = max(s_min_h + 256, scaled_occ.shape[0] * 2)
                s_exp = np.zeros((s_growth, scaled_occ.shape[1]), dtype=np.uint8)
                s_exp[: scaled_occ.shape[0], :] = scaled_occ
                scaled_occ = s_exp

            valid_positions = _find_valid_positions_nfp(
                occupancy=occupancy,
                scaled_occ=scaled_occ,
                variant=variant,
                max_width=max_width,
                margin=margin,
                search_h=search_h,
                step=step,
                spacing=spacing,
                scale=scale,
                top_k=candidate_limit,
                raster_search=raster_search,
                placed=placed,
            )

            for fx, fy in valid_positions:
                score = _score_candidate(mask, fx, fy, max_width, margin, max_y_used, variant.area)
                contact, pocket_bonus = _fast_score_contact(occupancy, fx, fy, w, h, spacing, margin, max_width)
                angle_penalty = 0 if variant.angle in (0, 90, 270) else 1
                final_score = (score[0], score[1], angle_penalty, -pocket_bonus, -contact, score[2], score[3], score[4], score[5])

                if best_choice is None or final_score < best_choice["score"]:
                    best_choice = {
                        "variant": variant,
                        "image": img, "mask": mask,
                        "x": fx, "y": fy,
                        "score": final_score,
                    }

            if best_choice is not None and best_choice["variant"] is variant:
                rx, ry = _refine_candidate(
                    occupancy=occupancy,
                    mask=mask,
                    x=best_choice["x"],
                    y=best_choice["y"],
                    min_x=margin,
                    min_y=margin,
                    max_occ_y=max_occ_y + h + step,
                    max_width=max_width,
                )
                if (rx, ry) != (best_choice["x"], best_choice["y"]):
                    score = _score_candidate(mask, rx, ry, max_width, margin, max_y_used, variant.area)
                    contact, pocket_bonus = _fast_score_contact(occupancy, rx, ry, w, h, spacing, margin, max_width)
                    angle_penalty = 0 if variant.angle in (0, 90, 270) else 1
                    refined_score = (score[0], score[1], angle_penalty, -pocket_bonus, -contact, score[2], score[3], score[4], score[5])
                    if refined_score < best_choice["score"]:
                        best_choice = {
                            "variant": variant,
                            "image": img,
                            "mask": mask,
                            "x": rx,
                            "y": ry,
                            "score": refined_score,
                        }

        if best_choice is None:
            fallback = piece["variants"][0]
            img = fallback.image
            mask = fallback.mask
            best_choice = {
                "variant": fallback,
                "image": img, "mask": mask,
                "x": margin, "y": max_y_used + spacing,
                "score": (1, fallback.h, 0, 0, -fallback.area, margin, max_y_used + spacing),
            }

        chosen_variant = best_choice["variant"]
        img = chosen_variant.image
        mask = chosen_variant.mask
        x = best_choice["x"]
        y = best_choice["y"]
        nudge_occ_y = min(max_y_used + spacing + chosen_variant.h + step, occupancy.shape[0])
        y_floor = y if y > margin else margin
        x, y = _nudge_gravity_full(
            occupancy=occupancy,
            mask=mask,
            x=x, y=y,
            min_x=margin,
            min_y=max(margin, y_floor - 32),
            max_occ_y=nudge_occ_y,
        )

        placed.append(PackedPiece(
            image=img,
            mask=mask,
            scaled_mask=chosen_variant.scaled_mask,
            x=x,
            y=y,
            w=chosen_variant.w,
            h=chosen_variant.h,
            area=chosen_variant.area,
        ))

        _stamp_reserved(occupancy, mask, x, y, spacing, margin, max_width, stamp_kernel)
        _stamp_reserved(
            scaled_occ, chosen_variant.scaled_mask,
            x // scale, y // scale,
            max(0, spacing // scale), margin // scale, max_width // scale,
            None,
        )
        max_y_used = max(max_y_used, y + chosen_variant.h)

    final_height = max_y_used + margin
    total_placed_area = sum(piece.area for piece in placed)
    return [(piece.image, piece.x, piece.y) for piece in placed], max_width, final_height, total_placed_area


def _mutate_order(items: list) -> list:
    mutated = list(items)
    if len(mutated) < 2:
        return mutated
    idx1, idx2 = random.sample(range(len(mutated)), 2)
    mutated[idx1], mutated[idx2] = mutated[idx2], mutated[idx1]
    return mutated


def _crossover_order(parent1: list, parent2: list) -> list:
    n = len(parent1)
    if n < 3:
        return list(parent1)
    cut1, cut2 = sorted(random.sample(range(n), 2))
    child = [None] * n
    child[cut1:cut2] = parent1[cut1:cut2]

    p2_idx = 0
    for i in range(n):
        if child[i] is None:
            while parent2[p2_idx] in child:
                p2_idx += 1
            child[i] = parent2[p2_idx]
            p2_idx += 1
    return child


def _run_genetic_packing(
    prepared_base: list[list[MaskVariant]],
    max_width: int,
    spacing: int,
    margin: int,
    step: int,
    performance_mode: str,
    progress_cb=None,
) -> tuple[list[tuple[Image.Image, int, int]], int, int, int]:
    seed1 = sorted(
        prepared_base,
        key=lambda v_list: (v_list[0].area, max(v.h for v in v_list), max(v.w for v in v_list)),
        reverse=True,
    )
    seed2 = sorted(
        prepared_base,
        key=lambda v_list: (max(v.h for v in v_list), v_list[0].area, max(v.w for v in v_list)),
        reverse=True,
    )
    seed3 = sorted(
        prepared_base,
        key=lambda v_list: (v_list[0].w * v_list[0].h, v_list[0].area),
        reverse=True,
    )

    pop_size = 6 if performance_mode == "quality" else 4
    num_generations = 2 if performance_mode == "quality" else 1

    population = [seed1, seed2, seed3]
    while len(population) < pop_size:
        base_seed = random.choice([seed1, seed2, seed3])
        population.append(_mutate_order(base_seed))

    best_result = None

    def eval_individual(indiv):
        prepared_items = [{"variants": v_list} for v_list in indiv]
        return _run_single_pass(
            prepared_items=prepared_items,
            max_width=max_width,
            spacing=spacing,
            margin=margin,
            step=step,
            performance_mode=performance_mode,
        )

    for gen in range(num_generations):
        with ThreadPoolExecutor(max_workers=min(len(population), 4)) as ex:
            results = list(ex.map(eval_individual, population))

        eval_pairs = list(zip(population, results))
        eval_pairs.sort(key=lambda pair: pair[1][2])

        if best_result is None or eval_pairs[0][1][2] < best_result[2]:
            best_result = eval_pairs[0][1]

        elite_count = max(2, len(population) // 2)
        elites = [pair[0] for pair in eval_pairs[:elite_count]]

        new_population = list(elites)
        while len(new_population) < pop_size:
            p1, p2 = random.sample(elites, 2)
            child = _crossover_order(p1, p2)
            if random.random() < 0.4:
                child = _mutate_order(child)
            new_population.append(child)

        population = new_population

    return best_result


def pack_images_masked(
    images: list[Image.Image],
    max_width: int,
    spacing: int,
    margin: int,
    step: int = 8,
    allow_rotate: bool = False,
    progress_cb=None,
    performance_mode: str = "balanced",
):
    for idx, img in enumerate(images):
        img.info["_original_id"] = idx

    usable_width = max_width - 2 * margin

    target_images = list(images)
    if allow_rotate and performance_mode != "fast" and len(images) >= 2:
        used_indices = set()
        paired_list = []
        i = 0
        while i < len(images):
            if i in used_indices:
                i += 1
                continue
            img_a = images[i]
            matched = False
            for j in range(i + 1, len(images)):
                if j in used_indices:
                    continue
                img_b = images[j]
                pair_img = _create_interlocking_pair(img_a, img_b, spacing, usable_width)
                if pair_img is not None:
                    paired_list.append(pair_img)
                    used_indices.add(i)
                    used_indices.add(j)
                    matched = True
                    break
            if not matched:
                paired_list.append(img_a)
                used_indices.add(i)
            i += 1

        if len(used_indices) > 0:
            target_images = paired_list

    _prep_fn = partial(
        _prepare_mask_variants,
        usable_width=usable_width,
        allow_rotate=allow_rotate,
        performance_mode=performance_mode,
    )

    with ThreadPoolExecutor(max_workers=min(len(target_images), 8)) as ex:
        all_variants = list(ex.map(_prep_fn, target_images))

    prepared_base = []
    for variants in all_variants:
        if not variants:
            continue
        prepared_base.append(variants)

    if not prepared_base:
        return [], max_width, margin * 2, 0

    if performance_mode == "fast":
        prepared_items = [{"variants": v_list} for v_list in prepared_base]
        best_result = _run_single_pass(
            prepared_items=prepared_items,
            max_width=max_width,
            spacing=spacing,
            margin=margin,
            step=step,
            performance_mode=performance_mode,
            progress_cb=progress_cb,
        )
    else:
        best_result = _run_genetic_packing(
            prepared_base=prepared_base,
            max_width=max_width,
            spacing=spacing,
            margin=margin,
            step=step,
            performance_mode=performance_mode,
            progress_cb=progress_cb,
        )

    packed, final_w, final_h, useful_area_px = best_result
    return packed, final_w, final_h, useful_area_px


def build_canvas(packed, width, height):
    canvas_arr = np.zeros((height, width, 4), dtype=np.uint8)
    canvas_arr[:, :, :3] = 255
    canvas_arr[:, :, 3] = 255

    for img, x, y in packed:
        img_arr = np.array(img) if img.mode == "RGBA" else np.array(img.convert("RGBA"))
        h_img, w_img = img_arr.shape[:2]
        y1 = min(y + h_img, height)
        x1 = min(x + w_img, width)
        h_fit = y1 - y
        w_fit = x1 - x
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

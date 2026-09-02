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
    _dedupe_candidates,
    _score_candidate,
)

# 1. Numba Fast Contact Scorer
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

# 2. Fast Frontier Candidates Collection
def _collect_frontier_candidates_fast(
    occupancy: np.ndarray,
    placed: list[PackedPiece],
    margin: int,
    max_width: int,
    search_h: int,
    piece_w: int,
    piece_h: int,
    step: int,
    spacing: int,
    limit: int = 128,
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

    if band_bottom > band_top:
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

# 3. Optimized NFP & Raster Candidate Finder
def _find_valid_positions_optimized(
    occupancy: np.ndarray,
    mask: np.ndarray,
    max_width: int,
    margin: int,
    search_h: int,
    step: int = 8,
    spacing: int = 0,
    scale: int = 8,
    top_k: int = 96,
    raster_search: bool = True,
    placed: list[PackedPiece] | None = None,
) -> list[tuple[int, int]]:
    h_m, w_m = mask.shape
    if h_m <= 0 or w_m <= 0:
        return [(margin, margin)]

    if not occupancy[:search_h, :].any():
        return [(margin, margin)]

    results: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    if placed is None:
        placed = []

    frontier_candidates = _collect_frontier_candidates_fast(
        occupancy=occupancy,
        placed=placed,
        margin=margin,
        max_width=max_width,
        search_h=search_h,
        piece_w=w_m,
        piece_h=h_m,
        step=step,
        spacing=spacing,
        limit=min(48, top_k // 2),
    )

    for fx, fy in frontier_candidates:
        if (fx, fy) in seen:
            continue
        seen.add((fx, fy))
        if fx + w_m > max_width - margin or fy + h_m > search_h:
            continue
        if not _collides_fast(occupancy, mask, fx, fy, search_h):
            results.append((fx, fy))

    if not raster_search or len(results) >= top_k:
        return results if results else [(margin, search_h - h_m)]

    # Coarse grid template matching
    h_c = max(2, search_h // scale)
    w_c = max(2, max_width // scale)

    # Downscale occupancy with cv2 on uint8 directly
    occ_slice = occupancy[:search_h, :]
    occ_small = cv2.resize(occ_slice, (w_c, h_c), interpolation=cv2.INTER_AREA)
    free_c = (occ_small == 0).astype(np.float32)

    mask_w_c = max(1, w_m // scale)
    mask_h_c = max(1, h_m // scale)
    mask_small = cv2.resize(mask, (mask_w_c, mask_h_c), interpolation=cv2.INTER_AREA)
    mask_small_f = (mask_small > 0).astype(np.float32)

    if mask_small_f.shape[0] >= free_c.shape[0] or mask_small_f.shape[1] >= free_c.shape[1]:
        return results if results else [(margin, search_h - h_m)]

    mask_sum = float(mask_small_f.sum())
    if mask_sum < 1.0:
        return results if results else [(margin, margin)]

    res = cv2.matchTemplate(free_c, mask_small_f, cv2.TM_CCORR)
    res_norm = res / mask_sum

    ys_c = xs_c = np.array([], dtype=np.int64)
    for thresh in (0.999, 0.98, 0.90, 0.70):
        ys_c, xs_c = np.where(res_norm >= thresh)
        if len(ys_c) > 0:
            break

    if len(ys_c) == 0:
        return results if results else [(margin, search_h - h_m)]

    margin_c = max(0, margin // scale)
    x_limit_c = max(1, (max_width - margin - w_m) // scale)
    valid = (ys_c >= margin_c) & (xs_c >= margin_c) & (xs_c <= x_limit_c)
    ys_c, xs_c = ys_c[valid], xs_c[valid]

    if len(ys_c) == 0:
        return results if results else [(margin, search_h - h_m)]

    order = np.lexsort((xs_c, ys_c))
    # Select distinct coarse points
    coarse_candidates = []
    seen_cells = set()
    for cx, cy in zip(xs_c[order].tolist(), ys_c[order].tolist()):
        cell = (cx // 2, cy // 2)
        if cell in seen_cells:
            continue
        seen_cells.add(cell)
        coarse_candidates.append((cx * scale, cy * scale))
        if len(coarse_candidates) >= 48:
            break

    for bx, by in coarse_candidates:
        if bx + w_m > max_width - margin or by + h_m > search_h:
            continue
        if (bx, by) in seen:
            continue
        seen.add((bx, by))
        if not _collides_fast(occupancy, mask, bx, by, search_h):
            results.append((bx, by))
            if len(results) >= top_k:
                break

    return results if results else [(margin, search_h - h_m)]

# 4. Fast Refine Candidate
def _refine_candidate_fast(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    min_x: int, min_y: int,
    max_occ_y: int,
    max_width: int,
) -> tuple[int, int]:
    step = 8
    for _ in range(4):
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

# 5. Fast Single Pass
def _run_single_pass_fast(
    prepared_items: list[dict],
    max_width: int,
    spacing: int,
    margin: int,
    step: int,
    performance_mode: str,
) -> tuple[list[tuple[Image.Image, int, int]], int, int, int]:
    usable_width = max_width - 2 * margin
    total_alpha_area = sum(p["variants"][0].area for p in prepared_items)
    estimated_height = int(total_alpha_area / max(1, usable_width) * 1.6) + margin * 4
    initial_height = max(64, margin * 2 + 1, estimated_height)
    occupancy = np.zeros((initial_height, max_width), dtype=np.uint8)

    placed: list[PackedPiece] = []
    max_y_used = margin
    stamp_kernel = _build_stamp_kernel(spacing) if spacing > 0 else None
    scale_factor = 16 if performance_mode == "fast" else 8
    candidate_limit = 32 if performance_mode == "fast" else 64
    raster_search = performance_mode != "fast"

    for piece in prepared_items:
        best_choice = None
        max_occ_y = max_y_used + spacing

        for variant in piece["variants"]:
            img = variant.image
            mask = variant.mask
            w, h = img.size
            search_h = max_y_used + spacing + h + step
            occupancy = _ensure_height(occupancy, search_h)

            valid_positions = _find_valid_positions_optimized(
                occupancy=occupancy,
                mask=mask,
                max_width=max_width,
                margin=margin,
                search_h=search_h,
                step=step,
                spacing=spacing,
                scale=scale_factor,
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
                        "image": img, "mask": mask,
                        "x": fx, "y": fy,
                        "score": final_score,
                    }

            if best_choice is not None and best_choice["image"] is img:
                rx, ry = _refine_candidate_fast(
                    occupancy=occupancy,
                    mask=mask,
                    x=best_choice["x"],
                    y=best_choice["y"],
                    min_x=margin,
                    min_y=margin,
                    max_occ_y=max_occ_y + img.height + step,
                    max_width=max_width,
                )
                if (rx, ry) != (best_choice["x"], best_choice["y"]):
                    score = _score_candidate(mask, rx, ry, max_width, margin, max_y_used, variant.area)
                    contact, pocket_bonus = _fast_score_contact(occupancy, rx, ry, w, h, spacing, margin, max_width)
                    angle_penalty = 0 if variant.angle in (0, 90, 270) else 1
                    refined_score = (score[0], score[1], angle_penalty, -pocket_bonus, -contact, score[2], score[3], score[4], score[5])
                    if refined_score < best_choice["score"]:
                        best_choice = {
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
                "image": img, "mask": mask,
                "x": margin, "y": max_y_used + spacing,
                "score": (1, img.height, 0, 0, -fallback.area, margin, max_y_used + spacing),
            }

        img = best_choice["image"]
        mask = best_choice["mask"]
        x = best_choice["x"]
        y = best_choice["y"]

        placed.append(PackedPiece(
            image=img,
            mask=mask,
            x=x,
            y=y,
            w=img.width,
            h=img.height,
            area=int(mask.sum()),
        ))
        _stamp_reserved(occupancy, mask, x, y, spacing, margin, max_width, stamp_kernel)
        max_y_used = max(max_y_used, y + img.height)

    final_height = max_y_used + margin
    total_placed_area = sum(piece.area for piece in placed)
    return [(piece.image, piece.x, piece.y) for piece in placed], max_width, final_height, total_placed_area

def test():
    # Warmup Numba functions
    dummy_occ = np.zeros((100, 100), dtype=np.uint8)
    _fast_score_contact(dummy_occ, 10, 10, 20, 20, 2, 2, 100)

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
    step = 8

    print("Preparando variantes...")
    variants_list = [_prepare_mask_variants(img, max_width - 2*margin, allow_rotate=True, performance_mode="balanced") for img in images]
    prepared_items = [{"variants": v_list} for v_list in variants_list]

    print("Executando Single Pass OTIMIZADO...")
    t0 = time.time()
    res = _run_single_pass_fast(
        prepared_items=prepared_items,
        max_width=max_width,
        spacing=spacing,
        margin=margin,
        step=step,
        performance_mode="balanced",
    )
    t1 = time.time()
    print(f"Resultado: Altura = {res[2]}px, Tempo = {t1-t0:.4f}s")

if __name__ == "__main__":
    test()

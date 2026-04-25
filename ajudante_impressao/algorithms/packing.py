from __future__ import annotations

from typing import List

import numpy as np
from PIL import Image

from .image_ops import fit_width, resize_to_height, trim_empty_borders


def pack_images_gallery(images: List[Image.Image], max_width: int, spacing: int, margin: int, row_height: int, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared: List[Image.Image] = []

    for img in images:
        img = trim_empty_borders(img)
        if allow_rotate and img.height > img.width * 1.8:
            rot = img.rotate(90, expand=True)
            if rot.width <= usable_width:
                img = rot
        img = resize_to_height(img, row_height)
        img = fit_width(img, usable_width)
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
        scale = min(1.18, usable_width / row_total) if row_total > 0 else 1.0

        scaled_row = []
        for im in row_imgs:
            if scale != 1.0:
                new_w = max(1, int(round(im.width * scale)))
                new_h = max(1, int(round(im.height * scale)))
                scaled_row.append(im.resize((new_w, new_h), Image.Resampling.LANCZOS))
            else:
                scaled_row.append(im)

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
        if allow_rotate and img.height > img.width and img.height <= usable_width:
            rotated = img.rotate(90, expand=True)
            if rotated.width <= usable_width and rotated.height < img.height:
                img = rotated
        if img.width > usable_width:
            img = fit_width(img, usable_width)
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


def pack_images_tight(images: List[Image.Image], max_width: int, spacing: int, margin: int, step: int = 8, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared = []

    for img in images:
        variants = [img]
        if allow_rotate:
            rot = img.rotate(90, expand=True)
            if rot.width <= usable_width:
                variants.append(rot)

        normalized_variants = []
        for variant in variants:
            if variant.width > usable_width:
                variant = fit_width(variant, usable_width)
            normalized_variants.append(variant)

        best_variant = max(normalized_variants, key=lambda im: (im.width * im.height, im.width, im.height))
        prepared.append(best_variant)

    prepared.sort(key=lambda im: (im.width * im.height, im.height, im.width), reverse=True)
    profile = np.full(max_width, margin, dtype=np.int32)
    placed = []
    max_y_used = margin
    step = max(1, step)

    for img in prepared:
        w, h = img.size
        x_start = margin
        x_end = max_width - margin - w

        if x_end < x_start:
            img = fit_width(img, usable_width)
            w, h = img.size
            x_end = max_width - margin - w

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

        if best_y is None:
            best_x = margin
            best_y = max_y_used + spacing
            best_bottom = best_y + h

        placed.append((img, best_x, best_y))
        max_y_used = max(max_y_used, best_bottom)

        reserve_start = max(margin, best_x - spacing)
        reserve_end = min(max_width - margin, best_x + w + spacing)
        profile[reserve_start:reserve_end] = max(profile[reserve_start:reserve_end].max(), best_bottom + spacing)

    final_height = max_y_used + margin
    return placed, max_width, final_height


def _alpha_mask(img: Image.Image) -> np.ndarray:
    return np.array(img.getchannel("A"), dtype=np.uint8) > 0


def _quantize(value: int, step: int, minimum: int) -> int:
    if value <= minimum:
        return minimum
    return minimum + ((value - minimum + step - 1) // step) * step


def _prepare_mask_variants(img: Image.Image, usable_width: int, allow_rotate: bool) -> list[dict]:
    img = trim_empty_borders(img)
    angle_candidates = [0]
    if allow_rotate:
        angle_candidates.extend([90, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75])

    variants: list[dict] = []
    seen: set[tuple[int, int, int]] = set()

    for angle in angle_candidates:
        variant = img if angle == 0 else trim_empty_borders(img.rotate(angle, expand=True))
        if variant.width > usable_width:
            variant = fit_width(variant, usable_width)
            variant = trim_empty_borders(variant)
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
    growth = max(min_height, occupancy.shape[0] * 2)
    expanded = np.zeros((growth, occupancy.shape[1]), dtype=bool)
    expanded[: occupancy.shape[0], :] = occupancy
    return expanded


def _collides(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int) -> bool:
    h, w = mask.shape
    if y < 0 or x < 0 or y + h > occupancy.shape[0] or x + w > occupancy.shape[1]:
        return True
    return bool(np.any(occupancy[y:y + h, x:x + w] & mask))


def _stamp_reserved(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, spacing: int, margin: int, max_width: int) -> None:
    h, w = mask.shape
    x0 = max(margin, x - spacing)
    y0 = max(margin, y - spacing)
    x1 = min(max_width - margin, x + w + spacing)
    y1 = y + h + spacing
    if x0 >= x1 or y0 >= y1:
        return

    region_h = y1 - y0
    region_w = x1 - x0
    reserve = np.zeros((region_h, region_w), dtype=bool)
    dest_x0 = x - x0
    dest_y0 = y - y0
    reserve[dest_y0:dest_y0 + h, dest_x0:dest_x0 + w] = mask
    source = reserve.copy()

    if spacing > 0:
        for dy in range(-spacing, spacing + 1):
            for dx in range(-spacing, spacing + 1):
                if abs(dx) + abs(dy) > spacing:
                    continue
                src_y0 = max(0, -dy)
                src_y1 = min(region_h, region_h - dy) if dy >= 0 else region_h
                src_x0 = max(0, -dx)
                src_x1 = min(region_w, region_w - dx) if dx >= 0 else region_w
                dst_y0 = max(0, dy)
                dst_y1 = dst_y0 + (src_y1 - src_y0)
                dst_x0 = max(0, dx)
                dst_x1 = dst_x0 + (src_x1 - src_x0)
                reserve[dst_y0:dst_y1, dst_x0:dst_x1] |= source[src_y0:src_y1, src_x0:src_x1]

    occupancy[y0:y1, x0:x1] |= reserve


def _score_candidate(mask: np.ndarray, x: int, y: int, max_width: int, margin: int, max_y_used: int) -> tuple[int, int, int, int]:
    h, w = mask.shape
    bottom = y + h
    side_gap = min(x - margin, max_width - margin - (x + w))
    box_area = w * h
    local_waste = box_area - int(mask.sum())
    return (max(bottom, max_y_used), bottom, local_waste, -side_gap)


def pack_images_masked(images: List[Image.Image], max_width: int, spacing: int, margin: int, step: int = 8, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared = []
    for img in images:
        variants = _prepare_mask_variants(img, usable_width, allow_rotate)
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
    occupancy = np.zeros((max(64, margin * 2 + 1), max_width), dtype=bool)
    placed = []
    candidates: set[tuple[int, int]] = {(margin, margin)}
    step = max(1, step)
    max_y_used = margin

    for piece in prepared:
        best_choice = None
        ordered_candidates = sorted(candidates, key=lambda point: (point[1], point[0]))

        for x_raw, y_raw in ordered_candidates[:400]:
            x_base = _quantize(x_raw, step, margin)
            y_base = _quantize(y_raw, step, margin)

            for variant in piece["variants"]:
                img = variant["image"]
                mask = variant["mask"]
                w, h = img.size
                if x_base + w > max_width - margin:
                    continue

                occupancy = _ensure_height(occupancy, y_base + h + spacing + margin + step)
                if _collides(occupancy, mask, x_base, y_base):
                    continue

                score = _score_candidate(mask, x_base, y_base, max_width, margin, max_y_used)
                if best_choice is None or score < best_choice["score"]:
                    best_choice = {"image": img, "mask": mask, "x": x_base, "y": y_base, "score": score}

        if best_choice is None:
            placed_successfully = False
            search_limit = max_y_used + max(variant["image"].height for variant in piece["variants"]) + spacing + margin
            y = margin
            while y <= search_limit and not placed_successfully:
                for variant in piece["variants"]:
                    img = variant["image"]
                    mask = variant["mask"]
                    w, h = img.size
                    x = margin
                    while x + w <= max_width - margin:
                        occupancy = _ensure_height(occupancy, y + h + spacing + margin + step)
                        if not _collides(occupancy, mask, x, y):
                            score = _score_candidate(mask, x, y, max_width, margin, max_y_used)
                            best_choice = {"image": img, "mask": mask, "x": x, "y": y, "score": score}
                            placed_successfully = True
                            break
                        x += step
                    if placed_successfully:
                        break
                y += step

        if best_choice is None:
            fallback = piece["variants"][0]
            img = fallback["image"]
            mask = fallback["mask"]
            x = margin
            y = _quantize(max_y_used + spacing, step, margin)
            occupancy = _ensure_height(occupancy, y + img.height + spacing + margin + step)
            while _collides(occupancy, mask, x, y):
                y += step
                occupancy = _ensure_height(occupancy, y + img.height + spacing + margin + step)
            best_choice = {"image": img, "mask": mask, "x": x, "y": y, "score": _score_candidate(mask, x, y, max_width, margin, max_y_used)}

        img = best_choice["image"]
        mask = best_choice["mask"]
        x = best_choice["x"]
        y = best_choice["y"]
        placed.append((img, x, y))
        _stamp_reserved(occupancy, mask, x, y, spacing, margin, max_width)
        max_y_used = max(max_y_used, y + img.height)

        candidates.discard((x, y))
        candidates.add((x + img.width + spacing, y))
        candidates.add((x, y + img.height + spacing))
        candidates.add((x + max(1, img.width // 2), y + img.height + spacing))
        candidates = {
            (_quantize(cx, step, margin), _quantize(cy, step, margin))
            for cx, cy in candidates
            if cx < max_width - margin and cy <= max_y_used + 4 * step + spacing + margin
        }

    final_height = max_y_used + margin
    return placed, max_width, final_height


def build_canvas(packed, width, height):
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    for img, x, y in packed:
        canvas.alpha_composite(img, (x, y))
    return canvas

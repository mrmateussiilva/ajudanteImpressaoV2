from __future__ import annotations

from typing import List

import numpy as np
from PIL import Image

from image_utils import fit_width, resize_to_height, trim_empty_borders


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


def build_canvas(packed, width, height):
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    for img, x, y in packed:
        canvas.alpha_composite(img, (x, y))
    return canvas

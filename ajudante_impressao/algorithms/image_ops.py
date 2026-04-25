from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image, ImageOps


VALID_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def cm_to_px(cm: float, dpi: int = 100) -> int:
    return int(round((cm / 2.54) * dpi))


def px_to_cm(px: int, dpi: int = 100) -> float:
    return (px / dpi) * 2.54


def normalize_to_100dpi(img: Image.Image) -> Image.Image:
    dpi = img.info.get("dpi", (100, 100))[0]
    if not dpi or dpi <= 0:
        dpi = 100
    if int(round(dpi)) == 100:
        return img
    scale = 100 / dpi
    new_w = max(1, int(round(img.width * scale)))
    new_h = max(1, int(round(img.height * scale)))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def remove_white(img: Image.Image, threshold: int = 245, softness: int = 18) -> Image.Image:
    img = img.convert("RGBA")
    arr = np.array(img).astype(np.int16)

    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]
    white_level = rgb.min(axis=2)
    fade_start = max(0, threshold - softness)

    mask_full = white_level >= threshold
    mask_fade = (white_level >= fade_start) & (white_level < threshold)
    alpha[mask_full] = 0

    if np.any(mask_fade):
        factor = (threshold - white_level[mask_fade]) / max(1, softness)
        alpha[mask_fade] = (alpha[mask_fade] * factor).astype(np.uint8)

    arr[:, :, 3] = np.clip(alpha, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def crop_transparent(img: Image.Image) -> Image.Image:
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def trim_empty_borders(img: Image.Image) -> Image.Image:
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def resize_to_height(img: Image.Image, target_h: int) -> Image.Image:
    if img.height <= 0:
        return img
    ratio = target_h / img.height
    new_w = max(1, int(round(img.width * ratio)))
    new_h = max(1, int(round(img.height * ratio)))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def fit_width(img: Image.Image, max_width: int) -> Image.Image:
    if img.width <= max_width:
        return img
    ratio = max_width / img.width
    new_w = max(1, int(round(img.width * ratio)))
    new_h = max(1, int(round(img.height * ratio)))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def rgba_to_white_background(img: Image.Image) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    background = Image.new("RGB", img.size, (255, 255, 255))
    background.paste(img, mask=img.getchannel("A"))
    return background


def process_images(
    folder: Path,
    max_width_px: int,
    threshold: int,
    log_fn,
    max_workers: int | None = None,
) -> List[dict]:
    imgs: List[dict] = []
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXT)

    if not files:
        log_fn("⚠  Nenhuma imagem encontrada na pasta.", "warn")
        return []

    cpu_count = max(1, (os.cpu_count() or 1))
    worker_count = min(cpu_count, max_workers or 8)
    log_fn(f"  Processamento paralelo: {worker_count} workers\n", "info")

    def _process_file(file: Path):
        try:
            with Image.open(file) as im:
                im = ImageOps.exif_transpose(im)
                im = normalize_to_100dpi(im)
                im = remove_white(im, threshold=threshold, softness=18)
                im = crop_transparent(im)

                if im.mode != "RGBA":
                    im = im.convert("RGBA")

                if im.width > max_width_px:
                    im = fit_width(im, max_width_px)
                    resize_log = f"  ↔  '{file.name}' redimensionada para caber no rolo."
                else:
                    resize_log = None

                im = crop_transparent(im)
                processed = im.copy()
                image_item = {
                    "name": file.name,
                    "image": processed,
                    "width_px": processed.width,
                    "height_px": processed.height,
                    "width_cm": px_to_cm(processed.width),
                    "height_cm": px_to_cm(processed.height),
                }
                return {
                    "item": image_item,
                    "logs": [*([resize_log] if resize_log else []), f"  ✓  {file.name}  ({im.width}×{im.height}px)"],
                    "levels": [*(["warn"] if resize_log else []), "ok"],
                }
        except Exception as e:
            return {
                "item": None,
                "logs": [f"  ✗  Erro em '{file.name}': {e}"],
                "levels": ["err"],
            }

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(_process_file, files))

    for result in results:
        item = result["item"]
        if item is not None:
            imgs.append(item)
        for message, level in zip(result["logs"], result["levels"]):
            log_fn(f"{message}\n", level)

    log_fn(f"\n  {len(imgs)} imagens carregadas.", "info")
    return imgs

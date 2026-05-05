from __future__ import annotations

import hashlib
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, List

import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageFont


VALID_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def add_label_to_image(img: Image.Image, text: str) -> Image.Image:
    """Adiciona uma margem na parte inferior da imagem e escreve o rótulo nela."""
    # Tamanho da fonte proporcional à altura da imagem
    font_size = max(20, int(img.height * 0.025))
    
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("segoeui.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    # Calcular tamanho do texto
    temp_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_bbox = temp_draw.textbbox((0, 0), text, font=font)
    tw = text_bbox[2] - text_bbox[0]
    th = text_bbox[3] - text_bbox[1]
    
    # Adicionar uma margem inferior (altura do texto + um pouco de respiro)
    padding = th + 20
    new_img = Image.new("RGBA", (img.width, img.height + padding), (0, 0, 0, 0))
    new_img.paste(img, (0, 0))
    
    draw = ImageDraw.Draw(new_img)
    
    # Centralizar o texto na nova margem ou colocar no canto
    # Vamos colocar no canto inferior direito da nova área
    x = new_img.width - tw - 10
    y = img.height + 5
    
    # Fundo do texto para garantir leitura
    draw.rectangle([x - 5, y - 2, x + tw + 5, y + th + 5], fill=(255, 255, 255, 220))
    draw.text((x, y), text, fill=(0, 0, 0, 255), font=font)
    
    return new_img


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


def _process_single_image(file: Path, max_width_px: int, threshold: int) -> dict[str, Any]:
    try:
        with Image.open(file) as im:
            im = ImageOps.exif_transpose(im)
            im = normalize_to_100dpi(im)
            im = remove_white(im, threshold=threshold, softness=18)
            im = crop_transparent(im)

            if im.mode != "RGBA":
                im = im.convert("RGBA")

            if im.width > max_width_px:
                resize_log = f"  ⚠  '{file.name}' ({px_to_cm(im.width):.1f}cm) é mais larga que o rolo ({px_to_cm(max_width_px):.1f}cm)!"
            else:
                resize_log = None

            # Classificação automática baseada no treinamento
            try:
                from .classifier import get_prod_classifier, get_quality_classifier
                
                prod_cls = get_prod_classifier()
                category = prod_cls.classify(im)
                
                quality_cls = get_quality_classifier()
                quality = quality_cls.classify(im)
                
                # Na imagem, escrevemos apenas o tipo (categoria)
                im = add_label_to_image(im, category)
                
                class_log = f"  🏷️  Tipo: {category} | Qualidade: {quality}"
            except Exception as e:
                category = "N/A"
                quality = "N/A"
                class_log = f"  ⚠  Erro na classificação: {e}"

            im = crop_transparent(im)
            processed = im.copy()
            image_item = {
                "name": file.name,
                "category": category,
                "quality": quality,
                "image": processed,
                "width_px": processed.width,
                "height_px": processed.height,
                "width_cm": px_to_cm(processed.width),
                "height_cm": px_to_cm(processed.height),
            }
            return {
                "item": image_item,
                "logs": [*([resize_log] if resize_log else []), class_log, f"  ✓  {file.name}  ({im.width}×{im.height}px)"],
                "levels": [*(["warn"] if resize_log else []), "info", "ok"],
            }
    except Exception as e:
        return {
            "item": None,
            "logs": [f"  ✗  Erro em '{file.name}': {e}"],
            "levels": ["err"],
        }


def _get_cache_key(file: Path, threshold: int) -> str:
    # Gerar um hash baseado no caminho, tamanho, data e threshold
    stats = file.stat()
    data = f"{file.absolute()}|{stats.st_size}|{stats.st_mtime}|{threshold}"
    return hashlib.md5(data.encode()).hexdigest()


def process_images(
    folder: Path,
    max_width_px: int,
    threshold: int,
    log_fn,
    max_workers: int | None = None,
) -> List[dict]:
    cache_dir = folder / ".ajudante_cache"
    cache_dir.mkdir(exist_ok=True)

    imgs: List[dict] = []
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXT)

    if not files:
        log_fn("⚠  Nenhuma imagem encontrada na pasta.", "warn")
        return []

    # Separar arquivos em "Cache" e "Para Processar"
    to_process = []
    for f in files:
        key = _get_cache_key(f, threshold)
        cache_file = cache_dir / f"{key}.png"
        meta_file = cache_dir / f"{key}.json"
        
        if cache_file.exists() and meta_file.exists():
            try:
                import json
                with open(meta_file, "r", encoding="utf-8") as j:
                    meta = json.load(j)
                processed = Image.open(cache_file)
                processed.load() # Garantir que foi lida
                imgs.append({
                    "name": f.name,
                    "image": processed,
                    **meta
                })
                log_fn(f"  ⚡ {f.name} (Cache)\n", "muted")
            except Exception:
                to_process.append(f)
        else:
            to_process.append(f)

    if not to_process:
        log_fn(f"\n  {len(imgs)} imagens carregadas do cache.", "ok")
        return imgs

    cpu_count = max(1, (os.cpu_count() or 1))
    worker_count = min(cpu_count, max_workers or 8)
    log_fn(f"  Processamento multiprocesso: {worker_count} workers ({len(to_process)} novas)\n", "info")

    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        from functools import partial
        worker_fn = partial(_process_single_image, max_width_px=max_width_px, threshold=threshold)
        results = list(executor.map(worker_fn, to_process))

    for f, result in zip(to_process, results):
        item = result["item"]
        if item is not None:
            imgs.append(item)
            # Salvar no cache
            try:
                key = _get_cache_key(f, threshold)
                item["image"].save(cache_dir / f"{key}.png", format="PNG")
                import json
                meta = {k: v for k, v in item.items() if k != "image"}
                with open(cache_dir / f"{key}.json", "w", encoding="utf-8") as j:
                    json.dump(meta, j, ensure_ascii=False)
            except Exception:
                pass

        for message, level in zip(result["logs"], result["levels"]):
            log_fn(f"{message}\n", level)

    log_fn(f"\n  {len(imgs)} imagens carregadas.", "info")
    return imgs

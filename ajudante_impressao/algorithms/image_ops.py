from __future__ import annotations

import hashlib
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, List

import numpy as np
import cv2
import functools
from PIL import Image, ImageOps, ImageDraw, ImageFont


VALID_EXT = {".png", ".jpg", ".jpeg", ".webp"}

_temp_img = Image.new("RGBA", (1, 1))
_temp_draw = ImageDraw.Draw(_temp_img)

@functools.lru_cache(maxsize=16)
def _get_font(font_size: int):
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        try:
            return ImageFont.truetype("segoeui.ttf", font_size)
        except Exception:
            return ImageFont.load_default()


def add_label_to_image(
    img: Image.Image,
    text: str,
    position: str = "external_bottom_right",
    font_pt: int = 30,
    date_str: str = "",
    text_color: tuple[int, int, int, int] = (0, 0, 0, 255),
) -> Image.Image:
    """Adiciona um rótulo de tipo de produção à imagem, em modo externo (com margem de
    exatamente 1cm) ou sobreposto (overlay).

    Parâmetros:
        font_pt    -- tamanho da fonte em pontos (padrão 30pt)
        date_str   -- data de envio opcional; se fornecida, é exibida em uma segunda linha
        text_color -- cor RGBA do texto (padrão preto); o fundo do box é sempre branco
    """
    label_lines = [text]
    if date_str.strip():
        label_lines.append(f"Envio: {date_str.strip()}")
    full_text = "\n".join(label_lines)

    if position.startswith("external_"):
        font_size = font_pt
    else:
        font_size = max(font_pt, int(img.height * 0.03))

    font = _get_font(font_size)

    text_bbox = _temp_draw.textbbox((0, 0), full_text, font=font)
    tw = text_bbox[2] - text_bbox[0]
    th = text_bbox[3] - text_bbox[1]

    if position.startswith("external_"):
        padding_h = cm_to_px(1.0)
        if date_str.strip():
            padding_h = max(padding_h, th + 20)
        new_img = ImageOps.expand(img, border=(0, 0, 0, padding_h), fill=(0, 0, 0, 0))
        y = img.height + (padding_h - th) // 2

        if position == "external_bottom_right":
            x = new_img.width - tw - 15
        elif position == "external_bottom_left":
            x = 15
        else:
            x = (new_img.width - tw) // 2

    else:
        new_img = img.copy()
        margin_offset = 12
        if position == "overlay_bottom_right":
            x = new_img.width - tw - margin_offset
            y = new_img.height - th - margin_offset
        elif position == "overlay_bottom_left":
            x = margin_offset
            y = new_img.height - th - margin_offset
        elif position == "overlay_top_right":
            x = new_img.width - tw - margin_offset
            y = margin_offset
        elif position == "overlay_top_left":
            x = margin_offset
            y = margin_offset
        else:
            x = new_img.width - tw - margin_offset
            y = new_img.height - th - margin_offset

    draw = ImageDraw.Draw(new_img)
    draw.rectangle([x - 8, y - 5, x + tw + 8, y + th + 8], fill=(255, 255, 255, 255))
    draw.text((x, y), full_text, fill=text_color, font=font)

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


def remove_background(img: Image.Image, threshold: int = 245, softness: int = 18) -> Image.Image:
    """Remove fundo claro conectado às bordas, preservando branco interno da arte."""
    img = img.convert("RGBA")
    arr = np.array(img)

    rgb = arr[:, :, :3].astype(np.int16)
    alpha = arr[:, :, 3].astype(np.float32)

    white_tolerance = max(1, 255 - threshold)
    distance_to_white = np.max(np.abs(255 - rgb), axis=2)
    light_enough = distance_to_white <= white_tolerance

    candidate_bg = (light_enough & (alpha > 0)).astype(np.uint8) * 255
    flood = cv2.copyMakeBorder(candidate_bg, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
    flood_mask = np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 128)
    connected_bg = flood[1:-1, 1:-1] == 128

    alpha[connected_bg] = 0

    if softness > 0 and np.any(connected_bg):
        foreground = (~connected_bg).astype(np.uint8)
        dist_from_bg = cv2.distanceTransform(foreground, cv2.DIST_L2, 3)
        fade_zone = (~connected_bg) & light_enough & (dist_from_bg > 0) & (dist_from_bg < softness)
        if np.any(fade_zone):
            factor = np.clip(dist_from_bg[fade_zone] / max(1, softness), 0.0, 1.0)
            alpha[fade_zone] *= factor

    arr[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def crop_transparent(img: Image.Image) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = np.array(img.getchannel("A"), dtype=np.uint8)
    non_zero = cv2.findNonZero(alpha)
    if non_zero is None:
        return img
    x, y, w, h = cv2.boundingRect(non_zero)
    return img.crop((x, y, x + w, y + h))


def trim_empty_borders(img: Image.Image) -> Image.Image:
    return crop_transparent(img)


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
            im = remove_background(im, threshold=threshold, softness=18)
            im = crop_transparent(im)

            if im.mode != "RGBA":
                im = im.convert("RGBA")

            if im.width > max_width_px:
                resize_log = f"  ⚠  '{file.name}' ({px_to_cm(im.width):.1f}cm) é mais larga que o rolo ({px_to_cm(max_width_px):.1f}cm)!"
            else:
                resize_log = None

            im = crop_transparent(im)

            # Classificação automática enriquecida baseada em IA e regras de contexto
            try:
                from .classifier import get_prod_classifier, get_quality_classifier

                prod_cls = get_prod_classifier()
                prod_res = prod_cls.classify_with_details(im, filename=file.name)
                category = prod_res.category
                category_conf = prod_res.confidence_pct
                category_alts = prod_res.alternatives

                quality_cls = get_quality_classifier()
                quality_res = quality_cls.classify_with_details(im, filename=file.name)
                quality = quality_res.category
                quality_conf = quality_res.confidence_pct

                rule_tag = f" 📌[{prod_res.rule_matched}]" if prod_res.rule_matched else ""
                class_log = (
                    f"  🏷️ Tipo: {category} ({category_conf:.0f}%){rule_tag} | "
                    f"★ Qualidade: {quality.upper()} ({quality_conf:.0f}%)"
                )
            except Exception as e:
                category = "N/A"
                category_conf = 0.0
                category_alts = []
                quality = "N/A"
                quality_conf = 0.0
                prod_res = None
                class_log = f"  ⚠  Erro na classificação: {e}"

            processed = im.copy()
            thumb = processed.copy()
            thumb.thumbnail((200, 200), Image.Resampling.BILINEAR)
            image_item = {
                "name": file.name,
                "category": category,
                "category_confidence": category_conf,
                "category_alternatives": category_alts,
                "quality": quality,
                "quality_confidence": quality_conf,
                "features_summary": prod_res.details if prod_res else {},
                "image": processed,
                "thumbnail": thumb,
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
    # Gerar um hash baseado no caminho, tamanho, data e threshold (v3 - fundo por flood fill)
    stats = file.stat()
    data = f"v3|{file.absolute()}|{stats.st_size}|{stats.st_mtime}|{threshold}"
    return hashlib.md5(data.encode()).hexdigest()


def update_image_cache_meta(folder: Path, filename: str, threshold: int, metadata_updates: dict) -> None:
    file = folder / filename
    if not file.exists():
        return
    try:
        key = _get_cache_key(file, threshold)
        cache_dir = folder / ".ajudante_cache"
        meta_file = cache_dir / f"{key}.json"
        if meta_file.exists():
            import json
            with open(meta_file, "r", encoding="utf-8") as j:
                meta = json.load(j)
            meta.update(metadata_updates)
            with open(meta_file, "w", encoding="utf-8") as j:
                json.dump(meta, j, ensure_ascii=False)
    except Exception:
        pass


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
    cached_count = 0
    for f in files:
        key = _get_cache_key(f, threshold)
        cache_file = cache_dir / f"{key}.png"
        meta_file = cache_dir / f"{key}.json"
        thumb_file = cache_dir / f"{key}_thumb.png"

        if cache_file.exists() and meta_file.exists():
            try:
                import json
                with open(meta_file, "r", encoding="utf-8") as j:
                    meta = json.load(j)
                processed = Image.open(cache_file)
                processed.load()

                if "width_px" in meta and (meta["width_px"] != processed.width or meta["height_px"] != processed.height):
                    processed = processed.resize((meta["width_px"], meta["height_px"]), Image.Resampling.LANCZOS)

                if thumb_file.exists():
                    thumb = Image.open(thumb_file)
                    thumb.load()
                else:
                    thumb = processed.copy()
                    thumb.thumbnail((200, 200), Image.Resampling.BILINEAR)

                imgs.append({
                    "name": f.name,
                    "image": processed,
                    "thumbnail": thumb,
                    **meta
                })
                cached_count += 1
            except Exception:
                to_process.append(f)
        else:
            to_process.append(f)

    if cached_count > 0:
        log_fn(f"  ⚡ {cached_count} imagens carregadas instantaneamente do cache em disco.\n", "ok")

    if not to_process:
        return imgs

    cpu_count = max(1, (os.cpu_count() or 1))
    worker_count = min(cpu_count, max_workers or 8)
    log_fn(f"  Processamento multithread: {worker_count} workers ({len(to_process)} novas)\n", "info")

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        from functools import partial
        worker_fn = partial(_process_single_image, max_width_px=max_width_px, threshold=threshold)
        results = list(executor.map(worker_fn, to_process))

    for f, result in zip(to_process, results):
        item = result["item"]
        if item is not None:
            imgs.append(item)
            try:
                key = _get_cache_key(f, threshold)
                item["image"].save(cache_dir / f"{key}.png", format="PNG")
                if "thumbnail" in item:
                    item["thumbnail"].save(cache_dir / f"{key}_thumb.png", format="PNG")
                import json
                meta = {k: v for k, v in item.items() if k not in ("image", "thumbnail")}
                with open(cache_dir / f"{key}.json", "w", encoding="utf-8") as j:
                    json.dump(meta, j, ensure_ascii=False)
            except Exception:
                pass
        for log_msg, level in zip(result["logs"], result["levels"]):
            log_fn(log_msg + "\n", level)

    log_fn(f"\n  {len(imgs)} imagens carregadas.", "info")
    return imgs

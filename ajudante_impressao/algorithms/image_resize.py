from __future__ import annotations

from pathlib import Path

from PIL import Image

from .image_ops import VALID_EXT, cm_to_px


def resolve_resize_scale(img: Image.Image, mode: str, target_value: float) -> float:
    if mode == "percent":
        return target_value / 100.0
    if mode == "width_px":
        return target_value / img.width
    dpi = img.info.get("dpi", (72, 72))[0]
    if not dpi or dpi <= 0:
        dpi = 72
    target_px = cm_to_px(target_value, dpi=int(round(dpi)))
    return target_px / img.width


def resize_image_file(file: Path, mode: str, target_value: float, output_name: str, destination_mode: str):
    with Image.open(file) as img:
        scale = resolve_resize_scale(img, mode, target_value)
        new_width = max(1, int(round(img.width * scale)))
        new_height = max(1, int(round(img.height * scale)))
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        output_dir = file.parent if destination_mode == "overwrite" else file.parent / output_name
        if destination_mode != "overwrite":
            output_dir.mkdir(exist_ok=True)
        save_path = output_dir / file.name

        save_kwargs = {}
        dpi = img.info.get("dpi")
        if dpi:
            save_kwargs["dpi"] = dpi
        if "icc_profile" in img.info:
            save_kwargs["icc_profile"] = img.info["icc_profile"]

        resized.save(save_path, **save_kwargs)
        return {"file": file.name, "width": new_width, "height": new_height, "scale": scale, "save_path": save_path}


def process_resize_folder(folder: Path, mode: str, target_value: float, output_name: str, destination_mode: str):
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXT)
    if not files:
        raise ValueError("Nenhuma imagem compativel encontrada na pasta.")
    return [resize_image_file(file, mode, target_value, output_name, destination_mode) for file in files]

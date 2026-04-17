from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from image_utils import VALID_EXT, cm_to_px, px_to_cm


def extract_client_name(filename: str) -> str:
    stem = Path(filename).stem.strip()
    if "-" in stem:
        client = stem.split("-", 1)[0].strip()
        if client:
            return client
    parts = stem.split()
    return parts[0].strip() if parts else stem


def resolve_image_dpi(image: Image.Image, dpi_override: int | None = None) -> tuple[int, int]:
    if dpi_override and dpi_override > 0:
        return (dpi_override, dpi_override)
    dpi = image.info.get("dpi", (72, 72))
    dpi_x = int(round(dpi[0])) if dpi and dpi[0] and dpi[0] > 0 else 72
    dpi_y = int(round(dpi[1])) if len(dpi) > 1 and dpi[1] and dpi[1] > 0 else dpi_x
    return (dpi_x, dpi_y)


def determine_pad_cm(image: Image.Image, dpi_override: int | None = None) -> float:
    dpi_x, dpi_y = resolve_image_dpi(image, dpi_override)
    width_cm = px_to_cm(image.width, dpi=dpi_x)
    height_cm = px_to_cm(image.height, dpi=dpi_y)
    rounded_width = round(width_cm)
    rounded_height = round(height_cm)

    if rounded_width == 155 and rounded_height == 155:
        return 2.0
    if rounded_width in {157, 158} and rounded_height in {157, 158}:
        return 1.0
    return 1.0


def determine_pad_side(image: Image.Image, dpi_override: int | None = None, side_mode: str = "auto") -> str:
    if side_mode in {"bottom", "right"}:
        return side_mode

    dpi_x, dpi_y = resolve_image_dpi(image, dpi_override)
    width_cm = px_to_cm(image.width, dpi=dpi_x)
    height_cm = px_to_cm(image.height, dpi=dpi_y)

    if width_cm >= height_cm:
        return "bottom"
    return "right"


def add_contour(image: Image.Image) -> Image.Image:
    return ImageOps.expand(image, border=1, fill="black")


def _load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=max(12, font_size))
    except OSError:
        return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int, base_size: int):
    font_size = max(12, base_size)
    while font_size >= 12:
        font = _load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        if text_width <= max_width and text_height <= max_height:
            return font, text_width, text_height
        font_size -= 2
    font = _load_font(12)
    bbox = draw.textbbox((0, 0), text, font=font)
    return font, bbox[2] - bbox[0], bbox[3] - bbox[1]


def apply_finishing_to_image(image: Image.Image, file_name: str, dpi_override: int | None = None, side_mode: str = "auto") -> tuple[Image.Image, dict]:
    dpi_x, dpi_y = resolve_image_dpi(image, dpi_override)
    pad_cm = determine_pad_cm(image, dpi_override)
    pad_side = determine_pad_side(image, dpi_override, side_mode=side_mode)
    client_name = extract_client_name(file_name)

    bordered = add_contour(image.convert("RGBA"))
    pad_x = cm_to_px(pad_cm, dpi=dpi_x)
    pad_y = cm_to_px(pad_cm, dpi=dpi_y)

    if pad_side == "right":
        final = Image.new("RGBA", (bordered.width + pad_x, bordered.height), "white")
        final.paste(bordered, (0, 0), bordered if bordered.mode == "RGBA" else None)
        text_area = (bordered.width, 0, final.width, final.height)
    else:
        final = Image.new("RGBA", (bordered.width, bordered.height + pad_y), "white")
        final.paste(bordered, (0, 0), bordered if bordered.mode == "RGBA" else None)
        text_area = (0, bordered.height, final.width, final.height)

    draw = ImageDraw.Draw(final)
    text_x0, text_y0, text_x1, text_y1 = text_area
    text_width_limit = max(20, (text_x1 - text_x0) - 12)
    text_height_limit = max(20, (text_y1 - text_y0) - 8)
    base_size = int(round(max(dpi_x, dpi_y) * 0.24))
    font, text_width, text_height = _fit_text(draw, client_name, text_width_limit, text_height_limit, base_size)
    text_x = text_x0 + max(6, ((text_x1 - text_x0) - text_width) // 2)
    text_y = text_y0 + max(4, ((text_y1 - text_y0) - text_height) // 2)
    draw.text((text_x, text_y), client_name, fill="black", font=font)

    metadata = {
        "client_name": client_name,
        "pad_cm": pad_cm,
        "pad_side": pad_side,
        "dpi": (dpi_x, dpi_y),
    }
    return final, metadata


def finish_image_file(file: Path, output_name: str, dpi_override: int | None = None, side_mode: str = "auto"):
    with Image.open(file) as image:
        processed, metadata = apply_finishing_to_image(
            image=image,
            file_name=file.name,
            dpi_override=dpi_override,
            side_mode=side_mode,
        )
        output_dir = file.parent / output_name
        output_dir.mkdir(exist_ok=True)
        save_path = output_dir / file.name

        save_kwargs = {"dpi": metadata["dpi"]}
        if "icc_profile" in image.info:
            save_kwargs["icc_profile"] = image.info["icc_profile"]

        image_to_save = processed
        if file.suffix.lower() in {".jpg", ".jpeg"}:
            background = Image.new("RGB", processed.size, "white")
            background.paste(processed, mask=processed.getchannel("A"))
            image_to_save = background

        image_to_save.save(save_path, **save_kwargs)
        return {
            "file": file.name,
            "save_path": save_path,
            "client_name": metadata["client_name"],
            "pad_cm": metadata["pad_cm"],
            "pad_side": metadata["pad_side"],
        }


def process_finishing_folder(folder: Path, output_name: str, dpi_override: int | None = None, side_mode: str = "auto"):
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXT)
    if not files:
        raise ValueError("Nenhuma imagem compativel encontrada na pasta.")
    return [finish_image_file(file, output_name, dpi_override=dpi_override, side_mode=side_mode) for file in files]

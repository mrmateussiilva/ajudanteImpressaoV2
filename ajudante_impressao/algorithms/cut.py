from __future__ import annotations

import gc
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .image_ops import VALID_EXT, cm_to_px, px_to_cm


Image.MAX_IMAGE_PIXELS = None


def add_contour(image, origin=(None, None)):
    image = image.crop((1, 1, origin[0], origin[1]))
    image = ImageOps.expand(image, border=1, fill="black")
    return image


def add_template_and_number(image, number, pad_cm, name_file, template, plate="start", origin=(0, 0), dpi=(None, None)):
    size_template = template.size
    template_dpi = template.info.get("dpi", (72, 72))
    new_width = math.ceil((size_template[0] * dpi[0]) / template_dpi[0])
    new_height = math.ceil((size_template[1] * dpi[1]) / template_dpi[1])
    template_new = template.resize((new_width, new_height))

    draw = ImageDraw.Draw(image)
    font_size = math.ceil(30 * (dpi[0] / 72))

    if plate == "start":
        image.paste(template_new, origin)
        num_str = f"{number}" if number >= 10 else f"0{number}"
        draw.text((image.size[0] - math.ceil(((2 * pad_cm) * dpi[0]) / 2.54), 0), num_str, fill="black", font_size=font_size)
        draw.text((math.ceil((pad_cm * dpi[0]) / 2.54), image.size[1] - math.ceil((pad_cm * dpi[0]) / 2.54)), name_file, fill="black", font_size=font_size)
    elif plate == "middle":
        image.paste(template_new, (0, 0))
        image.paste(template_new, origin)
        num_str1 = f"{number}" if number >= 10 else f"0{number}"
        num_str2 = f"{number + 1}" if (number + 1) >= 10 else f"0{number + 1}"
        draw.text((math.ceil((pad_cm * dpi[0]) / 2.54), 0), num_str1, fill="black", font_size=font_size)
        draw.text((image.size[0] - math.ceil(((2 * pad_cm) * dpi[0]) / 2.54), 0), num_str2, fill="black", font_size=font_size)
        draw.text((math.ceil((pad_cm * dpi[0]) / 2.54), image.size[1] - math.ceil((pad_cm * dpi[0]) / 2.54)), name_file, fill="black", font_size=font_size)
    else:
        image.paste(template_new, (0, 0))
        num_str = f"{number}" if number >= 10 else f"0{number}"
        draw.text((math.ceil((pad_cm * dpi[0]) / 2.54), 0), num_str, fill="black", font_size=font_size)
        draw.text((math.ceil((pad_cm * dpi[0]) / 2.54), image.size[1] - math.ceil((pad_cm * dpi[0]) / 2.54)), name_file, fill="black", font_size=font_size)


def process_cut_images(
    original_image,
    template_image,
    image_path: str,
    real_cut_points: list[int],
    pad_cm: float,
    dpi_override: int | None = None,
):
    output_dir = Path(image_path).parent / "PAINEL_CUT"
    output_dir.mkdir(exist_ok=True)

    icc_profile = original_image.info.get("icc_profile")
    dpi_original = original_image.info.get("dpi", (72, 72))
    if dpi_override and dpi_override > 0:
        dpi_original = (dpi_override, dpi_override)
    name_file = os.path.basename(image_path)

    for i in range(len(real_cut_points) - 1):
        x_start = real_cut_points[i]
        x_end = real_cut_points[i + 1]
        plate_number = i + 1

        if i == 0:
            plate_type = "start"
        elif i == len(real_cut_points) - 2:
            plate_type = "end"
            plate_number = (2 * (i + 1)) - 2
        else:
            plate_type = "middle"
            plate_number = (2 * (i + 1)) - 2

        plate_img = original_image.crop((x_start, 0, x_end, original_image.height))
        plate_img = add_contour(plate_img, (plate_img.size[0] - 1, original_image.height - 1))

        border_px = math.ceil((pad_cm * dpi_original[0]) / 2.54)
        plate_img = ImageOps.expand(plate_img, border=border_px, fill="white")

        origin_x = plate_img.size[0] - math.ceil((pad_cm * dpi_original[0]) / 2.54)
        add_template_and_number(
            image=plate_img,
            number=plate_number,
            pad_cm=pad_cm,
            name_file=name_file,
            template=template_image,
            plate=plate_type,
            origin=(origin_x, 0),
            dpi=dpi_original,
        )

        save_path = output_dir / name_file.replace(".", f" - P0{i + 1}.")
        plate_img.save(str(save_path), dpi=dpi_original, icc_profile=icc_profile)

        del plate_img
        gc.collect()

    return output_dir, len(real_cut_points) - 1


def resolve_image_dpi(image, dpi_override: int | None = None):
    dpi = image.info.get("dpi", (72, 72))
    if dpi_override and dpi_override > 0:
        return (dpi_override, dpi_override)
    if not dpi or dpi[0] <= 0:
        return (72, 72)
    return dpi


def build_cut_points_from_plate_width(image, plate_width_cm: float, dpi_override: int | None = None):
    dpi_x = resolve_image_dpi(image, dpi_override)[0]
    image_width_cm = px_to_cm(image.width, dpi=dpi_x)
    if plate_width_cm <= 0:
        raise ValueError("A largura da placa deve ser maior que zero.")
    if plate_width_cm > image_width_cm:
        raise ValueError(
            f"A placa tem {plate_width_cm:.1f} cm, mas a imagem tem {image_width_cm:.1f} cm de largura."
        )

    positions = []
    cumulative = plate_width_cm
    while cumulative < image_width_cm:
        positions.append(cm_to_px(cumulative, dpi=dpi_x))
        cumulative += plate_width_cm

    cut_points = sorted({max(1, min(pos, image.width - 1)) for pos in positions})
    return [0, *cut_points, image.width]


def process_cut_folder(folder_path: str, template_image, plate_width_cm: float, pad_cm: float, dpi_override: int | None = None):
    folder = Path(folder_path)
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXT)
    if not files:
        raise ValueError("Nenhuma imagem compativel encontrada na pasta.")

    results = []
    for file in files:
        with Image.open(file) as image:
            cut_points = build_cut_points_from_plate_width(image, plate_width_cm, dpi_override=dpi_override)
            output_dir, total_parts = process_cut_images(
                original_image=image.copy(),
                template_image=template_image,
                image_path=str(file),
                real_cut_points=cut_points,
                pad_cm=pad_cm,
                dpi_override=dpi_override,
            )
        results.append({"file": file.name, "parts": total_parts, "output_dir": output_dir})
    return results

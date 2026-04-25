from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from ..algorithms.cut import build_cut_points_from_plate_width, process_cut_folder, process_cut_images
from ..algorithms.image_ops import px_to_cm


LogCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]


@dataclass(slots=True)
class CutManualRequest:
    original_image: Image.Image
    template_image: Image.Image
    image_path: str
    plate_width_cm: float
    pad_cm: float
    dpi_override: int | None = None


@dataclass(slots=True)
class CutManualResult:
    output_dir: Path
    total_parts: int
    cut_points: list[int]


@dataclass(slots=True)
class CutBatchRequest:
    folder_path: str
    template_image: Image.Image
    plate_width_cm: float
    pad_cm: float
    dpi_override: int | None = None


def resolve_dpi(image: Image.Image, dpi_override: int | None = None) -> int:
    if dpi_override and dpi_override > 0:
        return dpi_override
    dpi = image.info.get("dpi", (72, 72))[0]
    if not dpi or dpi <= 0:
        return 72
    return int(round(dpi))


def image_dimensions_cm(image: Image.Image, dpi_override: int | None = None) -> tuple[float, float]:
    dpi_x = resolve_dpi(image, dpi_override)
    return (
        px_to_cm(image.width, dpi=dpi_x),
        px_to_cm(image.height, dpi=dpi_x),
    )


def run_manual_cut(request: CutManualRequest, status_fn: StatusCallback | None = None) -> CutManualResult:
    if status_fn is not None:
        status_fn("Calculando cortes...")
    cut_points = build_cut_points_from_plate_width(
        request.original_image,
        request.plate_width_cm,
        dpi_override=request.dpi_override,
    )

    if status_fn is not None:
        status_fn("Gerando arquivos cortados...")
    output_dir, total_parts = process_cut_images(
        original_image=request.original_image,
        template_image=request.template_image,
        image_path=request.image_path,
        real_cut_points=cut_points,
        pad_cm=request.pad_cm,
        dpi_override=request.dpi_override,
    )
    return CutManualResult(output_dir=output_dir, total_parts=total_parts, cut_points=cut_points)


def run_batch_cut(
    request: CutBatchRequest,
    log_fn: LogCallback | None = None,
    status_fn: StatusCallback | None = None,
):
    if log_fn is not None:
        log_fn("Iniciando processamento em lote...")
    if status_fn is not None:
        status_fn("Processando lote...")
    results = process_cut_folder(
        folder_path=request.folder_path,
        template_image=request.template_image,
        plate_width_cm=request.plate_width_cm,
        pad_cm=request.pad_cm,
        dpi_override=request.dpi_override,
    )
    if log_fn is not None:
        log_fn(f"{len(results)} arquivo(s) processado(s).")
        for result in results:
            log_fn(f"OK {result['file']} -> {result['parts']} partes")
    if status_fn is not None:
        status_fn("Lote concluido.")
    return results

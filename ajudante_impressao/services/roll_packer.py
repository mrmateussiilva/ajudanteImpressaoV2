from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from ..algorithms.image_ops import cm_to_px, process_images, rgba_to_white_background
from ..algorithms.packing import build_canvas, pack_images_fast, pack_images_gallery, pack_images_masked, pack_images_tight


PERFORMANCE_PROFILES = {
    "quality": {"label": "Qualidade", "step_multiplier": 0.75, "max_workers": 4, "debug_limit": 0, "jpeg_quality": 95},
    "balanced": {"label": "Balanceado", "step_multiplier": 1.0, "max_workers": 6, "debug_limit": 24, "jpeg_quality": 92},
    "fast": {"label": "Rapido", "step_multiplier": 2.0, "max_workers": 8, "debug_limit": 12, "jpeg_quality": 88},
}


LogCallback = Callable[[str, str], None]
StatusCallback = Callable[[str], None]
DebugCallback = Callable[[list[dict], int], None]


@dataclass(slots=True)
class RollerPackRequest:
    folder: Path
    largura_cm: float
    margem_cm: float
    espaco_cm: float
    threshold: int
    step_px: int
    allow_rotate: bool
    packing_mode: str
    row_height_cm: float
    output_name: str
    performance_mode: str


@dataclass(slots=True)
class RollerPackResult:
    output_path: Path
    packed_count: int
    final_width_px: int
    final_height_px: int
    final_image: Image.Image
    final_jpeg: Image.Image
    image_items: list[dict]


def run_roll_packer(
    request: RollerPackRequest,
    log_fn: LogCallback,
    status_fn: StatusCallback,
    debug_fn: DebugCallback | None = None,
) -> RollerPackResult | None:
    profile = PERFORMANCE_PROFILES.get(request.performance_mode, PERFORMANCE_PROFILES["balanced"])
    roll_px = cm_to_px(request.largura_cm)
    spacing_px = cm_to_px(request.espaco_cm)
    margin_px = cm_to_px(request.margem_cm)
    row_height_px = cm_to_px(request.row_height_cm)
    usable_width = max(1, roll_px - 2 * margin_px)
    effective_step = max(1, int(round(max(1, request.step_px) * profile["step_multiplier"])))

    log_fn(f"{'─' * 58}\n", "muted")
    log_fn(f"  Rolo: {request.largura_cm}cm = {roll_px}px\n", "info")
    log_fn(f"  Margem: {request.margem_cm}cm = {margin_px}px\n", "info")
    log_fn(f"  Espacamento: {request.espaco_cm}cm = {spacing_px}px\n", "info")
    log_fn(f"  Altura base do mosaico: {request.row_height_cm}cm = {row_height_px}px\n", "info")
    log_fn(f"  Area util: {usable_width}px\n", "info")
    log_fn(f"  Threshold: {request.threshold}\n", "info")
    log_fn(f"  Perfil: {profile['label']}\n", "info")
    log_fn(f"  Step encaixe: {effective_step}px\n", "info")
    log_fn(f"  Rotacao automatica: {'SIM' if request.allow_rotate else 'NAO'}\n", "info")
    log_fn(f"  Modo: {request.packing_mode}\n", "info")
    log_fn(f"{'─' * 58}\n\n", "muted")

    status_fn("Processando imagens...")
    image_items = process_images(request.folder, usable_width, request.threshold, log_fn, max_workers=profile["max_workers"])
    if not image_items:
        return None

    if debug_fn is not None:
        debug_fn(image_items, profile["debug_limit"])

    images = [item["image"] for item in image_items]
    status_fn("Calculando layout...")

    if request.packing_mode == "gallery":
        log_fn("\nGerando mosaico horizontal por linhas...\n", "info")
        packed, final_w, final_h = pack_images_gallery(
            images=images,
            max_width=roll_px,
            spacing=spacing_px,
            margin=margin_px,
            row_height=max(30, row_height_px),
            allow_rotate=request.allow_rotate,
        )
    elif request.packing_mode == "fast":
        log_fn("\nCalculando layout rapido...\n", "info")
        packed, final_w, final_h = pack_images_fast(
            images=images,
            max_width=roll_px,
            spacing=spacing_px,
            margin=margin_px,
            allow_rotate=request.allow_rotate,
        )
    elif request.packing_mode == "masked":
        log_fn("\nCalculando layout poligonal por mascara alfa...\n", "info")
        packed, final_w, final_h = pack_images_masked(
            images=images,
            max_width=roll_px,
            spacing=spacing_px,
            margin=margin_px,
            step=effective_step,
            allow_rotate=request.allow_rotate,
        )
    else:
        log_fn("\nCalculando layout compacto...\n", "info")
        packed, final_w, final_h = pack_images_tight(
            images=images,
            max_width=roll_px,
            spacing=spacing_px,
            margin=margin_px,
            step=effective_step,
            allow_rotate=request.allow_rotate,
        )

    log_fn(
        f"  Canvas final: {final_w}×{final_h}px  ({final_w / 100 * 2.54:.1f}cm × {final_h / 100 * 2.54:.1f}cm)\n",
        "info",
    )

    status_fn("Gerando imagem final...")
    log_fn("\nGerando imagem final...\n", "info")
    final = build_canvas(packed, final_w, final_h)
    final_jpeg = rgba_to_white_background(final)

    output_path = request.folder / request.output_name
    final_jpeg.save(str(output_path), format="JPEG", dpi=(100, 100), quality=profile["jpeg_quality"])

    log_fn(f"\nSalvo em:\n    {output_path}\n", "ok")
    log_fn(f"    {len(packed)} imagens posicionadas.\n", "ok")
    log_fn(f"\n{'─' * 58}\n", "muted")

    return RollerPackResult(
        output_path=output_path,
        packed_count=len(packed),
        final_width_px=final_w,
        final_height_px=final_h,
        final_image=final,
        final_jpeg=final_jpeg,
        image_items=image_items,
    )

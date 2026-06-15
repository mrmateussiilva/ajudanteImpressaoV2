from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # Permitir processar imagens muito grandes

from ..algorithms.image_ops import add_label_to_image, cm_to_px, process_images, rgba_to_white_background
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
    label_position: str
    label_date: str = ""                          # Data de envio (opcional)
    label_text_color: tuple[int, int, int, int] = (0, 0, 0, 255)  # Cor do texto RGBA


@dataclass(slots=True)
class RollerPackResult:
    output_path: Path
    output_paths: list[Path]
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
    image_items: list[dict] | None = None,
) -> RollerPackResult | None:
    profile = PERFORMANCE_PROFILES.get(request.performance_mode, PERFORMANCE_PROFILES["balanced"])
    roll_px = cm_to_px(request.largura_cm)
    spacing_px = cm_to_px(request.espaco_cm)
    margin_px = cm_to_px(request.margem_cm)
    row_height_px = cm_to_px(request.row_height_cm)
    usable_width = max(1, roll_px - 2 * margin_px)
    effective_step = max(1, int(round(max(1, request.step_px) * profile["step_multiplier"])))

    from ..algorithms.packing import HAS_NUMBA
    perf_msg = " [TURBO MODE: Numba Ativo]" if HAS_NUMBA else " [MODO LENTO: Numba não detectado]"
    
    log_fn(f"{'─' * 58}\n", "muted")
    log_fn(f"  {perf_msg}\n", "ok" if HAS_NUMBA else "warn")
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

    if image_items is None:
        status_fn("Processando imagens...")
        image_items = process_images(request.folder, usable_width, request.threshold, log_fn, max_workers=profile["max_workers"])
        if not image_items:
            return None
    else:
        log_fn(f"Usando {len(image_items)} imagens pré-carregadas da interface.\n", "info")

    if debug_fn is not None:
        debug_fn(image_items, profile["debug_limit"])

    # Aplicar rótulos dinâmicos de categoria nas imagens limpas antes de passar para o packer
    from concurrent.futures import ThreadPoolExecutor
    from functools import partial

    _label_fn = partial(
        add_label_to_image,
        position=request.label_position,
        date_str=request.label_date,
        text_color=request.label_text_color,
    )
    worker_count = min(len(image_items), profile["max_workers"])
    with ThreadPoolExecutor(max_workers=worker_count) as ex:
        images = list(ex.map(
            lambda it: _label_fn(it["image"], it.get("category", "N/A")),
            image_items
        ))

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
        
        def progress_callback(current, total):
            if current % 5 == 0 or current == total:
                log_fn(f"    Encaixando imagem {current} de {total}...\n", "muted")

        packed, final_w, final_h = pack_images_masked(
            images=images,
            max_width=roll_px,
            spacing=spacing_px,
            margin=margin_px,
            step=effective_step,
            allow_rotate=request.allow_rotate,
            progress_cb=progress_callback,
            performance_mode=request.performance_mode
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
            performance_mode=request.performance_mode,
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
    output_paths = [output_path]

    # Limite do JPEG é 65535 pixels. Vamos usar 65000 por segurança.
    MAX_JPEG_DIM = 65000
    
    if final_h > MAX_JPEG_DIM:
        log_fn(f"\n  ⚠  Imagem muito longa para um único JPEG ({final_h}px).\n", "warn")
        log_fn(f"  Dividindo em partes de no máximo {MAX_JPEG_DIM}px...\n", "info")
        
        output_paths = []
        num_parts = (final_h + MAX_JPEG_DIM - 1) // MAX_JPEG_DIM
        
        for i in range(num_parts):
            y0 = i * MAX_JPEG_DIM
            y1 = min((i + 1) * MAX_JPEG_DIM, final_h)
            part = final_jpeg.crop((0, y0, final_w, y1))
            
            part_name = f"{output_path.stem}_parte{i+1}.jpg"
            part_path = output_path.parent / part_name
            part.save(str(part_path), format="JPEG", dpi=(100, 100), quality=profile["jpeg_quality"])
            output_paths.append(part_path)
            log_fn(f"    ✓ Parte {i+1} salva: {part_name}\n", "ok")
        
        # Mantemos o output_path original como a primeira parte para compatibilidade
        output_path = output_paths[0]
    else:
        final_jpeg.save(str(output_path), format="JPEG", dpi=(100, 100), quality=profile["jpeg_quality"])
        log_fn(f"\nSalvo em:\n    {output_path}\n", "ok")

    log_fn(f"    {len(packed)} imagens posicionadas.\n", "ok")
    log_fn(f"\n{'─' * 58}\n", "muted")

    return RollerPackResult(
        output_path=output_path,
        output_paths=output_paths,
        packed_count=len(packed),
        final_width_px=final_w,
        final_height_px=final_h,
        final_image=final,
        final_jpeg=final_jpeg,
        image_items=image_items,
    )

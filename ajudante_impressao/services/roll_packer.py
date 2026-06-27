from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # Permitir processar imagens muito grandes

from ..algorithms.image_ops import add_label_to_image, cm_to_px, process_images, rgba_to_white_background
from ..algorithms.packing import build_canvas, pack_images_masked


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
    dxf_path: Path | None = None
    packed: list[tuple[Image.Image, int, int]] | None = None


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

    # Gerar DXF do rolo final
    status_fn("Gerando DXF do rolo final...")
    log_fn("\nGerando DXF de corte para o rolo final...\n", "info")
    dxf_path = output_path.with_suffix(".dxf")
    try:
        _generate_roll_dxf(
            packed=packed,
            final_h=final_h,
            output_dxf_path=dxf_path,
            image_items=image_items,
            dpi=100,
        )
        log_fn(f"    ✓ DXF salvo: {dxf_path.name}\n", "ok")
    except Exception as exc:
        dxf_path = None
        log_fn(f"  ✗ Erro ao gerar DXF: {exc}\n", "err")

    # Gerar imagem de debug com contornos
    status_fn("Gerando imagem de debug (contornos)...")
    debug_contour_path = output_path.with_name(output_path.stem + "_debug_contornos.png")
    try:
        _save_debug_contours(
            packed=packed,
            final_w=final_w,
            final_h=final_h,
            output_path=debug_contour_path,
            image_items=image_items,
        )
        log_fn(f"    ✓ Debug de contornos salvo: {debug_contour_path.name}\n", "ok")
    except Exception as exc:
        log_fn(f"  ✗ Erro ao gerar debug de contornos: {exc}\n", "err")

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
        dxf_path=dxf_path,
        packed=packed,
    )



def _extract_precise_contour(
    clean_variant: Image.Image,
    x: int,
    y: int,
    alpha_threshold: int = 10,
    close_gap_pct: float = 0.5,
    simplify_eps: float = 0.8,
) -> list[tuple[float, float]]:
    """Extrai um contorno suave e preciso da imagem de alta qualidade.
    Aplica suavização gaussiana para ruídos de borda, binarização adaptativa e
    usa TC89_KCOS para curvas perfeitas, simplificando com base na raiz da área.
    
    Retorna uma lista de pontos (roll_x, roll_y) na resolução real.
    """
    import cv2
    import numpy as np

    alpha = np.array(clean_variant.getchannel("A"), dtype=np.uint8)
    
    # 1. Filtro gaussiano para suavizar serrilhados da borda antes do threshold
    alpha_blur = cv2.GaussianBlur(alpha, (3, 3), 0.8)
    
    # 2. Threshold adaptativo simples para remover pixels semi-transparentes indesejados
    mask_bin = (alpha_blur > alpha_threshold).astype(np.uint8) * 255

    if not mask_bin.any():
        return []

    # Reduz para resolução limite (máx 1000px) para eficiência nos algoritmos morfológicos
    orig_h, orig_w = mask_bin.shape
    max_dim = max(orig_h, orig_w)
    if max_dim > 1000:
        scale_factor = max_dim / 1000.0
        down_w = int(round(orig_w / scale_factor))
        down_h = int(round(orig_h / scale_factor))
        mask_proc = cv2.resize(mask_bin, (down_w, down_h), interpolation=cv2.INTER_AREA)
    else:
        scale_factor = 1.0
        mask_proc = mask_bin

    # 3. Morfologia fina (apenas 0.5% em vez de 3%)
    min_side = min(mask_proc.shape[0], mask_proc.shape[1])
    close_radius = max(3, int(min_side * close_gap_pct / 100))
    kernel_size = 2 * close_radius + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    
    mask_dilated = cv2.dilate(mask_proc, kernel, iterations=1)
    mask_closed = cv2.morphologyEx(mask_dilated, cv2.MORPH_CLOSE, kernel)
    
    # 4. Fechamento de buracos internos via floodFill
    flood = mask_closed.copy()
    h_m, w_m = flood.shape
    border_mask = np.zeros((h_m + 2, w_m + 2), np.uint8)
    cv2.floodFill(flood, border_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flood)
    mask_filled = cv2.bitwise_or(mask_closed, holes)

    # 5. Encontra contornos usando CHAIN_APPROX_TC89_KCOS que é superior para curvas orgânicas
    contours, _ = cv2.findContours(mask_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS)
    if not contours:
        return []
        
    main_contour = max(contours, key=cv2.contourArea)

    # 6. Simplificação inteligente proporcional à raiz da área (mais estável)
    if simplify_eps > 0:
        area = cv2.contourArea(main_contour)
        epsilon = max(0.5, simplify_eps * np.sqrt(area) * 0.015)
        simplified = cv2.approxPolyDP(main_contour, epsilon, True)
    else:
        simplified = main_contour

    # 7. Escala os pontos de volta à resolução original e translada para coordenadas do rolo
    points_roll = []
    for pt in simplified:
        local_x, local_y = pt[0]
        orig_local_x = local_x * scale_factor
        orig_local_y = local_y * scale_factor
        points_roll.append((x + orig_local_x, y + orig_local_y))

    return points_roll


def _generate_roll_dxf(
    packed: list[tuple[Image.Image, int, int]],
    final_h: int,
    output_dxf_path: Path,
    image_items: list[dict],
    dpi: int = 100,
    simplify_eps: float = 0.8,
    close_gap_pct: float = 0.5,
    edge_sensitivity: int = 30,
    layer_name: str = "CORTE",
) -> Path:
    """Extrai os contornos das imagens limpas originais e os gera no DXF final do rolo."""
    import ezdxf
    from ezdxf import units
    from ..algorithms.image_ops import trim_empty_borders
    from ..algorithms.packing import _rotate_image

    doc = ezdxf.new(dxfversion="R2010")
    doc.units = units.MM
    msp = doc.modelspace()
    doc.layers.add(layer_name, color=1)  # Vermelho padrão ACI

    for img, x, y in packed:
        orig_id = img.info.get("_original_id", None)
        angle = img.info.get("_original_angle", 0)

        if orig_id is None or orig_id >= len(image_items):
            clean_variant = img
        else:
            clean_img = image_items[orig_id]["image"]
            clean_cropped = trim_empty_borders(clean_img)
            if angle != 0:
                clean_variant = trim_empty_borders(_rotate_image(clean_cropped, angle))
            else:
                clean_variant = clean_cropped

        if clean_variant.mode != "RGBA":
            clean_variant = clean_variant.convert("RGBA")

        # Chama a função de extração precisa unificada
        points_roll = _extract_precise_contour(
            clean_variant=clean_variant,
            x=x,
            y=y,
            alpha_threshold=10,
            close_gap_pct=close_gap_pct,
            simplify_eps=simplify_eps,
        )

        if len(points_roll) < 3:
            continue

        points_mm = []
        for rx, ry in points_roll:
            x_mm = (rx / dpi) * 25.4
            y_mm = ((final_h - ry) / dpi) * 25.4
            points_mm.append((x_mm, y_mm))

        msp.add_lwpolyline(
            points_mm,
            dxfattribs={"layer": layer_name, "closed": True},
        )

    output_dxf_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(output_dxf_path))
    return output_dxf_path


def _save_debug_contours(
    packed: list[tuple[Image.Image, int, int]],
    final_w: int,
    final_h: int,
    output_path: Path,
    image_items: list[dict],
    simplify_eps: float = 0.8,
    close_gap_pct: float = 0.5,
    scale_down: int = 4,
) -> None:
    """Gera uma imagem PNG de debug mostrando apenas os contornos das peças posicionadas no rolo.
    Garante sincronia 100% fiel com o resultado que será salvo no DXF.
    """
    import cv2
    import numpy as np
    from ..algorithms.image_ops import trim_empty_borders
    from ..algorithms.packing import _rotate_image

    dbg_w = max(1, final_w // scale_down)
    dbg_h = max(1, final_h // scale_down)
    sf = 1.0 / scale_down

    canvas = np.zeros((dbg_h, dbg_w, 3), dtype=np.uint8)
    canvas[:] = (30, 30, 30)

    PALETTE = [
        (0, 220, 255),    # ciano
        (0, 255, 128),    # verde
        (255, 200, 0),    # amarelo
        (255, 80, 80),    # vermelho claro
        (200, 100, 255),  # roxo
        (255, 160, 50),   # laranja
        (80, 200, 255),   # azul claro
        (255, 255, 255),  # branco
    ]

    for idx, (img, x, y) in enumerate(packed):
        orig_id = img.info.get("_original_id", None)
        angle = img.info.get("_original_angle", 0)

        if orig_id is None or orig_id >= len(image_items):
            clean_variant = img
        else:
            clean_img = image_items[orig_id]["image"]
            clean_cropped = trim_empty_borders(clean_img)
            if angle != 0:
                clean_variant = trim_empty_borders(_rotate_image(clean_cropped, angle))
            else:
                clean_variant = clean_cropped

        if clean_variant.mode != "RGBA":
            clean_variant = clean_variant.convert("RGBA")

        # Usa o mesmo extrator unificado
        points_roll = _extract_precise_contour(
            clean_variant=clean_variant,
            x=x,
            y=y,
            alpha_threshold=10,
            close_gap_pct=close_gap_pct,
            simplify_eps=simplify_eps,
        )

        if len(points_roll) < 3:
            continue

        # Transforma pontos para a escala do canvas de debug
        pts_debug = []
        for rx, ry in points_roll:
            dbg_x = int(round(rx * sf))
            dbg_y = int(round(ry * sf))
            pts_debug.append([dbg_x, dbg_y])

        pts_np = np.array(pts_debug, dtype=np.int32).reshape((-1, 1, 2))
        color = PALETTE[idx % len(PALETTE)]

        # Preenche área semitransparente
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [pts_np], color=(color[0] // 5, color[1] // 5, color[2] // 5))
        cv2.addWeighted(overlay, 0.5, canvas, 0.5, 0, canvas)

        # Contorno com espessura proporcional ao tamanho do canvas
        thickness = max(1, dbg_w // 400)
        cv2.polylines(canvas, [pts_np], isClosed=True, color=color, thickness=thickness)

        # Desenha o número ID no centro do bounding box
        bx, by, bw, bh = cv2.boundingRect(pts_np)
        cx = bx + bw // 2
        cy = by + bh // 2
        label = str(idx)
        font_scale = max(0.3, min(1.2, bw / 120))
        cv2.putText(
            canvas, label,
            (cx - 6, cy + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            max(1, thickness),
            cv2.LINE_AA,
        )

    from PIL import Image as PILImage
    debug_img = PILImage.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    debug_img.save(str(output_path), format="PNG")


from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
import math
import ezdxf
from ezdxf import units
from concurrent.futures import ThreadPoolExecutor
from functools import partial

Image.MAX_IMAGE_PIXELS = None  # Permitir processar imagens muito grandes

from ..algorithms.image_ops import add_label_to_image, cm_to_px, process_images, rgba_to_white_background, trim_empty_borders
from ..algorithms.packing import build_canvas, pack_images_masked, _rotate_image


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
    # Parâmetros de corte DXF para Router CNC
    dxf_bleed_mm: float = 0.0                    # Sangria em mm (0 = corte na borda exata da arte)
    dxf_simplify_eps: float = 1.0                # Fator de simplificação Douglas-Peucker
    dxf_include_border: bool = True              # Incluir retângulo do rolo na camada ROLO
    dxf_layer_name: str = "CORTE"               # Nome da camada de corte no DXF


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
    yield_pct: float = 0.0
    waste_pct: float = 0.0
    useful_area_m2: float = 0.0
    total_area_m2: float = 0.0
    elapsed_seconds: float = 0.0
    dxf_path: Path | None = None
    packed: list[tuple[Image.Image, int, int]] | None = None


def run_roll_packer(
    request: RollerPackRequest,
    log_fn: LogCallback,
    status_fn: StatusCallback,
    debug_fn: DebugCallback | None = None,
    image_items: list[dict] | None = None,
) -> RollerPackResult | None:
    t_start = time.time()
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
    if request.dxf_bleed_mm > 0:
        log_fn(f"  DXF Sangria: {request.dxf_bleed_mm:.1f} mm\n", "info")
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

    status_fn("Gerando debug do recorte...")
    debug_cut_path = request.folder / f"{Path(request.output_name).stem}_debug_recorte_contornos.png"
    try:
        _save_processed_contour_debug(image_items=image_items, output_path=debug_cut_path)
        log_fn(f"    ✓ Debug do recorte salvo: {debug_cut_path.name}\n", "ok")
    except Exception as exc:
        log_fn(f"  ✗ Erro ao gerar debug do recorte: {exc}\n", "err")

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

    pack_res = pack_images_masked(
        images=images,
        max_width=roll_px,
        spacing=spacing_px,
        margin=margin_px,
        step=effective_step,
        allow_rotate=request.allow_rotate,
        progress_cb=progress_callback,
        performance_mode=request.performance_mode
    )

    if len(pack_res) == 4:
        packed, final_w, final_h, useful_area_px = pack_res
    else:
        packed, final_w, final_h = pack_res
        useful_area_px = 0

    total_canvas_area_px = max(1, final_w * final_h)
    yield_pct = round((useful_area_px / total_canvas_area_px) * 100.0, 1)
    waste_pct = round(max(0.0, 100.0 - yield_pct), 1)

    # Converter px -> cm -> m² (100 px = 2.54 cm -> 1 px = 0.0254 cm)
    useful_area_cm2 = useful_area_px * (0.0254 ** 2)
    total_area_cm2 = (final_w * 0.0254) * (final_h * 0.0254)
    useful_area_m2 = round(useful_area_cm2 / 10000.0, 3)
    total_area_m2 = round(total_area_cm2 / 10000.0, 3)

    log_fn(
        f"  Canvas final: {final_w}×{final_h}px  ({final_w / 100 * 2.54:.1f}cm × {final_h / 100 * 2.54:.1f}cm)\n",
        "info",
    )
    log_fn(f"\n{'─' * 58}\n", "muted")
    log_fn(f"📊  RELATÓRIO DE APROVEITAMENTO E DESPERDÍCIO:\n", "info")
    log_fn(f"    • Aproveitamento Útil:  {yield_pct}%\n", "ok")
    log_fn(f"    • Sobra / Desperdício:  {waste_pct}%\n", "warn" if waste_pct > 30 else "info")
    log_fn(f"    • Área Total Consumida: {total_area_m2} m²  (Útil: {useful_area_m2} m²)\n", "muted")
    log_fn(f"{'─' * 58}\n\n", "muted")

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
            final_w=final_w,
            final_h=final_h,
            output_dxf_path=dxf_path,
            image_items=image_items,
            dpi=100,
            bleed_mm=request.dxf_bleed_mm,
            simplify_eps=request.dxf_simplify_eps,
            include_border=request.dxf_include_border,
            layer_name=request.dxf_layer_name,
        )
        log_fn(f"    ✓ DXF salvo: {dxf_path.name}\n", "ok")
    except Exception as exc:
        dxf_path = None
        log_fn(f"  ✗ Erro ao gerar DXF: {exc}\n", "err")

    # Gerar imagem de debug com contornos — 100% fiel ao DXF
    status_fn("Gerando imagem de debug (contornos)...")
    debug_contour_path = output_path.with_name(output_path.stem + "_debug_contornos.png")
    try:
        _save_debug_contours(
            packed=packed,
            final_w=final_w,
            final_h=final_h,
            output_path=debug_contour_path,
            image_items=image_items,
            bleed_mm=request.dxf_bleed_mm,
            simplify_eps=request.dxf_simplify_eps,
        )
        log_fn(f"    ✓ Debug de contornos salvo: {debug_contour_path.name}\n", "ok")
    except Exception as exc:
        log_fn(f"  ✗ Erro ao gerar debug de contornos: {exc}\n", "err")

    elapsed_sec = round(time.time() - t_start, 2)
    log_fn(f"    ✓ {len(packed)} imagens posicionadas com sucesso.\n", "ok")
    log_fn(f"⏱  Tempo Total de Geração: {elapsed_sec:.2f} segundos\n", "ok")
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
        yield_pct=yield_pct,
        waste_pct=waste_pct,
        useful_area_m2=useful_area_m2,
        total_area_m2=total_area_m2,
        elapsed_seconds=elapsed_sec,
        dxf_path=dxf_path,
        packed=packed,
    )


# ---------------------------------------------------------------------------
# Extração de contornos (Pipeline V3 — corrigido para Router CNC)
# ---------------------------------------------------------------------------

def _extract_piece_contours(
    clean_variant: Image.Image,
    x: int,
    y: int,
    alpha_threshold: int = 5,
    simplify_eps: float = 1.0,
    bleed_mm: float = 0.0,
    dpi: int = 100,
    min_area_px: int = 200,
) -> list[list[tuple[float, float]]]:
    """Extrai TODOS os contornos visíveis de uma peça posicionada no canvas do rolo.

    Pipeline V3 (Router CNC):
      - Borda de zeros adicionada (pad) ao redor da máscara antes de qualquer operação,
        garantindo que o floodFill/morfologia NUNCA confunda a borda da imagem com
        a borda da arte (bug que gerava retângulos no DXF anterior).
      - Fechamento morfológico por raio proporcional ao tamanho da peça.
      - Suporte a sangria morfológica (bleed) via dilatação paralela exata.
      - Suporte a múltiplos contornos por peça (ex: personagens com acessórios soltos).
      - Simplificação Douglas-Peucker adaptativa para gerar polilinhas limpas na CNC.

    Retorna lista de contornos; cada contorno é uma lista de pontos (roll_x, roll_y)
    em coordenadas reais do canvas do rolo (pixels, mesma escala do rolo impresso).
    """
    import cv2
    import numpy as np

    if clean_variant.mode != "RGBA":
        clean_variant = clean_variant.convert("RGBA")

    alpha = np.array(clean_variant.getchannel("A"), dtype=np.uint8)
    mask_bin = (alpha > alpha_threshold).astype(np.uint8) * 255

    if not mask_bin.any():
        return []

    orig_h, orig_w = mask_bin.shape

    # ── 1. Downscale apenas para imagens muito grandes (>4000px) ────────────
    max_dim = max(orig_h, orig_w)
    if max_dim > 4000:
        scale_factor = max_dim / 4000.0
        down_w = max(1, int(round(orig_w / scale_factor)))
        down_h = max(1, int(round(orig_h / scale_factor)))
        mask_work = cv2.resize(mask_bin, (down_w, down_h), interpolation=cv2.INTER_AREA)
    else:
        scale_factor = 1.0
        mask_work = mask_bin

    work_h, work_w = mask_work.shape

    # ── 2. Padding de segurança: garante que a arte nunca toca a borda ──────
    #    Sem isso, o floodFill a partir de (0,0) pode ficar bloqueado pela arte
    #    e inverter tudo ao redor — gerando retângulos no DXF.
    PAD = 8
    padded = cv2.copyMakeBorder(
        mask_work, PAD, PAD, PAD, PAD,
        cv2.BORDER_CONSTANT, value=0
    )

    # ── 3. Fechamento morfológico para conectar lacunas finas (<3px) ────────
    min_side = min(work_h, work_w)
    close_r = max(2, min(12, int(round(min_side * 0.008))))
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * close_r + 1, 2 * close_r + 1))
    closed = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, k_close)

    # ── 4. Sangria morfológica (bleed) exata e paralela ─────────────────────
    if bleed_mm > 0 and dpi > 0:
        bleed_px_work = int(round((bleed_mm / 25.4) * (dpi / scale_factor)))
        if bleed_px_work > 0:
            k_bleed = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (2 * bleed_px_work + 1, 2 * bleed_px_work + 1)
            )
            closed = cv2.dilate(closed, k_bleed)

    # ── 5. Extrai contornos externos ─────────────────────────────────────────
    contours_raw, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours_raw:
        return []

    result: list[list[tuple[float, float]]] = []

    for cnt in contours_raw:
        area = cv2.contourArea(cnt)
        # Descarta ruídos muito pequenos
        if area < min_area_px:
            continue

        # ── 6. Simplificação Douglas-Peucker adaptativa ──────────────────
        if simplify_eps > 0:
            arc = cv2.arcLength(cnt, True)
            # Epsilon adaptativo: proporcional ao perímetro do contorno
            epsilon = max(0.5, simplify_eps * arc / 500.0)
            simplified = cv2.approxPolyDP(cnt, epsilon, True)
        else:
            simplified = cnt

        if len(simplified) < 3:
            continue

        # ── 7. Converte para coordenadas reais do canvas do rolo ─────────
        pts_roll: list[tuple[float, float]] = []
        for pt in simplified:
            # Compensar o padding e o downscale
            local_x = (float(pt[0][0]) - PAD) * scale_factor
            local_y = (float(pt[0][1]) - PAD) * scale_factor
            # Clamp para não sair dos limites da imagem
            local_x = max(0.0, min(local_x, float(orig_w - 1)))
            local_y = max(0.0, min(local_y, float(orig_h - 1)))
            pts_roll.append((x + local_x, y + local_y))

        if len(pts_roll) >= 3:
            result.append(pts_roll)

    return result


def _generate_roll_dxf(
    packed: list[tuple[Image.Image, int, int]],
    final_w: int,
    final_h: int,
    output_dxf_path: Path,
    image_items: list[dict],
    dpi: int = 100,
    bleed_mm: float = 0.0,
    simplify_eps: float = 1.0,
    include_border: bool = True,
    layer_name: str = "CORTE",
) -> Path:
    """Gera o DXF de corte fiel ao rolo impresso.

    Cada peça gera uma ou mais LWPOLYLINE fechadas na camada CORTE,
    seguindo a silhueta real (contorno alfa) da arte — não retângulos.

    Parâmetros:
        packed:          Lista de (img, x, y) do resultado do packer
        final_w/h:       Dimensões reais do canvas do rolo em pixels
        output_dxf_path: Caminho de saída do arquivo .dxf
        image_items:     Lista de dicionários com as artes originais (chave 'image')
        dpi:             Resolução do rolo (100 DPI padrão)
        bleed_mm:        Sangria em mm ao redor de cada contorno (0 = sem sangria)
        simplify_eps:    Fator de simplificação Douglas-Peucker (menor = mais fiel)
        include_border:  Se True, adiciona o retângulo total do rolo na camada ROLO
        layer_name:      Nome da camada de corte (padrão: CORTE)
    """

    doc = ezdxf.new(dxfversion="R2010")
    doc.units = units.MM
    msp = doc.modelspace()

    # Camadas
    doc.layers.add(layer_name, color=1)       # Vermelho = corte (padrão CNC/CAD)
    if include_border:
        doc.layers.add("ROLO", color=3)       # Verde = limite da chapa/rolo

    # ── Retângulo limite do rolo (referência de zeramento G54 na CNC) ───────
    if include_border:
        rolo_w_mm = (final_w / dpi) * 25.4
        rolo_h_mm = (final_h / dpi) * 25.4
        border_pts = [
            (0.0,       0.0),
            (rolo_w_mm, 0.0),
            (rolo_w_mm, rolo_h_mm),
            (0.0,       rolo_h_mm),
        ]
        msp.add_lwpolyline(
            border_pts,
            dxfattribs={"layer": "ROLO", "closed": True},
        )

    # ── Contornos das peças ──────────────────────────────────────────────────
    def _process_piece(piece: tuple[Image.Image, int, int]) -> list[list[tuple[float, float]]]:
        img, x, y = piece
        orig_id = img.info.get("_original_id", None)
        angle = img.info.get("_original_angle", 0)

        # Usa sempre a imagem ORIGINAL limpa (sem rótulo) para extrair o contorno
        if orig_id is None or orig_id >= len(image_items):
            clean_img_raw = img
        else:
            clean_img_raw = image_items[orig_id]["image"]

        clean_cropped = trim_empty_borders(clean_img_raw)
        if angle != 0:
            clean_variant = trim_empty_borders(_rotate_image(clean_cropped, angle))
        else:
            clean_variant = clean_cropped

        if clean_variant.mode != "RGBA":
            clean_variant = clean_variant.convert("RGBA")

        # Extrai todos os contornos da peça
        return _extract_piece_contours(
            clean_variant=clean_variant,
            x=x,
            y=y,
            simplify_eps=simplify_eps,
            bleed_mm=bleed_mm,
            dpi=dpi,
        )

    # Processar em paralelo para acelerar extração de contornos pesados
    with ThreadPoolExecutor(max_workers=max(1, min(len(packed), 8))) as ex:
        all_pieces_contours = list(ex.map(_process_piece, packed))

    for all_contours in all_pieces_contours:
        for pts_roll in all_contours:
            if len(pts_roll) < 3:
                continue

            # Converte pixel → mm, invertendo Y para convenção CAD (Y↑)
            points_mm = []
            for rx, ry in pts_roll:
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


def _save_processed_contour_debug(
    image_items: list[dict],
    output_path: Path,
    thumb_size: int = 360,
    columns: int = 4,
) -> None:
    """Salva uma prancha para auditar o recorte alfa antes do encaixe."""

    if not image_items:
        return

    cell_w = thumb_size
    cell_h = thumb_size + 42
    rows = math.ceil(len(image_items) / columns)
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), (32, 32, 38))
    font = ImageFont.load_default()

    checker = Image.new("RGB", (thumb_size, thumb_size), (238, 238, 238))
    draw_checker = ImageDraw.Draw(checker)
    block = 18
    for yy in range(0, thumb_size, block):
        for xx in range(0, thumb_size, block):
            if (xx // block + yy // block) % 2:
                draw_checker.rectangle((xx, yy, xx + block - 1, yy + block - 1), fill=(204, 204, 204))

    for idx, item in enumerate(image_items):
        img = item["image"]
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        scale = min((thumb_size - 24) / max(1, img.width), (thumb_size - 24) / max(1, img.height), 1.0)
        preview_w = max(1, int(round(img.width * scale)))
        preview_h = max(1, int(round(img.height * scale)))
        preview = img.resize((preview_w, preview_h), Image.Resampling.LANCZOS)

        cell = checker.copy()
        px = (thumb_size - preview_w) // 2
        py = (thumb_size - preview_h) // 2
        cell.paste(preview, (px, py), preview.getchannel("A"))

        alpha = np.array(preview.getchannel("A"), dtype=np.uint8)
        mask = (alpha > 5).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cell_arr = np.array(cell)
            offset = np.array([[[px, py]]], dtype=np.int32)
            cv2.drawContours(cell_arr, [cnt + offset for cnt in contours], -1, (255, 0, 0), 2)
            cell = Image.fromarray(cell_arr)

        col = idx % columns
        row = idx // columns
        x = col * cell_w
        y = row * cell_h
        sheet.paste(cell, (x, y))

        draw = ImageDraw.Draw(sheet)
        name = str(item.get("name", f"imagem_{idx + 1}"))
        draw.text((x + 10, y + thumb_size + 8), f"{idx + 1}. {name[:38]}", fill=(245, 245, 245), font=font)
        draw.text((x + 10, y + thumb_size + 24), f"{img.width}x{img.height}px", fill=(180, 180, 190), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(output_path), format="PNG")


def _save_debug_contours(
    packed: list[tuple[Image.Image, int, int]],
    final_w: int,
    final_h: int,
    output_path: Path,
    image_items: list[dict],
    bleed_mm: float = 0.0,
    simplify_eps: float = 1.0,
    scale_down: int = 4,
) -> None:
    """Gera imagem PNG de debug com os contornos exatamente como irão para o DXF.

    100% fiel ao _generate_roll_dxf: usa o mesmo extrator _extract_piece_contours
    com os mesmos parâmetros, garantindo que o debug reflete o que a CNC vai cortar.
    """

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
            clean_img_raw = img
        else:
            clean_img_raw = image_items[orig_id]["image"]

        clean_cropped = trim_empty_borders(clean_img_raw)
        if angle != 0:
            clean_variant = trim_empty_borders(_rotate_image(clean_cropped, angle))
        else:
            clean_variant = clean_cropped

        if clean_variant.mode != "RGBA":
            clean_variant = clean_variant.convert("RGBA")

        # Mesmo extrator do DXF — garante fidelidade 100%
        all_contours = _extract_piece_contours(
            clean_variant=clean_variant,
            x=x,
            y=y,
            simplify_eps=simplify_eps,
            bleed_mm=bleed_mm,
            dpi=100,
        )

        color = PALETTE[idx % len(PALETTE)]
        thickness = max(1, dbg_w // 400)

        for pts_roll in all_contours:
            if len(pts_roll) < 3:
                continue

            pts_debug = []
            for rx, ry in pts_roll:
                dbg_x = int(round(rx * sf))
                dbg_y = int(round(ry * sf))
                dbg_x = max(0, min(dbg_x, dbg_w - 1))
                dbg_y = max(0, min(dbg_y, dbg_h - 1))
                pts_debug.append([dbg_x, dbg_y])

            pts_np = np.array(pts_debug, dtype=np.int32).reshape((-1, 1, 2))

            # Preenche área semitransparente
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [pts_np], color=(color[0] // 5, color[1] // 5, color[2] // 5))
            cv2.addWeighted(overlay, 0.5, canvas, 0.5, 0, canvas)

            cv2.polylines(canvas, [pts_np], isClosed=True, color=color, thickness=thickness)

        # Número do índice no centro do bounding box do primeiro contorno
        if all_contours:
            pts_all = []
            for c in all_contours:
                for rx, ry in c:
                    pts_all.append([int(round(rx * sf)), int(round(ry * sf))])
            if pts_all:
                pts_all_np = np.array(pts_all, dtype=np.int32)
                cx = int(pts_all_np[:, 0].mean())
                cy = int(pts_all_np[:, 1].mean())
                label = str(idx)
                font_scale = max(0.4, min(1.4, dbg_w / 600))
                cv2.putText(
                    canvas, label,
                    (cx - 6, cy + 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    color,
                    max(1, thickness),
                    cv2.LINE_AA,
                )

    debug_img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    debug_img.save(str(output_path), format="PNG")

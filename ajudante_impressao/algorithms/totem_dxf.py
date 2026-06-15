"""
totem_dxf.py — Extração de contorno e geração de DXF para artes de totem.

Pipeline:
  1. Carrega imagem (JPG/PNG)
  2. Remove fundo branco (reutilizando remove_white de image_ops)
  3. Extrai contorno externo principal via OpenCV (cv2.findContours)
  4. Simplifica o contorno com Douglas-Peucker (cv2.approxPolyDP)
  5. Converte coordenadas de pixels → milímetros reais (baseado no DPI)
  6. Aplica sangria (bleed) opcional em volta do contorno
  7. Gera arquivo DXF com LWPOLYLINE fechada na camada "CORTE"
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps

from .image_ops import remove_white, px_to_cm


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------

Contour = np.ndarray  # shape (N, 1, 2), dtype int32


@dataclass
class DxfResult:
    """Resultado da geração de DXF para um arquivo."""
    source_path: Path
    output_path: Path
    contour_points: int
    width_mm: float
    height_mm: float
    dpi_used: int


# ---------------------------------------------------------------------------
# Extracao de contorno
# ---------------------------------------------------------------------------

def _get_silhouette_mask(
    img: Image.Image,
    white_threshold: int = 245,
    edge_sensitivity: int = 30,
) -> np.ndarray:
    """
    Gera mascara binaria 8-bit da silhueta usando abordagem HIBRIDA:

    1. Deteccao de bordas (Canny) — detecta contornos desenhados,
       tracos, outlines. Funciona para arte branca sobre branco.
    2. Deteccao de areas coloridas — pixels que nao sao brancos/claros.
    3. OR das duas mascaras — qualquer pixel que seja borda OU colorido
       faz parte da silhueta.

    Isso resolve o problema de arte clara (flores brancas, sketches)
    onde o remove_white apagava a propria arte.

    Args:
        img:              Imagem PIL de entrada
        white_threshold:  Sensibilidade de deteccao de nao-branco (0-255)
                          Valor menor = detecta mais pixeis como nao-brancos
        edge_sensitivity: Limiar baixo do Canny (0-100).
                          Valor menor = detecta tracos mais finos/claros
    """
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    # --- Metodo 1: Deteccao de bordas (Canny) ---
    # Blur leve para reduzir ruido de JPEG antes do Canny
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    lo = max(5, edge_sensitivity)
    hi = min(255, lo * 3)
    edges = cv2.Canny(blurred, lo, hi)

    # --- Metodo 2: Areas nao-brancas (cores, sombras, preenchimentos) ---
    # Distancia do branco puro: quanto mais escuro/colorido, maior o valor
    dist_white = 255 - gray
    sensitivity = max(1, 255 - white_threshold)  # quanto menor o threshold, mais detecta
    _, color_mask = cv2.threshold(dist_white, sensitivity, 255, cv2.THRESH_BINARY)

    # --- Combinar: qualquer pixel detectado por qualquer metodo conta ---
    combined = cv2.bitwise_or(edges, color_mask)
    return combined


# Alias para compatibilidade interna (nao exposto publicamente)
def _get_alpha_mask(img: Image.Image, white_threshold: int, softness: int) -> np.ndarray:
    return _get_silhouette_mask(img, white_threshold=white_threshold, edge_sensitivity=30)


def _get_dpi(img: Image.Image, dpi_override: Optional[int]) -> int:
    """Resolve o DPI da imagem (manual tem prioridade, senão lê da imagem)."""
    if dpi_override and dpi_override > 0:
        return dpi_override
    dpi_info = img.info.get("dpi", None)
    if dpi_info:
        try:
            val = int(round(float(dpi_info[0])))
            if val > 0:
                return val
        except (TypeError, IndexError, ValueError):
            pass
    return 72  # fallback seguro para imagens sem DPI embutido


def extract_contour(
    img: Image.Image,
    white_threshold: int = 245,
    softness: int = 18,
    simplify_eps: float = 2.0,
    close_gap_pct: float = 3.0,
    edge_sensitivity: int = 30,
) -> Tuple[Optional[Contour], np.ndarray]:
    """
    Extrai o contorno externo UNIFICADO da silhueta da imagem.

    Usa deteccao hibrida (bordas Canny + areas coloridas) para funcionar
    corretamente tanto em arte colorida (Stitch) quanto em arte clara
    (flores brancas, sketches, outlines).

    Em seguida aplica fechamento morfologico agressivo para unir partes
    separadas (orelhas, maos, petalas) em uma silhueta unica.

    Args:
        img:              Imagem PIL de entrada
        white_threshold:  Sensibilidade de cor nao-branca (0-255)
        softness:         (reservado para compatibilidade)
        simplify_eps:     Epsilon para simplificacao Douglas-Peucker (0-100)
        close_gap_pct:    % do menor lado usado como raio de fechamento
        edge_sensitivity: Sensibilidade do Canny (0-100, menor = mais bordas)

    Retorna:
        (contorno simplificado como ndarray shape (N,1,2), mascara de bordas)
        Retorna (None, mask) se nenhum contorno for encontrado.
    """
    # Mascara hibrida: bordas + areas coloridas
    mask = _get_silhouette_mask(img, white_threshold=white_threshold, edge_sensitivity=edge_sensitivity)

    # --- Fechamento morfologico AGRESSIVO ---
    # Raio proporcional ao tamanho para fundir petalas/partes separadas
    min_side = min(mask.shape[0], mask.shape[1])
    close_radius = max(15, int(min_side * close_gap_pct / 100))
    kernel_size = 2 * close_radius + 1  # sempre impar
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))

    # Dilatar -> preenche espacos brancos entre bordas e entre partes
    mask_dilated = cv2.dilate(mask, kernel, iterations=1)
    # Fechar -> suaviza e une completamente
    mask_closed = cv2.morphologyEx(mask_dilated, cv2.MORPH_CLOSE, kernel)

    # Preencher buracos internos (olhos, centros de flores, etc.)
    flood = mask_closed.copy()
    h, w = flood.shape
    border_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, border_mask, (0, 0), 255)
    holes = cv2.bitwise_not(flood)
    mask_filled = cv2.bitwise_or(mask_closed, holes)

    contours, _ = cv2.findContours(mask_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, mask

    # Pegar o contorno com maior area (a silhueta unificada)
    main_contour = max(contours, key=cv2.contourArea)

    # Simplificar com Douglas-Peucker
    if simplify_eps > 0:
        arc = cv2.arcLength(main_contour, True)
        # Epsilon como % do perimetro: 2.0 -> bem simplificado, 0.3 -> mais detalhado
        epsilon = max(1.0, simplify_eps * arc / 1000.0)
        simplified = cv2.approxPolyDP(main_contour, epsilon, True)
    else:
        simplified = main_contour

    return simplified, mask


# ---------------------------------------------------------------------------
# Conversão de coordenadas
# ---------------------------------------------------------------------------

def pixels_to_mm(px: float, dpi: int) -> float:
    """Converte pixels para milímetros."""
    return (px / dpi) * 25.4


def _expand_contour_bleed(
    points_mm: List[Tuple[float, float]],
    bleed_mm: float,
) -> List[Tuple[float, float]]:
    """
    Expande o contorno radialmente a partir do centroide para adicionar sangria.
    Cada ponto é empurrado 'bleed_mm' para fora a partir do centro do polígono.
    """
    if bleed_mm <= 0 or len(points_mm) < 3:
        return points_mm

    cx = sum(p[0] for p in points_mm) / len(points_mm)
    cy = sum(p[1] for p in points_mm) / len(points_mm)

    expanded = []
    for x, y in points_mm:
        dx = x - cx
        dy = y - cy
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            expanded.append((x, y))
            continue
        factor = (dist + bleed_mm) / dist
        expanded.append((cx + dx * factor, cy + dy * factor))

    return expanded


def contour_to_mm(
    contour: Contour,
    dpi: int,
    bleed_mm: float = 0.0,
    img_height_px: int = 0,
) -> List[Tuple[float, float]]:
    """
    Converte contorno de pixels para milímetros reais.

    O DXF usa eixo Y crescendo para cima (convenção CAD), por isso
    invertemos o Y: y_dxf = (img_height - y_px) em pixels, depois convertemos.
    """
    points = []
    for pt in contour:
        x_px, y_px = pt[0]
        x_mm = pixels_to_mm(x_px, dpi)
        # Inverter Y para convenção CAD (Y cresce para cima)
        if img_height_px > 0:
            y_mm = pixels_to_mm(img_height_px - y_px, dpi)
        else:
            y_mm = pixels_to_mm(y_px, dpi)
        points.append((x_mm, y_mm))

    if bleed_mm > 0:
        points = _expand_contour_bleed(points, bleed_mm)

    return points


# ---------------------------------------------------------------------------
# Geração do DXF
# ---------------------------------------------------------------------------

def generate_dxf(
    points_mm: List[Tuple[float, float]],
    output_path: Path,
    layer_name: str = "CORTE",
) -> Path:
    """
    Gera um arquivo DXF com o contorno como LWPOLYLINE fechada.

    A unidade do DXF é definida como milímetros (INSUNITS = 4).
    """
    import ezdxf
    from ezdxf import units

    doc = ezdxf.new(dxfversion="R2010")
    doc.units = units.MM  # milímetros

    msp = doc.modelspace()

    # Criar camada de corte (vermelho = cor padrão de corte)
    doc.layers.add(layer_name, color=1)  # cor 1 = vermelho no padrão ACI

    # Adicionar LWPOLYLINE fechada
    msp.add_lwpolyline(
        points_mm,
        dxfattribs={"layer": layer_name, "closed": True},
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(output_path))
    return output_path


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def process_totem_image(
    image_path: Path,
    output_path: Path,
    white_threshold: int = 245,
    softness: int = 18,
    bleed_mm: float = 3.0,
    simplify_eps: float = 2.0,
    close_gap_pct: float = 3.0,
    edge_sensitivity: int = 30,
    dpi_override: Optional[int] = None,
    layer_name: str = "CORTE",
    status_fn=None,
) -> DxfResult:
    """
    Pipeline completo: imagem -> DXF.

    Args:
        image_path:        Caminho da imagem de entrada
        output_path:       Caminho de saida do arquivo DXF
        white_threshold:   Sensibilidade de cor nao-branca (0-255)
        softness:          (reservado para compatibilidade)
        bleed_mm:          Sangria em milimetros (0 = sem sangria)
        simplify_eps:      Epsilon para simplificacao do contorno (0-100)
        close_gap_pct:     % do menor lado usado para fechar espacos entre partes
        edge_sensitivity:  Sensibilidade do Canny (0-100, menor = detecta tracos mais finos)
        dpi_override:      DPI manual (None = le da imagem)
        layer_name:        Nome da camada DXF de corte
        status_fn:         Callback opcional para log de status

    Returns:
        DxfResult com metadados do arquivo gerado
    """
    def _log(msg: str) -> None:
        if status_fn:
            status_fn(msg)

    _log(f"  Carregando: {image_path.name}")
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        dpi = _get_dpi(img, dpi_override)
        img_h = img.height

        _log(f"  DPI: {dpi} | Tamanho: {img.width}x{img.height}px")

        contour, _mask = extract_contour(
            img,
            white_threshold=white_threshold,
            softness=softness,
            simplify_eps=simplify_eps,
            close_gap_pct=close_gap_pct,
            edge_sensitivity=edge_sensitivity,
        )

    if contour is None or len(contour) < 3:
        raise ValueError(
            f"Nenhum contorno válido encontrado em '{image_path.name}'. "
            "Verifique o threshold de remoção de branco."
        )

    _log(f"  Contorno extraído: {len(contour)} pontos")

    points_mm = contour_to_mm(contour, dpi=dpi, bleed_mm=bleed_mm, img_height_px=img_h)

    xs = [p[0] for p in points_mm]
    ys = [p[1] for p in points_mm]
    width_mm = max(xs) - min(xs)
    height_mm = max(ys) - min(ys)

    _log(f"  Dimensões reais: {width_mm:.1f} × {height_mm:.1f} mm")
    if bleed_mm > 0:
        _log(f"  Sangria aplicada: {bleed_mm} mm")

    generate_dxf(points_mm, output_path, layer_name=layer_name)
    _log(f"  ✓ DXF gerado: {output_path.name}")

    return DxfResult(
        source_path=image_path,
        output_path=output_path,
        contour_points=len(points_mm),
        width_mm=width_mm,
        height_mm=height_mm,
        dpi_used=dpi,
    )

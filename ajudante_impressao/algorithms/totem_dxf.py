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


Image.MAX_IMAGE_PIXELS = None

# ---------------------------------------------------------------------------
# Extracao de contorno
# ---------------------------------------------------------------------------

def _get_silhouette_mask(
    img: Image.Image,
    white_threshold: int = 245,
    edge_sensitivity: int = 30,
) -> np.ndarray:
    """
    Gera máscara binária 8-bit da silhueta da arte do totem (255 = arte, 0 = fundo).

    Pipeline robusto:
      1. Transparência Alfa:
         Se a imagem possui canal alfa e há pixels transparentes (PNG/WebP),
         extrai a silhueta diretamente da transparência.
      2. Imagens com fundo branco/claro (JPG/PNG sólido):
         - Identifica candidatos a fundo com base na distância até o branco puro
           usando white_threshold.
         - Protege bordas detectadas (Canny) para que o fundo não invada artes claras.
         - Detecta e neutraliza linhas/molduras escuras de 1-8px comuns em exportações CAD.
         - Executa floodFill a partir de uma margem externa artificial (1px pad),
           garantindo que o fundo externo ao redor de toda a arte seja identificado,
           mesmo quando a arte toca as bordas ou a base da imagem.
    """
    # 1. Caso Alpha: transparência real
    if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
        rgba_img = img.convert("RGBA")
        alpha = np.array(rgba_img.getchannel("A"))
        if np.any(alpha < 240):
            return (alpha > 15).astype(np.uint8) * 255

    # 2. Caso Fundo Branco / Sólido
    rgb_img = img.convert("RGB")
    arr = np.array(rgb_img)
    rgb = arr[:, :, :3].astype(np.int16)

    white_tolerance = max(1, 255 - white_threshold)
    dist_white = np.max(np.abs(255 - rgb), axis=2)
    candidate_bg = (dist_white <= white_tolerance).astype(np.uint8) * 255

    # Proteção de traços finos/claros na borda da arte
    if edge_sensitivity > 0:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        lo = max(10, edge_sensitivity)
        hi = min(255, lo * 3)
        edges = cv2.Canny(blurred, lo, hi)
        candidate_bg[(edges > 0) & (dist_white > 4)] = 0

    # Burlar molduras/linhas escuras artificiais de exportação (1-10px) nas bordas
    h, w = candidate_bg.shape
    max_d = min(12, min(h, w) // 4)
    for d in range(1, max_d):
        if np.mean(dist_white[0:d, :] > white_tolerance) > 0.8 and np.mean(dist_white[d, :] <= white_tolerance) > 0.7:
            candidate_bg[0:d, :] = 255
        if np.mean(dist_white[-d:, :] > white_tolerance) > 0.8 and np.mean(dist_white[-1-d, :] <= white_tolerance) > 0.7:
            candidate_bg[-d:, :] = 255
        if np.mean(dist_white[:, 0:d] > white_tolerance) > 0.8 and np.mean(dist_white[:, d] <= white_tolerance) > 0.7:
            candidate_bg[:, 0:d] = 255
        if np.mean(dist_white[:, -d:] > white_tolerance) > 0.8 and np.mean(dist_white[:, -1-d] <= white_tolerance) > 0.7:
            candidate_bg[:, -d:] = 255

    # Inundação conexa a partir da borda externa
    flood = cv2.copyMakeBorder(candidate_bg, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
    flood_mask = np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 128)
    connected_bg = (flood[1:-1, 1:-1] == 128)

    # A máscara da silhueta é tudo que NÃO é o fundo externo conectado
    mask = (~connected_bg).astype(np.uint8) * 255
    return mask


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


def extract_contour_pair(
    img: Image.Image,
    white_threshold: int = 245,
    softness: int = 18,
    simplify_eps: float = 2.0,
    close_gap_pct: float = 3.0,
    edge_sensitivity: int = 30,
    bleed_mm: float = 0.0,
    dpi: int = 72,
) -> Tuple[Optional[Contour], Optional[Contour], np.ndarray]:
    """
    Extrai o contorno base da arte e o contorno com sangria paralela exata.

    A sangria é calculada por DILATAÇÃO MORFOLÓGICA direta na máscara binária
    (offset paralelo perfeito), preservando proporções, concavidades e detalhes
    sem a distorção da antiga expansão radial por centroide.

    Args:
        img:              Imagem PIL de entrada
        white_threshold:  Sensibilidade de cor nao-branca (0-255)
        softness:         (reservado para compatibilidade)
        simplify_eps:     Epsilon para simplificacao Douglas-Peucker (0-100)
        close_gap_pct:    % do menor lado usado como raio de fechamento
        edge_sensitivity: Sensibilidade do Canny (0-100, menor = mais bordas)
        bleed_mm:         Sangria em milímetros para o contorno de corte
        dpi:              Resolução para cálculo exato de pixels da sangria

    Retorna:
        (base_contour, bleed_contour, mask)
        - base_contour: contorno simplificado na borda exata da arte
        - bleed_contour: contorno simplificado com a sangria uniforme aplicada
        - mask: máscara de silhueta/bordas
    """
    mask = _get_silhouette_mask(img, white_threshold=white_threshold, edge_sensitivity=edge_sensitivity)

    # Fechamento morfológico para conectar pequenas descontinuidades e unir partes próximas
    min_side = min(mask.shape[0], mask.shape[1])
    close_radius = min(45, max(2, int(round(min_side * (close_gap_pct / 100.0)))))
    kernel_size = 2 * close_radius + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours_base, _ = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours_base:
        return None, None, mask_closed

    main_base = max(contours_base, key=cv2.contourArea)

    # Simplificar contorno base
    if simplify_eps > 0:
        arc_base = cv2.arcLength(main_base, True)
        eps_base = max(1.0, simplify_eps * arc_base / 1000.0)
        base_contour = cv2.approxPolyDP(main_base, eps_base, True)
    else:
        base_contour = main_base

    # Se não há sangria solicitada, o contorno de corte é o próprio contorno base
    if bleed_mm <= 0 or dpi <= 0:
        return base_contour, base_contour, mask_closed

    # --- Sangria via Dilatação Morfológica Paralela Exata ---
    bleed_px = int(round((bleed_mm / 25.4) * dpi))
    if bleed_px <= 0:
        return base_contour, base_contour, mask_closed

    pad = bleed_px + 4
    padded = cv2.copyMakeBorder(mask_closed, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    b_kernel_size = 2 * bleed_px + 1
    b_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (b_kernel_size, b_kernel_size))
    dilated_mask = cv2.dilate(padded, b_kernel)

    contours_bleed, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours_bleed:
        return base_contour, base_contour, mask_closed

    main_bleed = max(contours_bleed, key=cv2.contourArea).copy()
    # Deslocar coordenadas de volta compensando o padding de segurança
    main_bleed[:, 0, 0] -= pad
    main_bleed[:, 0, 1] -= pad

    if simplify_eps > 0:
        arc_bleed = cv2.arcLength(main_bleed, True)
        eps_bleed = max(1.0, simplify_eps * arc_bleed / 1000.0)
        bleed_contour = cv2.approxPolyDP(main_bleed, eps_bleed, True)
    else:
        bleed_contour = main_bleed

    return base_contour, bleed_contour, mask_closed


def extract_contour(
    img: Image.Image,
    white_threshold: int = 245,
    softness: int = 18,
    simplify_eps: float = 2.0,
    close_gap_pct: float = 3.0,
    edge_sensitivity: int = 30,
    bleed_mm: float = 0.0,
    dpi: int = 72,
) -> Tuple[Optional[Contour], np.ndarray]:
    """
    Extrai o contorno externo UNIFICADO da silhueta da imagem.
    Se bleed_mm > 0, já retorna o contorno com a sangria uniforme aplicada.
    """
    base, bleed, mask = extract_contour_pair(
        img=img,
        white_threshold=white_threshold,
        softness=softness,
        simplify_eps=simplify_eps,
        close_gap_pct=close_gap_pct,
        edge_sensitivity=edge_sensitivity,
        bleed_mm=bleed_mm,
        dpi=dpi,
    )
    return (bleed if bleed_mm > 0 else base), mask


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
    Expansão radial legada (mantida apenas como fallback).
    A extração morfológica em extract_contour_pair é o padrão preciso recomendado.
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

    # Apenas se um caller externo ainda solicitar sangria aqui
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
            bleed_mm=bleed_mm,
            dpi=dpi,
        )

    if contour is None or len(contour) < 3:
        raise ValueError(
            f"Nenhum contorno válido encontrado em '{image_path.name}'. "
            "Verifique o threshold de remoção de branco."
        )

    _log(f"  Contorno extraído: {len(contour)} pontos")

    # Sangria uniforme já foi aplicada com precisão no espaço de pixels
    points_mm = contour_to_mm(contour, dpi=dpi, bleed_mm=0.0, img_height_px=img_h)

    xs = [p[0] for p in points_mm]
    ys = [p[1] for p in points_mm]
    width_mm = max(xs) - min(xs)
    height_mm = max(ys) - min(ys)

    _log(f"  Dimensões reais: {width_mm:.1f} × {height_mm:.1f} mm")
    if bleed_mm > 0:
        _log(f"  Sangria morfológica aplicada: {bleed_mm:.1f} mm (offset paralelo)")

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

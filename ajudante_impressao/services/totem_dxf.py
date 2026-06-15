"""
services/totem_dxf.py — Orquestrador do módulo Totem DXF.

Liga a interface gráfica ao algoritmo de extração de contorno e geração de DXF.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from ..algorithms.totem_dxf import DxfResult, process_totem_image


VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


@dataclass
class TotemDxfOptions:
    """Parametros de configuracao para geracao de DXF."""
    white_threshold: int = 245
    softness: int = 18
    bleed_mm: float = 3.0
    simplify_eps: float = 2.0
    close_gap_pct: float = 3.0
    edge_sensitivity: int = 30
    dpi_override: Optional[int] = None
    layer_name: str = "CORTE"


@dataclass
class TotemBatchRequest:
    """Requisição de processamento em lote de uma pasta de imagens."""
    folder_path: Path
    output_folder: Path
    options: TotemDxfOptions = field(default_factory=TotemDxfOptions)


@dataclass
class TotemManualRequest:
    """Requisição de processamento manual de uma única imagem."""
    image_path: Path
    output_path: Path
    options: TotemDxfOptions = field(default_factory=TotemDxfOptions)


@dataclass
class TotemBatchResult:
    """Resultado do processamento em lote."""
    results: List[DxfResult] = field(default_factory=list)
    errors: List[tuple[Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results) + len(self.errors)

    @property
    def success_count(self) -> int:
        return len(self.results)

    @property
    def error_count(self) -> int:
        return len(self.errors)


# ---------------------------------------------------------------------------
# Funções de execução (chamadas em QThread para não travar a UI)
# ---------------------------------------------------------------------------

def run_manual_totem(
    request: TotemManualRequest,
    status_fn: Optional[Callable[[str], None]] = None,
) -> DxfResult:
    """
    Processa uma unica imagem e gera o DXF correspondente.

    Raises:
        ValueError: Se o contorno nao puder ser extraido.
        Exception:  Para outros erros de I/O ou processamento.
    """
    opts = request.options
    return process_totem_image(
        image_path=request.image_path,
        output_path=request.output_path,
        white_threshold=opts.white_threshold,
        softness=opts.softness,
        bleed_mm=opts.bleed_mm,
        simplify_eps=opts.simplify_eps,
        close_gap_pct=opts.close_gap_pct,
        edge_sensitivity=opts.edge_sensitivity,
        dpi_override=opts.dpi_override,
        layer_name=opts.layer_name,
        status_fn=status_fn,
    )


def run_batch_totem(
    request: TotemBatchRequest,
    log_fn: Optional[Callable[[str], None]] = None,
    status_fn: Optional[Callable[[str], None]] = None,
) -> TotemBatchResult:
    """
    Processa todos os arquivos de imagem válidos em uma pasta.

    O DXF de cada imagem é salvo na output_folder com o mesmo nome (extensão .dxf).
    """
    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    def _status(msg: str) -> None:
        if status_fn:
            status_fn(msg)

    folder = Path(request.folder_path)
    output_folder = Path(request.output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    files = sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in VALID_IMAGE_EXTS
    )

    if not files:
        _log("⚠  Nenhuma imagem encontrada na pasta selecionada.")
        return TotemBatchResult()

    batch_result = TotemBatchResult()
    total = len(files)
    _log(f"  {total} imagem(ns) encontrada(s) em: {folder.name}\n")

    for idx, img_path in enumerate(files, 1):
        _status(f"Processando {idx}/{total}: {img_path.name}")
        output_path = output_folder / (img_path.stem + ".dxf")
        _log(f"\n[{idx}/{total}] {img_path.name}")

        try:
            result = process_totem_image(
                image_path=img_path,
                output_path=output_path,
                white_threshold=request.options.white_threshold,
                softness=request.options.softness,
                bleed_mm=request.options.bleed_mm,
                simplify_eps=request.options.simplify_eps,
                close_gap_pct=request.options.close_gap_pct,
                edge_sensitivity=request.options.edge_sensitivity,
                dpi_override=request.options.dpi_override,
                layer_name=request.options.layer_name,
                status_fn=_log,
            )
            batch_result.results.append(result)
        except Exception as exc:
            _log(f"  ✗ Erro: {exc}")
            batch_result.errors.append((img_path, str(exc)))

    _log(
        f"\n{'='*40}\n"
        f"  Concluído: {batch_result.success_count} gerados, "
        f"{batch_result.error_count} erro(s).\n"
        f"  Pasta de saída: {output_folder}"
    )
    _status("Lote concluído.")
    return batch_result

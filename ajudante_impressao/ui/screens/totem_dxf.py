"""
ui/screens/totem_dxf.py — Tela de geração de DXF para totens.

Interface PySide6 que permite ao operador:
  - Carregar uma pasta com artes de totem (JPG/PNG)
  - Configurar parâmetros de extração de contorno e sangria
  - Gerar DXFs em lote para corte na máquina
  - Visualizar o contorno extraído sobre a arte (preview com overlay verde)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont, QImage, QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...algorithms.totem_dxf import extract_contour, extract_contour_pair, _get_dpi
from ...services.totem_dxf import (
    TotemBatchRequest,
    TotemBatchResult,
    TotemDxfOptions,
    TotemManualRequest,
    run_batch_totem,
    run_manual_totem,
)
from ..common import ScreenScaffold, ZoomablePreviewWidget


# ---------------------------------------------------------------------------
# Helpers de conversão Pillow → QPixmap
# ---------------------------------------------------------------------------

def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    """Converte PIL.Image (RGBA ou RGB) para QPixmap."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def _checkerboard(img: Image.Image, tile: int = 16) -> Image.Image:
    """Renderiza fundo xadrez sob imagem RGBA para visualizar transparência."""
    bg = Image.new("RGBA", img.size)
    cols = (img.width + tile - 1) // tile
    rows = (img.height + tile - 1) // tile
    light = (200, 200, 200, 255)
    dark = (140, 140, 140, 255)
    for r in range(rows):
        for c in range(cols):
            color = light if (r + c) % 2 == 0 else dark
            x0, y0 = c * tile, r * tile
            x1, y1 = min(x0 + tile, img.width), min(y0 + tile, img.height)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    bg.putpixel((x, y), color)
    bg.paste(img, mask=img.getchannel("A"))
    return bg


def _make_thumb(img: Image.Image, max_w: int = 800, max_h: int = 700) -> Image.Image:
    """Redimensiona imagem mantendo proporção para caber no preview."""
    ratio = min(1.0, max_w / img.width, max_h / img.height)
    if ratio >= 1.0:
        return img
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------
# Worker thread (processamento em background)
# ---------------------------------------------------------------------------

class _TotemWorker(QObject):
    """Worker que roda em QThread para não bloquear a UI."""
    status = Signal(str)
    log = Signal(str)
    finished_manual = Signal(object)   # DxfResult
    finished_batch = Signal(object)    # TotemBatchResult
    failed = Signal(str)

    def __init__(self, mode: str, request):
        super().__init__()
        self._mode = mode
        self._request = request

    def run(self) -> None:
        try:
            if self._mode == "manual":
                result = run_manual_totem(self._request, status_fn=self.log.emit)
                self.finished_manual.emit(result)
            else:
                result = run_batch_totem(
                    self._request,
                    log_fn=self.log.emit,
                    status_fn=self.status.emit,
                )
                self.finished_batch.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# Widget principal da tela Totem DXF
# ---------------------------------------------------------------------------

class TotemDxfWidget(QWidget, ScreenScaffold):
    """Tela de geração de DXF para totens com contorno extraído automaticamente."""

    def __init__(self):
        super().__init__()
        self._current_image: Optional[Image.Image] = None
        self._current_image_path: Optional[Path] = None
        self._batch_folder: Optional[Path] = None
        self._batch_output_folder: Optional[Path] = None
        self._preview_contour: Optional[np.ndarray] = None
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[_TotemWorker] = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        sidebar = self.wrap_sidebar(self._build_sidebar(), 390)
        main = self._build_main()
        layout.addWidget(sidebar, 0)
        layout.addWidget(main, 1)

    def _build_sidebar(self) -> QWidget:
        frame, layout = self.build_sidebar_frame()
        layout.addWidget(self.build_sidebar_header(
            "TOTEM DXF",
            "Extrai contorno da arte e gera DXF de corte em mm reais",
        ))

        # --- IMPORTAÇÃO ---
        layout.addWidget(self.section_label("IMPORTAÇÃO"))

        self._img_status = QLabel("Nenhuma imagem carregada")
        self._img_status.setObjectName("muted")
        self._img_status.setWordWrap(True)

        self._folder_status = QLabel("Nenhuma pasta selecionada")
        self._folder_status.setObjectName("muted")
        self._folder_status.setWordWrap(True)

        self._out_folder_status = QLabel("Padrão: subpasta 'dxf_output'")
        self._out_folder_status.setObjectName("muted")
        self._out_folder_status.setWordWrap(True)

        btn_img = QPushButton("Carregar Imagem (Preview)")
        btn_img.clicked.connect(self._load_preview_image)

        btn_folder = QPushButton("Selecionar Pasta do Lote")
        btn_folder.clicked.connect(self._select_batch_folder)

        btn_out = QPushButton("Pasta de Saída dos DXFs")
        btn_out.clicked.connect(self._select_output_folder)

        layout.addWidget(btn_img)
        layout.addWidget(self._img_status)
        layout.addWidget(btn_folder)
        layout.addWidget(self._folder_status)
        layout.addWidget(btn_out)
        layout.addWidget(self._out_folder_status)

        # --- CONFIGURAÇÕES ---
        layout.addWidget(self.section_label("CONFIGURAÇÕES"))

        config = QFrame()
        config.setObjectName("card")
        cfg_layout = QVBoxLayout(config)
        cfg_layout.setContentsMargins(14, 14, 14, 14)
        cfg_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self._dpi_input = self.add_field_card("DPI manual", "", "opcional", grid, 0, 0)
        self._dpi_input.setPlaceholderText("auto")
        self._bleed_input = self.add_field_card("Sangria", "3", "mm", grid, 0, 1)
        self._threshold_input = self.add_field_card("Threshold branco", "245", "0-255", grid, 1, 0)
        self._simplify_input = self.add_field_card("Simplificacao", "2.0", "0-100", grid, 1, 1)
        self._close_gap_input = self.add_field_card("Fechamento", "3.0", "% img", grid, 2, 0)
        self._edge_input = self.add_field_card("Sensib. borda", "30", "0-100", grid, 2, 1)

        # Dicas de uso
        tip = QLabel(
            "Fechamento: une partes separadas (orelhas, maos).\n"
            "Sensib. borda: menor = detecta tracos mais finos (arte branca)."
        )
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        grid.addWidget(tip, 3, 0, 1, 2)

        cfg_layout.addLayout(grid)

        self._preview_info = QLabel("Carregue uma imagem para ver o preview do contorno.")
        self._preview_info.setObjectName("muted")
        self._preview_info.setWordWrap(True)
        cfg_layout.addWidget(self._preview_info)

        btn_refresh = QPushButton("↻ Atualizar Preview do Contorno")
        btn_refresh.clicked.connect(self._refresh_contour_preview)
        cfg_layout.addWidget(btn_refresh)

        layout.addWidget(config)
        layout.addStretch(1)

        # --- AÇÃO ---
        self._btn_generate = QPushButton("GERAR DXF DO LOTE")
        self._btn_generate.setObjectName("accent")
        self._btn_generate.setMinimumHeight(48)
        self._btn_generate.clicked.connect(self._start_batch)
        layout.addWidget(self._btn_generate)

        return frame

    def _build_main(self) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        status_card, self._status_label, self._progress = self.build_status_panel("Aguardando...")
        self._status_label.setObjectName("muted")
        layout.addWidget(status_card)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_preview_tab(), "Preview do Contorno")
        self._tabs.addTab(self._build_log_tab(), "Log do Lote")
        layout.addWidget(self._tabs, 1)

        return frame

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview_widget = ZoomablePreviewWidget(
            placeholder_text="Carregue uma imagem e clique em 'Atualizar Preview do Contorno'"
        )
        layout.addWidget(self.preview_widget)
        return widget

    def _build_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self._batch_log = self.build_log_output()
        self._batch_log.setPlainText("O log do processamento em lote aparecerá aqui.\n")
        layout.addWidget(self._batch_log)
        return widget

    # ------------------------------------------------------------------
    # Leitura de parâmetros
    # ------------------------------------------------------------------

    def _read_options(self) -> TotemDxfOptions:
        def _float(widget: QLineEdit, default: float) -> float:
            try:
                return float(widget.text().replace(",", "."))
            except ValueError:
                return default

        def _int_or_none(widget: QLineEdit) -> Optional[int]:
            raw = widget.text().strip()
            if not raw:
                return None
            try:
                val = int(float(raw))
                return val if val > 0 else None
            except ValueError:
                return None

        def _int(widget: QLineEdit, default: int) -> int:
            try:
                return max(0, int(float(widget.text().replace(",", "."))))
            except ValueError:
                return default

        return TotemDxfOptions(
            white_threshold=_int(self._threshold_input, 245),
            softness=18,
            bleed_mm=max(0.0, _float(self._bleed_input, 3.0)),
            simplify_eps=max(0.0, _float(self._simplify_input, 2.0)),
            close_gap_pct=max(0.5, _float(self._close_gap_input, 3.0)),
            edge_sensitivity=max(5, min(100, _int(self._edge_input, 30))),
            dpi_override=_int_or_none(self._dpi_input),
            layer_name="CORTE",
        )

    # ------------------------------------------------------------------
    # Ações de importação
    # ------------------------------------------------------------------

    def _load_preview_image(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Carregar imagem de preview",
            "", "Imagens (*.jpg *.jpeg *.png *.webp *.tif *.tiff)"
        )
        if not path_str:
            return
        try:
            self._current_image_path = Path(path_str)
            self._current_image = Image.open(path_str)
            self._current_image = ImageOps.exif_transpose(self._current_image)
            self._img_status.setText(f"✓ {self._current_image_path.name}")
            self._refresh_contour_preview()
        except Exception as exc:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir a imagem:\n{exc}")

    def _select_batch_folder(self) -> None:
        path_str = QFileDialog.getExistingDirectory(self, "Selecionar pasta com totens")
        if not path_str:
            return
        self._batch_folder = Path(path_str)
        self._folder_status.setText(str(self._batch_folder))
        # Definir saída padrão como subpasta
        self._batch_output_folder = self._batch_folder / "dxf_output"
        self._out_folder_status.setText(str(self._batch_output_folder))

    def _select_output_folder(self) -> None:
        path_str = QFileDialog.getExistingDirectory(self, "Selecionar pasta de saída dos DXFs")
        if not path_str:
            return
        self._batch_output_folder = Path(path_str)
        self._out_folder_status.setText(str(self._batch_output_folder))

    # ------------------------------------------------------------------
    # Preview do contorno
    # ------------------------------------------------------------------

    def _refresh_contour_preview(self) -> None:
        if self._current_image is None:
            QMessageBox.information(self, "Info", "Carregue uma imagem primeiro.")
            return

        try:
            opts = self._read_options()
            img = self._current_image
            dpi = _get_dpi(img, opts.dpi_override)

            base_contour, bleed_contour, _mask = extract_contour_pair(
                img,
                white_threshold=opts.white_threshold,
                softness=opts.softness,
                simplify_eps=opts.simplify_eps,
                close_gap_pct=opts.close_gap_pct,
                edge_sensitivity=opts.edge_sensitivity,
                bleed_mm=opts.bleed_mm,
                dpi=dpi,
            )

            # Para preview de alta fidelidade que suporta zoom avançado
            thumb = _make_thumb(img, max_w=2400, max_h=2400)
            scale_x = thumb.width / img.width
            scale_y = thumb.height / img.height

            # Imagem base em QPixmap
            pixmap = _pil_to_qpixmap(thumb)

            contour_to_use = bleed_contour if opts.bleed_mm > 0 else base_contour

            if contour_to_use is not None and len(contour_to_use) >= 2:
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

                # Se houver sangria, desenha primeiro a borda original da arte (tracejada em azul suave)
                if opts.bleed_mm > 0 and base_contour is not None and len(base_contour) >= 2:
                    base_pen = QPen(QColor("#60A5FA"))  # Azul claro
                    base_pen.setWidth(2)
                    base_pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(base_pen)
                    base_pts = [(int(pt[0][0] * scale_x), int(pt[0][1] * scale_y)) for pt in base_contour]
                    for i in range(len(base_pts)):
                        p1 = base_pts[i]
                        p2 = base_pts[(i + 1) % len(base_pts)]
                        painter.drawLine(p1[0], p1[1], p2[0], p2[1])

                # Desenha o contorno de corte DXF principal (verde turquesa sólido)
                cut_pen = QPen(QColor("#00C2A8"))
                cut_pen.setWidth(3)
                painter.setPen(cut_pen)

                pts = [(int(pt[0][0] * scale_x), int(pt[0][1] * scale_y)) for pt in contour_to_use]
                for i in range(len(pts)):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i + 1) % len(pts)]
                    painter.drawLine(x1, y1, x2, y2)

                # Marcar pontos de vértice (vermelho)
                pen_points = QPen(QColor("#FF6B6B"))
                pen_points.setWidth(6)
                painter.setPen(pen_points)
                for x, y in pts:
                    painter.drawPoint(x, y)

                painter.end()

                # Dimensões do corte real em milímetros
                xs = [p[0][0] for p in contour_to_use]
                ys = [p[0][1] for p in contour_to_use]
                w_mm = ((max(xs) - min(xs)) / dpi) * 25.4
                h_mm = ((max(ys) - min(ys)) / dpi) * 25.4

                info = (
                    f"Contorno: {len(contour_to_use)} pontos | "
                    f"DPI: {dpi} | "
                    f"Corte DXF: {w_mm:.1f} × {h_mm:.1f} mm"
                )
                if opts.bleed_mm > 0:
                    info += f" (Sangria morfológica: {opts.bleed_mm:.1f} mm)"

                self._preview_info.setText(info)
                self.preview_widget.set_pixmap(pixmap, info_text=info)
            else:
                self._preview_info.setText(
                    "⚠ Nenhum contorno encontrado. Ajuste o threshold de branco."
                )
                self.preview_widget.clear("Nenhum contorno encontrado. Ajuste o threshold de branco.")

            self._tabs.setCurrentIndex(0)

        except Exception as exc:
            QMessageBox.critical(self, "Erro no Preview", str(exc))

    # ------------------------------------------------------------------
    # Processamento em lote
    # ------------------------------------------------------------------

    def _start_batch(self) -> None:
        if self._batch_folder is None:
            QMessageBox.warning(self, "Aviso", "Selecione a pasta com os arquivos de totem primeiro.")
            return

        if self._batch_output_folder is None:
            self._batch_output_folder = self._batch_folder / "dxf_output"

        if self._worker_thread is not None:
            return  # já rodando

        opts = self._read_options()
        request = TotemBatchRequest(
            folder_path=self._batch_folder,
            output_folder=self._batch_output_folder,
            options=opts,
        )

        self._batch_log.setPlainText("")
        self._tabs.setCurrentIndex(1)
        self._set_running(True)

        self._worker_thread = QThread(self)
        self._worker = _TotemWorker("batch", request)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.status.connect(self._status_label.setText)
        self._worker.log.connect(self._append_log)
        self._worker.finished_batch.connect(self._on_batch_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished_batch.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)

        self._worker_thread.start()

    def _append_log(self, text: str) -> None:
        self._batch_log.appendPlainText(text)

    def _on_batch_finished(self, result: TotemBatchResult) -> None:
        self._set_running(False)
        msg = (
            f"Lote concluído!\n\n"
            f"  ✓  {result.success_count} DXF(s) gerado(s)\n"
        )
        if result.error_count > 0:
            msg += f"  ✗  {result.error_count} erro(s)\n"
        if self._batch_output_folder:
            msg += f"\nSalvo em:\n{self._batch_output_folder}"
        QMessageBox.information(self, "Concluído", msg)

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self._append_log(f"\nErro crítico: {message}")
        QMessageBox.critical(self, "Erro", message)

    def _cleanup_worker(self) -> None:
        if self._worker:
            self._worker.deleteLater()
        if self._worker_thread:
            self._worker_thread.deleteLater()
        self._worker = None
        self._worker_thread = None

    def _set_running(self, running: bool) -> None:
        self._btn_generate.setEnabled(not running)
        if running:
            self._progress.setRange(0, 0)
            self._status_label.setText("Processando...")
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)

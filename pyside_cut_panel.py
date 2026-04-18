from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont, QPixmap
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
    QProgressBar,
    QScrollArea,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cut_panel_service import (
    CutBatchRequest,
    CutManualRequest,
    image_dimensions_cm,
    resolve_dpi,
    run_batch_cut,
    run_manual_cut,
)
from pyside_rolo_packer import _checkerboard_image, pil_to_qpixmap


@dataclass(slots=True)
class ManualPayload:
    request: CutManualRequest


@dataclass(slots=True)
class BatchPayload:
    request: CutBatchRequest


class CutWorker(QObject):
    status = Signal(str)
    log = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, payload: ManualPayload | BatchPayload):
        super().__init__()
        self._payload = payload

    def run(self) -> None:
        try:
            if isinstance(self._payload, ManualPayload):
                result = run_manual_cut(self._payload.request, status_fn=self.status.emit)
            else:
                result = run_batch_cut(
                    self._payload.request,
                    log_fn=self.log.emit,
                    status_fn=self.status.emit,
                )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class CutPanelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.template_image: Image.Image | None = None
        self.original_image: Image.Image | None = None
        self.image_path: str = ""
        self.batch_folder: str = ""
        self.pad_cm = 1.0
        self._worker_thread: QThread | None = None
        self._worker: CutWorker | None = None
        self._preview_pixmap: QPixmap | None = None
        self._current_mode: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        sidebar = self._wrap_sidebar(self._build_sidebar(), 376)
        main = self._build_main()
        layout.addWidget(sidebar, 0)
        layout.addWidget(main, 1)

    def _wrap_sidebar(self, widget: QWidget, width: int) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(width)
        scroll.setWidget(widget)
        return scroll

    def _build_sidebar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setFixedWidth(360)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("PAINEL CUT")
        title.setObjectName("title")
        title.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        subtitle = QLabel("Corte de paineis com gabarito e largura de placa")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        layout.addWidget(self._section_label("IMPORTACAO"))
        self.template_status = QLabel("Nenhum gabarito")
        self.template_status.setObjectName("muted")
        self.image_status = QLabel("Nenhuma imagem")
        self.image_status.setObjectName("muted")
        self.batch_status = QLabel("Nenhuma pasta de lote")
        self.batch_status.setObjectName("muted")

        btn_template = QPushButton("Carregar Gabarito")
        btn_template.clicked.connect(self._load_template)
        btn_image = QPushButton("Carregar Imagem Principal")
        btn_image.clicked.connect(self._load_image)
        btn_batch = QPushButton("Selecionar Pasta do Lote")
        btn_batch.clicked.connect(self._select_batch_folder)
        layout.addWidget(btn_template)
        layout.addWidget(self.template_status)
        layout.addWidget(btn_image)
        layout.addWidget(self.image_status)
        layout.addWidget(btn_batch)
        layout.addWidget(self.batch_status)

        rotate_row = QHBoxLayout()
        btn_left = QPushButton("Rotacionar -90")
        btn_left.clicked.connect(lambda: self._rotate_image(-90))
        btn_right = QPushButton("Rotacionar +90")
        btn_right.clicked.connect(lambda: self._rotate_image(90))
        rotate_row.addWidget(btn_left)
        rotate_row.addWidget(btn_right)
        layout.addLayout(rotate_row)

        layout.addWidget(self._section_label("CONFIGURACOES"))
        config = QFrame()
        config.setObjectName("card")
        config_layout = QVBoxLayout(config)
        config_layout.setContentsMargins(14, 14, 14, 14)
        config_layout.setSpacing(12)
        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(10)
        field_grid.setVerticalSpacing(10)
        self.measure_input = self._field_card("Largura da placa", "150", "cm", field_grid, 0, 0)
        self.dpi_input = self._field_card("DPI manual", "", "opcional", field_grid, 0, 1)
        config_layout.addLayout(field_grid)
        self.dpi_info = QLabel("DPI em uso: automatico")
        self.dpi_info.setObjectName("muted")
        self.dpi_input.textChanged.connect(self._refresh_summary)
        config_layout.addWidget(self.dpi_info)

        self.summary_label = QLabel("Placa alvo: - | Total calculado: -")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("muted")
        config_layout.addWidget(self.summary_label)

        self.guides_note = QLabel("Observacao: a configuracao manual de guias do canvas antigo ainda nao foi migrada. Nesta fase, o corte usa a largura da placa.")
        self.guides_note.setWordWrap(True)
        self.guides_note.setObjectName("muted")
        config_layout.addWidget(self.guides_note)
        layout.addWidget(config)

        layout.addStretch(1)

        self.process_manual_btn = QPushButton("PROCESSAR CORTE")
        self.process_manual_btn.setObjectName("accent")
        self.process_manual_btn.setMinimumHeight(46)
        self.process_manual_btn.clicked.connect(self._process_manual)
        self.process_batch_btn = QPushButton("PROCESSAR LOTE")
        self.process_batch_btn.clicked.connect(self._process_batch)
        layout.addWidget(self.process_manual_btn)
        layout.addWidget(self.process_batch_btn)
        return frame

    def _build_main(self) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        self.status_label = QLabel("Aguardando...")
        self.status_label.setObjectName("muted")
        self.status_label.setFont(QFont("Courier New", 11))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(220)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.progress, 0)
        layout.addWidget(status_card)

        tabs = QTabWidget()
        tabs.addTab(self._build_preview_tab(), "Preview")
        tabs.addTab(self._build_info_tab(), "Info")
        tabs.addTab(self._build_batch_tab(), "Lote")
        self.tabs = tabs
        layout.addWidget(tabs, 1)
        return frame

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(16, 16, 16, 16)
        self.preview_label = QLabel("Carregue uma imagem para visualizar o painel.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(340)
        self.preview_label.setObjectName("muted")
        self.preview_layout.addWidget(self.preview_label)
        self.preview_scroll.setWidget(self.preview_container)
        layout.addWidget(self.preview_scroll)
        return widget

    def _build_info_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        self.info_text = QLabel("Sem imagem carregada.")
        self.info_text.setWordWrap(True)
        card_layout.addWidget(self.info_text)
        layout.addWidget(card)
        return widget

    def _build_batch_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.batch_log = QPlainTextEdit()
        self.batch_log.setReadOnly(True)
        self.batch_log.setPlainText("O lote vai listar aqui cada arquivo processado.\n")
        layout.addWidget(self.batch_log)
        return widget

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        return label

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        label.setFont(QFont("Courier New", 10))
        return label

    def _field_card(self, label_text: str, default: str, suffix: str, grid: QGridLayout, row: int, column: int) -> QLineEdit:
        card = QFrame()
        card.setObjectName("fieldCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)
        label = label_text if not suffix else f"{label_text} ({suffix})"
        card_layout.addWidget(self._field_label(label))
        entry = QLineEdit()
        entry.setObjectName("fieldInput")
        entry.setText(default)
        entry.setMinimumHeight(36)
        card_layout.addWidget(entry)
        grid.addWidget(card, row, column)
        return entry

    def _load_template(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Carregar gabarito", "", "Imagens (*.png *.jpg *.jpeg *.tif *.tiff)")
        if not file_path:
            return
        self.template_image = Image.open(file_path)
        self.template_status.setText(f"OK {os.path.basename(file_path)[:24]}")

    def _load_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Carregar imagem principal", "", "Imagens (*.png *.jpg *.jpeg *.tif *.tiff)")
        if not file_path:
            return
        self.image_path = file_path
        self.original_image = Image.open(file_path)
        self.image_status.setText(f"OK {os.path.basename(file_path)[:24]}")
        self._refresh_summary()
        self._show_preview(self.original_image)

    def _select_batch_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Selecionar pasta para corte em lote")
        if not path:
            return
        self.batch_folder = path
        self.batch_status.setText(path)
        self._append_batch_log(f"Pasta selecionada: {path}")

    def _rotate_image(self, angle: int) -> None:
        if self.original_image is None:
            QMessageBox.warning(self, "Aviso", "Carregue a imagem principal primeiro.")
            return
        self.original_image = self.original_image.rotate(angle, expand=True)
        self._refresh_summary()
        self._show_preview(self.original_image)

    def _manual_dpi(self) -> int | None:
        raw = self.dpi_input.text().strip()
        if not raw:
            return None
        try:
            value = int(float(raw.replace(",", ".")))
        except ValueError:
            return None
        return value if value > 0 else None

    def _plate_width(self) -> float:
        raw = self.measure_input.text().strip()
        if not raw:
            raise ValueError("Digite a largura da placa em cm.")
        try:
            value = float(raw.replace(",", "."))
        except ValueError as exc:
            raise ValueError("A largura da placa deve ser um numero em cm.") from exc
        if value <= 0:
            raise ValueError("A largura da placa deve ser maior que zero.")
        return value

    def _refresh_summary(self) -> None:
        if self.original_image is None:
            self.dpi_info.setText("DPI em uso: automatico")
            self.summary_label.setText("Placa alvo: - | Total calculado: -")
            self.info_text.setText("Sem imagem carregada.")
            return

        manual_dpi = self._manual_dpi()
        dpi_x = resolve_dpi(self.original_image, manual_dpi)
        self.dpi_info.setText(f"DPI em uso: {dpi_x} ({'manual' if manual_dpi else 'imagem'})")

        width_cm, height_cm = image_dimensions_cm(self.original_image, manual_dpi)
        try:
            plate_width = self._plate_width()
            total = max(1, int(width_cm // plate_width) + (1 if width_cm % plate_width else 0))
            summary = f"Placa alvo: {plate_width:.1f} cm | Total calculado: {total} placa(s)"
        except ValueError:
            summary = "Placa alvo: - | Total calculado: -"

        self.summary_label.setText(summary)
        self.info_text.setText(
            f"Arquivo: {os.path.basename(self.image_path) if self.image_path else '-'}\n"
            f"Dimensoes: {self.original_image.width}×{self.original_image.height} px\n"
            f"Tamanho real: {width_cm:.1f} × {height_cm:.1f} cm\n"
            f"DPI considerado: {dpi_x}\n"
            f"Padding fixo: {self.pad_cm:.1f} cm"
        )

    def _process_manual(self) -> None:
        if self.original_image is None:
            QMessageBox.warning(self, "Aviso", "Carregue a imagem principal primeiro.")
            return
        if self.template_image is None:
            QMessageBox.warning(self, "Aviso", "Carregue o gabarito primeiro.")
            return

        try:
            request = CutManualRequest(
                original_image=self.original_image.copy(),
                template_image=self.template_image.copy(),
                image_path=self.image_path,
                plate_width_cm=self._plate_width(),
                pad_cm=self.pad_cm,
                dpi_override=self._manual_dpi(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Erro", str(exc))
            return

        self._start_worker("manual", ManualPayload(request))

    def _process_batch(self) -> None:
        if self.template_image is None:
            QMessageBox.warning(self, "Aviso", "Carregue o gabarito primeiro.")
            return
        if not self.batch_folder:
            QMessageBox.warning(self, "Aviso", "Selecione uma pasta para o lote.")
            return

        try:
            request = CutBatchRequest(
                folder_path=self.batch_folder,
                template_image=self.template_image.copy(),
                plate_width_cm=self._plate_width(),
                pad_cm=self.pad_cm,
                dpi_override=self._manual_dpi(),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "Erro", str(exc))
            return

        self._append_batch_log("Preparando lote...")
        self.tabs.setCurrentIndex(2)
        self._start_worker("batch", BatchPayload(request))

    def _start_worker(self, mode: str, payload: ManualPayload | BatchPayload) -> None:
        if self._worker_thread is not None:
            return
        self._current_mode = mode
        self._set_running(True)
        self._worker_thread = QThread(self)
        self._worker = CutWorker(payload)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.status.connect(self._set_status)
        self._worker.log.connect(self._append_batch_log)
        self._worker.finished.connect(self._handle_finished)
        self._worker.failed.connect(self._handle_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _append_batch_log(self, text: str) -> None:
        self.batch_log.appendPlainText(text)

    def _handle_finished(self, result: object) -> None:
        if self._current_mode == "manual":
            output_dir = result.output_dir
            total_parts = result.total_parts
            self._set_status("Corte concluido.")
            QMessageBox.information(self, "Sucesso", f"Processo concluido.\n\nAs {total_parts} partes foram salvas em:\n{output_dir}")
        else:
            total_files = len(result)
            self._set_status("Lote concluido.")
            QMessageBox.information(self, "Sucesso", f"Lote concluido com {total_files} arquivo(s).")
        self._set_running(False)

    def _handle_failed(self, message: str) -> None:
        self._set_status("Erro durante o processamento.")
        self._append_batch_log(f"Erro: {message}")
        QMessageBox.critical(self, "Erro", message)
        self._set_running(False)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
        self._worker = None
        self._worker_thread = None
        self._current_mode = None

    def _set_running(self, running: bool) -> None:
        self.process_manual_btn.setEnabled(not running)
        self.process_batch_btn.setEnabled(not running)
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

    def _show_preview(self, img: Image.Image) -> None:
        max_w = 820
        ratio = min(1.0, max_w / img.width) if img.width > 0 else 1.0
        thumb = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)
        pixmap = pil_to_qpixmap(_checkerboard_image(thumb))
        self._preview_pixmap = pixmap
        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...algorithms.finishing import process_finishing_folder
from ..common import ScreenScaffold


@dataclass(slots=True)
class FinishingRequest:
    folder: Path
    output_name: str
    dpi_override: int | None
    side_mode: str


class FinishingWorker(QObject):
    status = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, request: FinishingRequest):
        super().__init__()
        self._request = request

    def run(self) -> None:
        try:
            self.status.emit("Processando acabamento em lote...")
            results = process_finishing_folder(
                folder=self._request.folder,
                output_name=self._request.output_name,
                dpi_override=self._request.dpi_override,
                side_mode=self._request.side_mode,
            )
            self.finished.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))


class ArtFinisherWidget(QWidget, ScreenScaffold):
    def __init__(self):
        super().__init__()
        self._folder: Path | None = None
        self._worker_thread: QThread | None = None
        self._worker: FinishingWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        layout.addWidget(self.wrap_sidebar(self._build_sidebar(), 376), 0)
        layout.addWidget(self._build_main(), 1)

    def _build_sidebar(self) -> QWidget:
        frame, layout = self.build_sidebar_frame()
        layout.addWidget(self.build_sidebar_header("ACABAMENTO", "Adiciona contorno, pad e nome do cliente em lote"))

        layout.addWidget(self.section_label("PASTA DE IMAGENS"))
        self.folder_label = QLabel("Nenhuma pasta selecionada")
        self.folder_label.setObjectName("muted")
        self.folder_label.setWordWrap(True)
        layout.addWidget(self.folder_label)

        pick_button = QPushButton("Selecionar Pasta")
        pick_button.clicked.connect(self._choose_folder)
        layout.addWidget(pick_button)

        layout.addWidget(self.section_label("CONFIGURACAO"))
        config = QFrame()
        config.setObjectName("card")
        config_layout = QVBoxLayout(config)
        config_layout.setContentsMargins(14, 14, 14, 14)
        config_layout.setSpacing(12)

        config_layout.addWidget(self.field_label("Lado do pad"))
        self.side_group = QButtonGroup(self)
        self.side_radios = {}
        for text, value in (("Automatico", "auto"), ("Inferior", "bottom"), ("Direita", "right")):
            radio = QRadioButton(text)
            if value == "auto":
                radio.setChecked(True)
            self.side_group.addButton(radio)
            self.side_radios[value] = radio
            config_layout.addWidget(radio)

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(10)
        field_grid.setVerticalSpacing(10)
        self.dpi_input = self.add_field_card("DPI manual", "", "opcional", field_grid, 0, 0)
        self.output_input = self.add_field_card("Subpasta de saida", "ACABAMENTO", "", field_grid, 0, 1)
        config_layout.addLayout(field_grid)

        help_label = QLabel("Regra atual: 155x155 usa pad 2 cm. Outras medidas usam pad 1 cm. O nome sai do prefixo antes do '-' ou do primeiro espaco.")
        help_label.setObjectName("muted")
        help_label.setWordWrap(True)
        config_layout.addWidget(help_label)
        layout.addWidget(config)

        layout.addStretch(1)
        self.run_button = QPushButton("PROCESSAR ACABAMENTO")
        self.run_button.setObjectName("accent")
        self.run_button.setMinimumHeight(46)
        self.run_button.clicked.connect(self._run)
        layout.addWidget(self.run_button)
        return frame

    def _build_main(self) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        status_card, self.status_label, self.progress = self.build_status_panel("Aguardando...")
        layout.addWidget(status_card)

        self.log_output = self.build_log_output()
        layout.addWidget(self.log_output, 1)
        return frame

    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Selecionar pasta de imagens")
        if not selected:
            return
        self._folder = Path(selected)
        self.folder_label.setText(selected)
        self._append_log(f"Pasta selecionada: {selected}\n")

    def _selected_value(self, radios: dict[str, QRadioButton]) -> str:
        for value, radio in radios.items():
            if radio.isChecked():
                return value
        return next(iter(radios))

    def _run(self) -> None:
        if self._worker_thread is not None:
            return
        if self._folder is None:
            QMessageBox.critical(self, "Erro", "Selecione uma pasta primeiro.")
            return

        dpi_override = None
        raw_dpi = self.dpi_input.text().strip()
        if raw_dpi:
            try:
                dpi_override = int(float(raw_dpi.replace(",", ".")))
            except ValueError:
                QMessageBox.critical(self, "Erro", "O DPI manual deve ser um numero valido.")
                return
            if dpi_override <= 0:
                QMessageBox.critical(self, "Erro", "O DPI manual deve ser maior que zero.")
                return

        request = FinishingRequest(
            folder=self._folder,
            output_name=self.output_input.text().strip() or "ACABAMENTO",
            dpi_override=dpi_override,
            side_mode=self._selected_value(self.side_radios),
        )
        self.log_output.clear()
        self._set_running(True)
        self._worker_thread = QThread(self)
        self._worker = FinishingWorker(request)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.status.connect(self._set_status)
        self._worker.finished.connect(self._handle_finished)
        self._worker.failed.connect(self._handle_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()

    def _append_log(self, text: str) -> None:
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_output.setTextCursor(cursor)
        self.log_output.insertPlainText(text)
        self.log_output.ensureCursorVisible()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _handle_finished(self, results: list[dict]) -> None:
        for item in results:
            self._append_log(
                f"OK {item['file']} -> cliente: {item['client_name']} | pad: {item['pad_cm']:.1f} cm | lado: {item['pad_side']}\n"
            )
        self._set_status(f"{len(results)} arquivo(s) processado(s).")
        self._set_running(False)

    def _handle_failed(self, message: str) -> None:
        self._set_status("Erro no processamento.")
        QMessageBox.critical(self, "Erro", message)
        self._set_running(False)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
        self._worker = None
        self._worker_thread = None

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.run_button.setText("Processando..." if running else "PROCESSAR ACABAMENTO")
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

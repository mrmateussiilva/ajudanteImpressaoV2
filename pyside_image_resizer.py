from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from image_resize_processing import process_resize_folder


@dataclass(slots=True)
class ResizeRequest:
    folder: Path
    mode: str
    target_value: float
    output_name: str
    destination_mode: str


class ResizeWorker(QObject):
    log = Signal(str)
    status = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, request: ResizeRequest):
        super().__init__()
        self._request = request

    def run(self) -> None:
        try:
            self.status.emit("Processando imagens...")
            self.log.emit(f"Modo: {self._request.mode}\n")
            self.log.emit(f"Valor alvo: {self._request.target_value}\n")
            destination = "sobrescrever originais" if self._request.destination_mode == "overwrite" else str(self._request.folder / self._request.output_name)
            self.log.emit(f"Destino: {destination}\n\n")
            results = process_resize_folder(
                self._request.folder,
                self._request.mode,
                self._request.target_value,
                self._request.output_name,
                self._request.destination_mode,
            )
            self.finished.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))


class ImageResizerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._folder: Path | None = None
        self._worker_thread: QThread | None = None
        self._worker: ResizeWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        layout.addWidget(self._wrap_sidebar(self._build_sidebar(), 376), 0)
        layout.addWidget(self._build_main(), 1)

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

        header = QFrame()
        header.setObjectName("panel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("REDIMENSIONAR")
        title.setObjectName("title")
        title.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        subtitle = QLabel("Reduz ou amplia em lote mantendo a proporcao")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        layout.addWidget(self._section_label("PASTA DE IMAGENS"))
        self.folder_label = QLabel("Nenhuma pasta selecionada")
        self.folder_label.setObjectName("muted")
        self.folder_label.setWordWrap(True)
        layout.addWidget(self.folder_label)

        pick_button = QPushButton("Selecionar Pasta")
        pick_button.clicked.connect(self._choose_folder)
        layout.addWidget(pick_button)

        layout.addWidget(self._section_label("CONFIGURACAO"))
        config = QFrame()
        config.setObjectName("card")
        config_layout = QVBoxLayout(config)
        config_layout.setContentsMargins(14, 14, 14, 14)
        config_layout.setSpacing(12)

        mode_label = self._field_label("Modo de redimensionamento")
        config_layout.addWidget(mode_label)
        self.mode_group = QButtonGroup(self)
        self.mode_radios = {}
        for text, value in (("Percentual", "percent"), ("Largura em cm", "width_cm"), ("Largura em px", "width_px")):
            radio = QRadioButton(text)
            if value == "percent":
                radio.setChecked(True)
            radio.toggled.connect(self._refresh_mode_labels)
            self.mode_group.addButton(radio)
            self.mode_radios[value] = radio
            config_layout.addWidget(radio)

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(10)
        field_grid.setVerticalSpacing(10)
        self.value_input = self._field_card("Valor alvo", "25", "%", field_grid, 0, 0)
        self.output_input = self._field_card("Subpasta de saida", "REDIMENSIONADAS", "", field_grid, 0, 1)
        config_layout.addLayout(field_grid)

        config_layout.addWidget(self._field_label("Destino"))
        self.destination_group = QButtonGroup(self)
        self.destination_radios = {}
        for text, value in (("Salvar em subpasta", "subfolder"), ("Sobrescrever originais", "overwrite")):
            radio = QRadioButton(text)
            if value == "subfolder":
                radio.setChecked(True)
            radio.toggled.connect(self._refresh_destination_ui)
            self.destination_group.addButton(radio)
            self.destination_radios[value] = radio
            config_layout.addWidget(radio)

        self.help_label = QLabel()
        self.help_label.setObjectName("muted")
        self.help_label.setWordWrap(True)
        config_layout.addWidget(self.help_label)
        self._refresh_mode_labels()
        self._refresh_destination_ui()
        layout.addWidget(config)

        layout.addStretch(1)
        self.run_button = QPushButton("PROCESSAR LOTE")
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

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        self.status_label = QLabel("Aguardando...")
        self.status_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(220)
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.progress)
        layout.addWidget(status_card)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Courier New", 10))
        layout.addWidget(self.log_output, 1)
        return frame

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
        field_label = self._field_label(label)
        card_layout.addWidget(field_label)
        entry = QLineEdit()
        entry.setObjectName("fieldInput")
        entry.setText(default)
        entry.setMinimumHeight(36)
        card_layout.addWidget(entry)
        grid.addWidget(card, row, column)
        if row == 0 and column == 0:
            self._value_field_label = field_label
        return entry

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

    def _refresh_mode_labels(self) -> None:
        mode = self._selected_value(self.mode_radios)
        mapping = {
            "percent": ("Valor alvo (%)", "Exemplo: 25 reduz para 25% do tamanho atual.", "25"),
            "width_cm": ("Largura final (cm)", "Usa o DPI da imagem para converter a largura alvo em cm.", "50"),
            "width_px": ("Largura final (px)", "Define uma largura final em pixels e mantem a proporcao.", "1000"),
        }
        label, help_text, default = mapping[mode]
        self._value_field_label.setText(label)
        if not self.value_input.hasFocus():
            self.value_input.setText(default)
        self.help_label.setText(help_text)

    def _refresh_destination_ui(self) -> None:
        is_subfolder = self._selected_value(self.destination_radios) == "subfolder"
        self.output_input.parentWidget().setVisible(is_subfolder)

    def _run(self) -> None:
        if self._worker_thread is not None:
            return
        if self._folder is None:
            QMessageBox.critical(self, "Erro", "Selecione uma pasta primeiro.")
            return
        try:
            target_value = float(self.value_input.text().replace(",", "."))
        except ValueError:
            QMessageBox.critical(self, "Erro", "Informe um valor valido.")
            return
        if target_value <= 0:
            QMessageBox.critical(self, "Erro", "O valor deve ser maior que zero.")
            return

        destination_mode = self._selected_value(self.destination_radios)
        if destination_mode == "overwrite":
            confirmed = QMessageBox.question(
                self,
                "Confirmar sobrescrita",
                "Isso vai sobrescrever as imagens originais da pasta selecionada. Deseja continuar?",
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return

        request = ResizeRequest(
            folder=self._folder,
            mode=self._selected_value(self.mode_radios),
            target_value=target_value,
            output_name=self.output_input.text().strip() or "REDIMENSIONADAS",
            destination_mode=destination_mode,
        )
        self.log_output.clear()
        self._set_running(True)
        self._worker_thread = QThread(self)
        self._worker = ResizeWorker(request)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
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
        for result in results:
            self._append_log(f"OK {result['file']} -> {result['width']}x{result['height']}px (escala {result['scale']:.3f})\n")
        self._append_log("\nLote finalizado.\n")
        self._set_status("Concluido.")
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
        self.run_button.setText("Processando..." if running else "PROCESSAR LOTE")
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

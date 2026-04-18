from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from roller_pack_service import RollerPackRequest, RollerPackResult, run_roll_packer


def _checkerboard_image(img: Image.Image, block: int = 16) -> Image.Image:
    base = img.convert("RGBA")
    checker = Image.new("RGBA", base.size, (30, 30, 30, 255))
    for cy in range(0, base.height, block):
        for cx in range(0, base.width, block):
            if (cx // block + cy // block) % 2 == 0:
                x1 = min(cx + block, base.width)
                y1 = min(cy + block, base.height)
                tile = Image.new("RGBA", (x1 - cx, y1 - cy), (50, 50, 50, 255))
                checker.alpha_composite(tile, (cx, cy))
    return Image.alpha_composite(checker, base)


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


@dataclass(slots=True)
class DebugPayload:
    image_items: list[dict]
    debug_limit: int


class RollPackWorker(QObject):
    log = Signal(str, str)
    status = Signal(str)
    debug = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, request: RollerPackRequest):
        super().__init__()
        self._request = request

    def run(self) -> None:
        try:
            result = run_roll_packer(
                request=self._request,
                log_fn=lambda text, level="info": self.log.emit(text, level),
                status_fn=lambda text: self.status.emit(text),
                debug_fn=lambda items, limit: self.debug.emit(DebugPayload(items, limit)),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class RoloPackerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._folder: Path | None = None
        self._worker_thread: QThread | None = None
        self._worker: RollPackWorker | None = None
        self._preview_pixmap: QPixmap | None = None
        self._debug_pixmaps: list[QPixmap] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        sidebar = self._build_sidebar()
        main_panel = self._build_main()
        layout.addWidget(sidebar, 0)
        layout.addWidget(main_panel, 1)

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
        header_layout.setSpacing(4)

        title = QLabel("ROLO PACKER")
        title.setObjectName("title")
        title.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        subtitle = QLabel("Layout horizontal para impressao em rolo")
        subtitle.setObjectName("subtitle")
        subtitle.setFont(QFont("Courier New", 10))
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        layout.addWidget(self._section_label("PASTA DE IMAGENS"))
        self.folder_label = QLabel("Nenhuma pasta selecionada")
        self.folder_label.setWordWrap(True)
        self.folder_label.setObjectName("muted")
        self.folder_label.setFont(QFont("Courier New", 10))
        layout.addWidget(self.folder_label)

        pick_button = QPushButton("Selecionar Pasta")
        pick_button.clicked.connect(self._choose_folder)
        layout.addWidget(pick_button)

        layout.addWidget(self._section_label("CONFIGURACOES"))
        config_box = QGroupBox()
        config_layout = QVBoxLayout(config_box)
        config_layout.setContentsMargins(14, 14, 14, 14)
        config_layout.setSpacing(12)

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(10)
        field_grid.setVerticalSpacing(10)

        self.width_input = self._field_card("Largura do rolo", "125", "cm", field_grid, 0, 0)
        self.margin_input = self._field_card("Margem nas bordas", "0.5", "cm", field_grid, 0, 1)
        self.spacing_input = self._field_card("Espacamento", "0.3", "cm", field_grid, 1, 0)
        self.threshold_input = self._field_card("Threshold branco", "245", "", field_grid, 1, 1)
        self.step_input = self._field_card("Precisao do encaixe", "8", "px", field_grid, 2, 0)
        self.row_height_input = self._field_card("Altura base", "18", "cm", field_grid, 2, 1)
        config_layout.addLayout(field_grid)

        config_layout.addWidget(self._field_label("Perfil de performance"))
        self.performance_group = QButtonGroup(self)
        self.performance_radios = {}
        for text, value in (("Qualidade", "quality"), ("Balanceado", "balanced"), ("Rapido", "fast")):
            radio = QRadioButton(text)
            if value == "balanced":
                radio.setChecked(True)
            self.performance_group.addButton(radio)
            self.performance_radios[value] = radio
            config_layout.addWidget(radio)

        config_layout.addWidget(self._field_label("Modo de encaixe"))
        self.mode_group = QButtonGroup(self)
        self.mode_radios = {}
        for text, value in (
            ("Mosaico por linhas", "gallery"),
            ("Rapido - Linhas inteligentes", "fast"),
            ("Compacto - Skyline", "tight"),
            ("Poligonal - Mascara alfa", "masked"),
        ):
            radio = QRadioButton(text)
            if value == "gallery":
                radio.setChecked(True)
            self.mode_group.addButton(radio)
            self.mode_radios[value] = radio
            config_layout.addWidget(radio)

        self.rotate_checkbox = QCheckBox("Permitir rotacao automatica")
        config_layout.addWidget(self.rotate_checkbox)
        layout.addWidget(config_box)

        layout.addWidget(self._section_label("ARQUIVO DE SAIDA"))
        self.output_input = self._standalone_field(layout, "Nome do arquivo", "rolo_125cm.jpg")

        layout.addStretch(1)

        self.run_button = QPushButton("GERAR ROLO")
        self.run_button.setObjectName("accent")
        self.run_button.setMinimumHeight(48)
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
        status_layout.setSpacing(12)

        self.status_label = QLabel("Aguardando...")
        self.status_label.setFont(QFont("Courier New", 11))
        self.status_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(220)

        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.progress, 0)
        layout.addWidget(status_card)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_log_tab(), "Log")
        self.tabs.addTab(self._build_preview_tab(), "Preview")
        self.tabs.addTab(self._build_debug_tab(), "Debug")
        layout.addWidget(self.tabs, 1)
        return frame

    def _build_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Courier New", 10))
        layout.addWidget(self.log_output)
        return widget

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_content = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_content)
        self.preview_layout.setContentsMargins(16, 16, 16, 16)
        self.preview_layout.setSpacing(10)
        self.preview_label = QLabel("A previa aparecera aqui apos gerar o rolo.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setObjectName("muted")
        self.preview_label.setMinimumHeight(280)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_layout.addWidget(self.preview_label)
        self.preview_scroll.setWidget(self.preview_content)
        layout.addWidget(self.preview_scroll)
        return widget

    def _build_debug_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.debug_list = QListWidget()
        self.debug_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.debug_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.debug_list.setMovement(QListWidget.Movement.Static)
        self.debug_list.setSpacing(12)
        self.debug_list.setIconSize(QPixmap(120, 120).size())
        layout.addWidget(self.debug_list)
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
        card_layout.setSpacing(4)
        label = label_text if not suffix else f"{label_text} ({suffix})"
        card_layout.addWidget(self._field_label(label))
        entry = QLineEdit()
        entry.setObjectName("fieldInput")
        entry.setText(default)
        card_layout.addWidget(entry)
        grid.addWidget(card, row, column)
        return entry

    def _standalone_field(self, layout: QVBoxLayout, label_text: str, placeholder: str) -> QLineEdit:
        card = QFrame()
        card.setObjectName("fieldCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)
        card_layout.addWidget(self._field_label(label_text))
        entry = QLineEdit()
        entry.setObjectName("fieldInput")
        entry.setPlaceholderText(placeholder)
        card_layout.addWidget(entry)
        layout.addWidget(card)
        return entry

    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Selecionar pasta de imagens")
        if not selected:
            return
        self._folder = Path(selected)
        self.folder_label.setText(f".../{self._folder.name}")
        self._append_log(f"📂  Pasta selecionada:\n    {selected}\n", "info")

    def _run(self) -> None:
        if self._worker_thread is not None:
            return
        if self._folder is None:
            QMessageBox.critical(self, "Erro", "Selecione uma pasta de imagens primeiro.")
            return

        try:
            largura = float(self.width_input.text())
            margem = float(self.margin_input.text())
            espaco = float(self.spacing_input.text())
            threshold = int(self.threshold_input.text())
            step = int(self.step_input.text())
            row_height_cm = float(self.row_height_input.text())
        except ValueError:
            QMessageBox.critical(self, "Erro", "Verifique os valores dos parametros.")
            return

        output_name = self.output_input.text().strip() or f"rolo_{int(largura)}cm.jpg"
        if not Path(output_name).suffix:
            output_name = f"{output_name}.jpg"
        elif Path(output_name).suffix.lower() not in {".jpg", ".jpeg"}:
            output_name = f"{Path(output_name).stem}.jpg"

        request = RollerPackRequest(
            folder=self._folder,
            largura_cm=largura,
            margem_cm=margem,
            espaco_cm=espaco,
            threshold=threshold,
            step_px=step,
            allow_rotate=self.rotate_checkbox.isChecked(),
            packing_mode=self._selected_value(self.mode_radios),
            row_height_cm=row_height_cm,
            output_name=output_name,
            performance_mode=self._selected_value(self.performance_radios),
        )

        self.log_output.clear()
        self.debug_list.clear()
        self.preview_label.setText("Processando...")
        self.preview_label.setPixmap(QPixmap())
        self._set_running(True)

        self._worker_thread = QThread(self)
        self._worker = RollPackWorker(request)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.status.connect(self._set_status)
        self._worker.debug.connect(self._show_debug_images)
        self._worker.finished.connect(self._handle_finished)
        self._worker.failed.connect(self._handle_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()

    def _append_log(self, text: str, level: str = "info") -> None:
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_output.setTextCursor(cursor)
        self.log_output.insertPlainText(text)
        self.log_output.ensureCursorVisible()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _handle_finished(self, result: RollerPackResult | None) -> None:
        if result is None:
            self._set_status("Nenhuma imagem valida encontrada.")
            self._set_running(False)
            return

        self._set_status(f"Concluido - {result.output_path.name}")
        self._show_preview(result.final_image)
        self._set_running(False)

    def _handle_failed(self, message: str) -> None:
        self._append_log(f"\nErro inesperado: {message}\n", "err")
        self._set_status("Erro durante o processamento.")
        QMessageBox.critical(self, "Erro", message)
        self._set_running(False)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
        self._worker = None
        self._worker_thread = None

    def _show_preview(self, img: Image.Image) -> None:
        max_w = 760
        ratio = min(1.0, max_w / img.width) if img.width > 0 else 1.0
        thumb = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)
        pixmap = pil_to_qpixmap(_checkerboard_image(thumb))
        self._preview_pixmap = pixmap

        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        size_label = QLabel(
            f"{img.width}×{img.height}px  ·  {img.width / 100 * 2.54:.1f}×{img.height / 100 * 2.54:.1f}cm"
        )
        size_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        size_label.setObjectName("muted")

        self._clear_layout(self.preview_layout)
        self.preview_layout.addWidget(self.preview_label)
        self.preview_layout.addWidget(size_label)
        self.tabs.setCurrentIndex(1)

    def _show_debug_images(self, payload: DebugPayload) -> None:
        self.debug_list.clear()
        self._debug_pixmaps.clear()
        visible_items = payload.image_items if payload.debug_limit <= 0 else payload.image_items[: payload.debug_limit]
        for item in visible_items:
            preview = item["image"].copy()
            preview.thumbnail((120, 120), Image.Resampling.LANCZOS)
            pixmap = pil_to_qpixmap(_checkerboard_image(preview, block=12))
            self._debug_pixmaps.append(pixmap)

            list_item = QListWidgetItem()
            list_item.setIcon(QIcon(pixmap))
            list_item.setText(
                f"{item['name']}\n{item['width_px']}×{item['height_px']} px\n{item['width_cm']:.1f} × {item['height_cm']:.1f} cm"
            )
            list_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            list_item.setSizeHint(list_item.sizeHint().expandedTo(self.debug_list.iconSize()))
            self.debug_list.addItem(list_item)

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.run_button.setText("Processando..." if running else "GERAR ROLO")
        if running:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

    def _selected_value(self, radios: dict[str, QRadioButton]) -> str:
        for value, radio in radios.items():
            if radio.isChecked():
                return value
        return next(iter(radios))

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class RoloPackerWindow(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        widget = RoloPackerWidget()
        layout.addWidget(widget)

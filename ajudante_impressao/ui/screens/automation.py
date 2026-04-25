from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
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

from ...services.automation import (
    AutomationConfig,
    CutAutomationConfig,
    ResizeAutomationConfig,
    watch_folder,
)
from ..common import ScreenScaffold


class AutomationWorker(QObject):
    log = Signal(str)
    status = Signal(str)
    stopped = Signal()

    def __init__(self, config: AutomationConfig):
        super().__init__()
        self._config = config
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self.status.emit("Monitorando pasta...")
        watch_folder(self._config, lambda: self._running, self.log.emit)
        self.stopped.emit()


class AutomationWidget(QWidget, ScreenScaffold):
    def __init__(self):
        super().__init__()
        self._source_folder: str = ""
        self._template_path: str = ""
        self._worker_thread: QThread | None = None
        self._worker: AutomationWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        layout.addWidget(self.wrap_sidebar(self._build_sidebar(), 396), 0)
        layout.addWidget(self._build_main(), 1)

    def _build_sidebar(self) -> QWidget:
        frame, layout = self.build_sidebar_frame(width=380)
        layout.addWidget(self.build_sidebar_header("AUTOMACAO", "Monitora uma pasta e executa a acao configurada em novos arquivos"))

        layout.addWidget(self.section_label("ORIGEM"))
        self.source_label = QLabel("Nenhuma pasta monitorada")
        self.source_label.setObjectName("muted")
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)

        pick_button = QPushButton("Selecionar Pasta")
        pick_button.clicked.connect(self._choose_source_folder)
        layout.addWidget(pick_button)

        layout.addWidget(self.section_label("ACAO"))
        config = QFrame()
        config.setObjectName("card")
        config_layout = QVBoxLayout(config)
        config_layout.setContentsMargins(14, 14, 14, 14)
        config_layout.setSpacing(12)

        config_layout.addWidget(self.field_label("Tipo de acao"))
        self.action_group = QButtonGroup(self)
        self.action_radios = {}
        for text, value in (("Resize", "resize"), ("Corte automatico", "cut_batch")):
            radio = QRadioButton(text)
            if value == "resize":
                radio.setChecked(True)
            radio.toggled.connect(self._refresh_action_ui)
            self.action_group.addButton(radio)
            self.action_radios[value] = radio
            config_layout.addWidget(radio)

        general_grid = QGridLayout()
        general_grid.setHorizontalSpacing(10)
        general_grid.setVerticalSpacing(10)
        self.poll_input = self.add_field_card("Intervalo de leitura", "2", "s", general_grid, 0, 0)
        config_layout.addLayout(general_grid)

        self.resize_section = QFrame()
        resize_layout = QVBoxLayout(self.resize_section)
        resize_layout.setContentsMargins(0, 0, 0, 0)
        resize_layout.setSpacing(10)
        resize_layout.addWidget(self.field_label("Configuracao de resize"))

        self.resize_mode_group = QButtonGroup(self)
        self.resize_mode_radios = {}
        for text, value in (("Percentual", "percent"), ("Largura em cm", "width_cm"), ("Largura em px", "width_px")):
            radio = QRadioButton(text)
            if value == "percent":
                radio.setChecked(True)
            radio.toggled.connect(self._refresh_resize_labels)
            self.resize_mode_group.addButton(radio)
            self.resize_mode_radios[value] = radio
            resize_layout.addWidget(radio)

        resize_grid = QGridLayout()
        resize_grid.setHorizontalSpacing(10)
        resize_grid.setVerticalSpacing(10)
        self.resize_value_input = self.add_field_card("Valor", "25", "%", resize_grid, 0, 0)
        self.resize_output_input = self.add_field_card("Subpasta", "AUTO_REDIMENSIONADAS", "", resize_grid, 0, 1)
        resize_layout.addLayout(resize_grid)

        self.resize_destination_group = QButtonGroup(self)
        self.resize_destination_radios = {}
        resize_layout.addWidget(self.field_label("Destino do resize"))
        for text, value in (("Subpasta", "subfolder"), ("Sobrescrever", "overwrite")):
            radio = QRadioButton(text)
            if value == "subfolder":
                radio.setChecked(True)
            radio.toggled.connect(self._refresh_resize_destination_ui)
            self.resize_destination_group.addButton(radio)
            self.resize_destination_radios[value] = radio
            resize_layout.addWidget(radio)

        self.resize_help = QLabel()
        self.resize_help.setObjectName("muted")
        self.resize_help.setWordWrap(True)
        resize_layout.addWidget(self.resize_help)

        self.cut_section = QFrame()
        cut_layout = QVBoxLayout(self.cut_section)
        cut_layout.setContentsMargins(0, 0, 0, 0)
        cut_layout.setSpacing(10)
        cut_layout.addWidget(self.field_label("Configuracao de corte"))

        self.template_label = QLabel("Nenhum gabarito")
        self.template_label.setObjectName("muted")
        self.template_label.setWordWrap(True)
        cut_layout.addWidget(self.template_label)
        template_button = QPushButton("Carregar Gabarito")
        template_button.clicked.connect(self._choose_template)
        cut_layout.addWidget(template_button)

        cut_grid = QGridLayout()
        cut_grid.setHorizontalSpacing(10)
        cut_grid.setVerticalSpacing(10)
        self.cut_plate_input = self.add_field_card("Largura da placa", "150", "cm", cut_grid, 0, 0)
        self.cut_dpi_input = self.add_field_card("DPI manual", "", "opcional", cut_grid, 0, 1)
        self.cut_pad_input = self.add_field_card("Margem branca", "1.0", "cm", cut_grid, 1, 0)
        cut_layout.addLayout(cut_grid)

        config_layout.addWidget(self.resize_section)
        config_layout.addWidget(self.cut_section)
        layout.addWidget(config)

        layout.addStretch(1)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("INICIAR")
        self.start_button.setObjectName("accent")
        self.start_button.clicked.connect(self._start_watching)
        self.stop_button = QPushButton("PARAR")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_watching)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)

        self._refresh_resize_labels()
        self._refresh_resize_destination_ui()
        self._refresh_action_ui()
        return frame

    def _build_main(self) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        status_card, self.status_label, self.progress = self.build_status_panel("Parado.")
        layout.addWidget(status_card)

        self.log_output = self.build_log_output()
        layout.addWidget(self.log_output, 1)
        return frame

    def _selected_value(self, radios: dict[str, QRadioButton]) -> str:
        for value, radio in radios.items():
            if radio.isChecked():
                return value
        return next(iter(radios))

    def _append_log(self, text: str) -> None:
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_output.setTextCursor(cursor)
        self.log_output.insertPlainText(text + "\n")
        self.log_output.ensureCursorVisible()

    def _choose_source_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Selecionar pasta para monitorar")
        if not selected:
            return
        self._source_folder = selected
        self.source_label.setText(selected)
        self._append_log(f"Pasta monitorada: {selected}")

    def _choose_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Carregar gabarito", "", "Imagens (*.png *.jpg *.jpeg *.tif *.tiff)")
        if not path:
            return
        self._template_path = path
        self.template_label.setText(path)

    def _refresh_action_ui(self) -> None:
        action = self._selected_value(self.action_radios)
        self.resize_section.setVisible(action == "resize")
        self.cut_section.setVisible(action == "cut_batch")

    def _refresh_resize_labels(self) -> None:
        mode = self._selected_value(self.resize_mode_radios)
        mapping = {
            "percent": ("Valor (%)", "Exemplo: 25 reduz para 25% do tamanho atual.", "25"),
            "width_cm": ("Largura final (cm)", "Usa o DPI da imagem para converter a largura alvo em cm.", "50"),
            "width_px": ("Largura final (px)", "Define uma largura final em pixels e mantem a proporcao.", "1000"),
        }
        label, help_text, default = mapping[mode]
        self.resize_value_input.parentWidget().findChildren(QLabel)[0].setText(label)
        if not self.resize_value_input.hasFocus():
            self.resize_value_input.setText(default)
        self.resize_help.setText(help_text)

    def _refresh_resize_destination_ui(self) -> None:
        is_subfolder = self._selected_value(self.resize_destination_radios) == "subfolder"
        self.resize_output_input.parentWidget().setVisible(is_subfolder)

    def _build_config(self) -> AutomationConfig:
        if not self._source_folder:
            raise ValueError("Selecione a pasta para monitorar.")

        poll_interval = float(self.poll_input.text().replace(",", "."))
        if poll_interval <= 0:
            raise ValueError("O intervalo deve ser maior que zero.")

        action = self._selected_value(self.action_radios)
        if action == "resize":
            target_value = float(self.resize_value_input.text().replace(",", "."))
            if target_value <= 0:
                raise ValueError("O valor de resize deve ser maior que zero.")
            return AutomationConfig(
                source_folder=self._source_folder,
                poll_interval=poll_interval,
                action=action,
                resize=ResizeAutomationConfig(
                    mode=self._selected_value(self.resize_mode_radios),
                    target_value=target_value,
                    destination_mode=self._selected_value(self.resize_destination_radios),
                    output_name=self.resize_output_input.text().strip() or "AUTO_REDIMENSIONADAS",
                ),
            )

        if not self._template_path:
            raise ValueError("Carregue um gabarito para o corte automatico.")
        plate_width = float(self.cut_plate_input.text().replace(",", "."))
        pad_cm = float(self.cut_pad_input.text().replace(",", "."))
        if plate_width <= 0 or pad_cm <= 0:
            raise ValueError("Largura da placa e margem branca devem ser maiores que zero.")
        dpi_override = None
        raw_dpi = self.cut_dpi_input.text().strip()
        if raw_dpi:
            dpi_override = int(float(raw_dpi.replace(",", ".")))
            if dpi_override <= 0:
                raise ValueError("O DPI manual deve ser maior que zero.")
        return AutomationConfig(
            source_folder=self._source_folder,
            poll_interval=poll_interval,
            action=action,
            cut=CutAutomationConfig(
                template_path=self._template_path,
                plate_width_cm=plate_width,
                pad_cm=pad_cm,
                dpi_override=dpi_override,
            ),
        )

    def _start_watching(self) -> None:
        if self._worker_thread is not None:
            return
        try:
            config = self._build_config()
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))
            return

        self._worker_thread = QThread(self)
        self._worker = AutomationWorker(config)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.status.connect(self._set_status)
        self._worker.stopped.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress.setRange(0, 0)

    def _stop_watching(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._set_status("Parando monitor...")
        self.stop_button.setEnabled(False)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _cleanup_worker(self) -> None:
        self._set_status("Parado.")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self._worker is not None:
            self._worker.deleteLater()
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
        self._worker = None
        self._worker_thread = None

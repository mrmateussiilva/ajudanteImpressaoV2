from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QDate, QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...services.roll_packer import PERFORMANCE_PROFILES, RollerPackRequest, RollerPackResult, run_roll_packer
from ..common import ScreenScaffold, ZoomablePreviewWidget


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


class ImageLoaderWorker(QObject):
    log = Signal(str, str)
    status = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, folder: Path, usable_width: int, threshold: int, max_workers: int):
        super().__init__()
        self._folder = folder
        self._usable_width = usable_width
        self._threshold = threshold
        self._max_workers = max_workers

    def run(self) -> None:
        try:
            from ...algorithms.image_ops import process_images
            items = process_images(
                folder=self._folder,
                max_width_px=self._usable_width,
                threshold=self._threshold,
                log_fn=lambda text, level="info": self.log.emit(text, level),
                max_workers=self._max_workers,
            )
            self.finished.emit(items)
        except Exception as exc:
            self.failed.emit(str(exc))


class RollPackWorker(QObject):
    log = Signal(str, str)
    status = Signal(str)
    debug = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, request: RollerPackRequest, image_items: list[dict] | None = None):
        super().__init__()
        self._request = request
        self._image_items = image_items

    def run(self) -> None:
        try:
            result = run_roll_packer(
                request=self._request,
                log_fn=lambda text, level="info": self.log.emit(text, level),
                status_fn=lambda text: self.status.emit(text),
                debug_fn=lambda items, limit: self.debug.emit(DebugPayload(items, limit)),
                image_items=self._image_items,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class RoloPackerWidget(QWidget, ScreenScaffold):
    def __init__(self):
        super().__init__()
        self._folder: Path | None = None
        self._worker_thread: QThread | None = None
        self._worker: QObject | None = None
        self._preview_pixmap: QPixmap | None = None
        self._debug_pixmaps: list[QPixmap] = []
        self._loaded_image_items: list[dict] = []
        self._label_text_color: tuple[int, int, int, int] = (0, 0, 0, 255)  # preto padrão
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        sidebar = self.wrap_sidebar(self._build_sidebar(), 376)
        main_panel = self._build_main()
        layout.addWidget(sidebar, 0)
        layout.addWidget(main_panel, 1)

    def _build_sidebar(self) -> QWidget:
        frame, layout = self.build_sidebar_frame()
        layout.addWidget(self.build_sidebar_header("ROLO PACKER", "Layout horizontal para impressao em rolo"))

        layout.addWidget(self.section_label("PASTA DE IMAGENS"))
        self.folder_label = QLabel("Nenhuma pasta selecionada")
        self.folder_label.setWordWrap(True)
        self.folder_label.setObjectName("muted")
        layout.addWidget(self.folder_label)

        pick_button = QPushButton("Selecionar Pasta")
        pick_button.clicked.connect(self._choose_folder)
        layout.addWidget(pick_button)

        self.load_button = QPushButton("Carregar Imagens")
        self.load_button.clicked.connect(self._load_images)
        self.load_button.setEnabled(False)
        layout.addWidget(self.load_button)

        self.clear_cache_button = QPushButton("Limpar Cache")
        self.clear_cache_button.clicked.connect(self._clear_cache)
        self.clear_cache_button.setEnabled(False)
        layout.addWidget(self.clear_cache_button)

        layout.addWidget(self.section_label("CONFIGURACOES"))
        config_box = QGroupBox()
        config_layout = QVBoxLayout(config_box)
        config_layout.setContentsMargins(14, 14, 14, 14)
        config_layout.setSpacing(12)

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(10)
        field_grid.setVerticalSpacing(10)

        self.width_input = self.add_field_card("Largura do rolo", "125", "cm", field_grid, 0, 0)
        self.margin_input = self.add_field_card("Margem nas bordas", "0.5", "cm", field_grid, 0, 1)
        self.spacing_input = self.add_field_card("Espacamento", "0.3", "cm", field_grid, 1, 0)
        self.threshold_input = self.add_field_card("Threshold branco", "245", "", field_grid, 1, 1)
        self.step_input = self.add_field_card("Precisao do encaixe", "8", "px", field_grid, 2, 0)
        self.row_height_input = self.add_field_card("Altura base", "18", "cm", field_grid, 2, 1)
        config_layout.addLayout(field_grid)

        config_layout.addWidget(self.field_label("Perfil de performance"))
        self.performance_group = QButtonGroup(self)
        self.performance_radios = {}
        for text, value in (("Qualidade", "quality"), ("Balanceado", "balanced"), ("Rapido", "fast")):
            radio = QRadioButton(text)
            if value == "balanced":
                radio.setChecked(True)
            self.performance_group.addButton(radio)
            self.performance_radios[value] = radio
            config_layout.addWidget(radio)


        self.rotate_checkbox = QCheckBox("Permitir rotacao automatica")
        config_layout.addWidget(self.rotate_checkbox)

        config_layout.addWidget(self.field_label("Posição do rótulo"))
        self.label_pos_combo = QComboBox()
        self.label_pos_combo.addItems([
            "Externo - Inferior Direita",
            "Externo - Inferior Esquerda",
            "Externo - Inferior Centro",
            "Sobreposto - Direita Inferior",
            "Sobreposto - Esquerda Inferior",
            "Sobreposto - Direita Superior",
            "Sobreposto - Esquerda Superior"
        ])
        self.label_pos_map = {
            "Externo - Inferior Direita": "external_bottom_right",
            "Externo - Inferior Esquerda": "external_bottom_left",
            "Externo - Inferior Centro": "external_bottom_center",
            "Sobreposto - Direita Inferior": "overlay_bottom_right",
            "Sobreposto - Esquerda Inferior": "overlay_bottom_left",
            "Sobreposto - Direita Superior": "overlay_top_right",
            "Sobreposto - Esquerda Superior": "overlay_top_left"
        }
        self.label_pos_combo.setCurrentText("Externo - Inferior Direita")
        config_layout.addWidget(self.label_pos_combo)

        # --- Data de Envio ---
        config_layout.addWidget(self.field_label("Data de envio (opcional)"))
        self.label_date_edit = QDateEdit()
        self.label_date_edit.setDisplayFormat("dd/MM/yyyy")
        self.label_date_edit.setCalendarPopup(True)
        self.label_date_edit.setDate(QDate.currentDate())
        self.label_date_edit.setObjectName("fieldInput")
        self.label_date_edit.setMinimumHeight(36)
        self.label_date_checkbox = QCheckBox("Incluir data de envio no rótulo")
        config_layout.addWidget(self.label_date_checkbox)
        config_layout.addWidget(self.label_date_edit)

        # --- Cor do Texto ---
        config_layout.addWidget(self.field_label("Cor do texto do rótulo"))
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self._color_swatch = QLabel()
        self._color_swatch.setFixedSize(32, 32)
        self._color_swatch.setStyleSheet(
            "background-color: #000000; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2);"
        )
        color_row.addWidget(self._color_swatch)
        self._color_btn = QPushButton("Escolher cor")
        self._color_btn.setMinimumHeight(32)
        self._color_btn.clicked.connect(self._pick_label_color)
        color_row.addWidget(self._color_btn, 1)
        config_layout.addLayout(color_row)

        layout.addWidget(config_box)

        layout.addWidget(self.section_label("ARQUIVO DE SAIDA"))
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

        status_card, self.status_label, self.progress = self.build_status_panel("Aguardando...")
        self.status_label.setObjectName("muted")
        layout.addWidget(status_card)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_log_tab(), "Log")
        self.tabs.addTab(self._build_preview_tab(), "Preview")
        self.tabs.addTab(self._build_debug_tab(), "Fila de Produção")
        layout.addWidget(self.tabs, 1)
        return frame

    def _build_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.log_output = self.build_log_output()
        layout.addWidget(self.log_output)
        return widget

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Card de estatísticas de aproveitamento (quando gerado)
        self.stats_card = QFrame()
        self.stats_card.setObjectName("fieldCard")
        self.stats_layout = QHBoxLayout(self.stats_card)
        self.stats_layout.setContentsMargins(14, 8, 14, 8)
        self.stats_layout.setSpacing(12)
        self.stats_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_card.setVisible(False)
        layout.addWidget(self.stats_card)

        self.preview_widget = ZoomablePreviewWidget(
            placeholder_text="A prévia aparecerá aqui após gerar o rolo."
        )
        layout.addWidget(self.preview_widget, 1)
        return widget

    def _build_debug_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.debug_list = QListWidget()
        self.debug_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.debug_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.debug_list.setMovement(QListWidget.Movement.Static)
        self.debug_list.setSpacing(16)
        layout.addWidget(self.debug_list)
        return widget

    def _standalone_field(self, layout: QVBoxLayout, label_text: str, placeholder: str) -> QLineEdit:
        card = QFrame()
        card.setObjectName("fieldCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)
        card_layout.addWidget(self.field_label(label_text))
        entry = QLineEdit()
        entry.setObjectName("fieldInput")
        entry.setPlaceholderText(placeholder)
        entry.setMinimumHeight(36)
        card_layout.addWidget(entry)
        layout.addWidget(card)
        return entry

    def _pick_label_color(self) -> None:
        r, g, b, a = self._label_text_color
        initial = QColor(r, g, b, a)
        color = QColorDialog.getColor(
            initial, self, "Cor do texto do rótulo",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._label_text_color = (color.red(), color.green(), color.blue(), color.alpha())
            hex_color = color.name()  # ex: "#1a2b3c"
            self._color_swatch.setStyleSheet(
                f"background-color: {hex_color}; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2);"
            )

    def _choose_folder(self) -> None:

        selected = QFileDialog.getExistingDirectory(self, "Selecionar pasta de imagens")
        if not selected:
            return
        self._folder = Path(selected)
        self.folder_label.setText(f".../{self._folder.name}")
        self._append_log(f"📂  Pasta selecionada:\n    {selected}\n", "info")
        self.load_button.setEnabled(True)
        self.clear_cache_button.setEnabled(True)
        self._loaded_image_items = []

    def _load_images(self) -> None:
        if self._worker_thread is not None:
            return
        if self._folder is None:
            QMessageBox.critical(self, "Erro", "Selecione uma pasta de imagens primeiro.")
            return

        try:
            largura = float(self.width_input.text())
            margem = float(self.margin_input.text())
            threshold = int(self.threshold_input.text())
        except ValueError:
            QMessageBox.critical(self, "Erro", "Verifique os valores de largura, margem e threshold.")
            return

        from ...algorithms.image_ops import cm_to_px
        roll_px = cm_to_px(largura)
        margin_px = cm_to_px(margem)
        usable_width = max(1, roll_px - 2 * margin_px)

        profile = PERFORMANCE_PROFILES.get(
            self._selected_value(self.performance_radios), PERFORMANCE_PROFILES["balanced"]
        )

        self.log_output.clear()
        self.debug_list.clear()
        self.preview_widget.clear("Carregando imagens...")
        self._set_running(True)

        self._worker_thread = QThread(self)
        self._worker = ImageLoaderWorker(
            folder=self._folder,
            usable_width=usable_width,
            threshold=threshold,
            max_workers=profile["max_workers"],
        )
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.status.connect(self._set_status)
        self._worker.finished.connect(self._handle_loading_finished)
        self._worker.failed.connect(self._handle_failed)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.failed.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()

    def _clear_cache(self) -> None:
        if self._folder is None:
            return
        cache_dir = self._folder / ".ajudante_cache"
        if not cache_dir.exists():
            QMessageBox.information(self, "Limpeza de Cache", "Não há nenhum cache salvo para esta pasta.")
            return
            
        reply = QMessageBox.question(
            self, "Confirmar Limpeza",
            "Deseja realmente excluir todos os arquivos de cache desta pasta?\n"
            "As imagens precisarão ser processadas novamente na próxima execução.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                import shutil
                shutil.rmtree(cache_dir)
                self._append_log("⚡ Cache da pasta limpo com sucesso!\n", "ok")
                self.debug_list.clear()
                self._loaded_image_items = []
                self.clear_cache_button.setEnabled(False)
                QMessageBox.information(self, "Sucesso", "O cache desta pasta foi excluído.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao limpar o cache: {e}")

    def _handle_loading_finished(self, image_items: list[dict] | None) -> None:
        self._set_running(False)
        if not image_items:
            self._set_status("Nenhuma imagem valida encontrada.")
            return

        self._loaded_image_items = image_items
        self._set_status(f"{len(image_items)} imagens carregadas.")
        
        profile = PERFORMANCE_PROFILES.get(
            self._selected_value(self.performance_radios), PERFORMANCE_PROFILES["balanced"]
        )
        self._show_debug_images(DebugPayload(image_items, profile["debug_limit"]))
        self.tabs.setCurrentIndex(2)

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

        label_pos_text = self.label_pos_combo.currentText()
        label_pos_value = self.label_pos_map.get(label_pos_text, "external_bottom_right")

        # Data de envio: só inclui se o checkbox estiver marcado
        label_date = ""
        if self.label_date_checkbox.isChecked():
            label_date = self.label_date_edit.date().toString("dd/MM/yyyy")

        request = RollerPackRequest(
            folder=self._folder,
            largura_cm=largura,
            margem_cm=margem,
            espaco_cm=espaco,
            threshold=threshold,
            step_px=step,
            allow_rotate=self.rotate_checkbox.isChecked(),
            row_height_cm=row_height_cm,
            output_name=output_name,
            performance_mode=self._selected_value(self.performance_radios),
            label_position=label_pos_value,
            label_date=label_date,
            label_text_color=self._label_text_color,
        )

        self.log_output.clear()
        self.preview_widget.clear("Processando layout do rolo...")
        self._set_running(True)

        self._worker_thread = QThread(self)
        self._worker = RollPackWorker(request, image_items=self._loaded_image_items or None)
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
        self._show_preview(result.final_image, result=result)
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

    def _show_preview(self, img: Image.Image, result: RollerPackResult | None = None) -> None:
        # Gera visualização em alta fidelidade para navegação interativa (zoom/pan)
        max_preview_w = 2600
        ratio = min(1.0, max_preview_w / img.width) if img.width > 0 else 1.0
        if ratio < 1.0:
            preview_img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)
        else:
            preview_img = img

        pixmap = pil_to_qpixmap(preview_img)
        self._preview_pixmap = pixmap

        dim_info = (
            f"Rolo: {img.width}×{img.height} px  ·  "
            f"{img.width / 100 * 2.54:.1f} × {img.height / 100 * 2.54:.1f} cm"
        )
        self.preview_widget.set_pixmap(pixmap, info_text=dim_info)

        # Atualiza métricas de aproveitamento se disponíveis
        if result is not None and getattr(result, "yield_pct", 0) > 0:
            while self.stats_layout.count():
                item = self.stats_layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()

            yield_lbl = QLabel(f"✓ {result.yield_pct}% Aproveitamento Útil")
            yield_lbl.setStyleSheet(
                "background: rgba(166, 227, 161, 0.15); color: #A6E3A1; border: 1px solid #A6E3A1; "
                "font-weight: bold; font-size: 12px; border-radius: 6px; padding: 4px 10px;"
            )

            waste_color = "#F38BA8" if result.waste_pct > 30 else "#F9E2AF"
            waste_lbl = QLabel(f"⚠ {result.waste_pct}% Sobra / Desperdício")
            waste_lbl.setStyleSheet(
                f"background: rgba(243, 139, 168, 0.15); color: {waste_color}; border: 1px solid {waste_color}; "
                "font-weight: bold; font-size: 12px; border-radius: 6px; padding: 4px 10px;"
            )

            area_lbl = QLabel(f"📐 {result.total_area_m2} m² Área Total")
            area_lbl.setStyleSheet(
                "background: rgba(59, 130, 246, 0.15); color: #3B82F6; border: 1px solid #3B82F6; "
                "font-weight: bold; font-size: 12px; border-radius: 6px; padding: 4px 10px;"
            )

            time_lbl = QLabel(f"⏱ {result.elapsed_seconds:.1f}s Tempo Geração")
            time_lbl.setStyleSheet(
                "background: rgba(195, 160, 245, 0.15); color: #C3A0F5; border: 1px solid #C3A0F5; "
                "font-weight: bold; font-size: 12px; border-radius: 6px; padding: 4px 10px;"
            )

            self.stats_layout.addWidget(yield_lbl)
            self.stats_layout.addWidget(waste_lbl)
            self.stats_layout.addWidget(area_lbl)
            self.stats_layout.addWidget(time_lbl)
            self.stats_card.setVisible(True)
        else:
            self.stats_card.setVisible(False)

        self.tabs.setCurrentIndex(1)
        self.tabs.setCurrentIndex(1)

    def _show_debug_images(self, payload: DebugPayload) -> None:
        self.debug_list.clear()
        self._debug_pixmaps.clear()
        visible_items = payload.image_items if payload.debug_limit <= 0 else payload.image_items[: payload.debug_limit]
        for item in visible_items:
            if "thumbnail" in item:
                preview = item["thumbnail"]
            else:
                preview = item["image"].copy()
                preview.thumbnail((200, 200), Image.Resampling.BILINEAR)
            pixmap = pil_to_qpixmap(_checkerboard_image(preview, block=16))
            self._debug_pixmaps.append(pixmap)

            card = QFrame()
            card.setStyleSheet(
                "QFrame {"
                "    background-color: rgba(30, 30, 46, 0.6);"
                "    border-radius: 8px;"
                "    border: 1px solid rgba(255, 255, 255, 0.1);"
                "}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(6)

            img_lbl = QLabel()
            img_lbl.setPixmap(pixmap)
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setStyleSheet("border: none; background: transparent;")
            card_layout.addWidget(img_lbl, 1)

            name_lbl = QLabel(item['name'])
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = name_lbl.font()
            font.setBold(True)
            name_lbl.setFont(font)
            name_lbl.setStyleSheet("border: none; background: transparent; color: #CDD6F4;")
            
            metrics = name_lbl.fontMetrics()
            elided_name = metrics.elidedText(item['name'], Qt.TextElideMode.ElideRight, 196)
            name_lbl.setText(elided_name)
            name_lbl.setToolTip(item['name'])

            card_layout.addWidget(name_lbl)

            # Inputs interativos para alterar a medida (mantendo proporção)
            dim_container = QWidget()
            dim_container.setStyleSheet("border: none; background: transparent;")
            dim_layout = QHBoxLayout(dim_container)
            dim_layout.setContentsMargins(0, 0, 0, 0)
            dim_layout.setSpacing(4)
            dim_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            w_input = QLineEdit(f"{item['width_cm']:.1f}")
            h_input = QLineEdit(f"{item['height_cm']:.1f}")
            w_input.setFixedWidth(54)
            h_input.setFixedWidth(54)
            w_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            input_style = (
                "QLineEdit {"
                "    background: #313244;"
                "    color: #CDD6F4;"
                "    border: 1px solid rgba(255, 255, 255, 0.1);"
                "    border-radius: 4px;"
                "    font-size: 11px;"
                "    padding: 2px;"
                "}"
                "QLineEdit:focus {"
                "    border: 1px solid #3B82F6;"
                "}"
            )
            w_input.setStyleSheet(input_style)
            h_input.setStyleSheet(input_style)

            times_lbl = QLabel("×")
            times_lbl.setStyleSheet("color: #A6ADC8; font-size: 11px; border: none; background: transparent;")
            cm_lbl = QLabel("cm")
            cm_lbl.setStyleSheet("color: #A6ADC8; font-size: 11px; border: none; background: transparent;")

            dim_layout.addWidget(w_input)
            dim_layout.addWidget(times_lbl)
            dim_layout.addWidget(h_input)
            dim_layout.addWidget(cm_lbl)
            card_layout.addWidget(dim_container)

            # Lógica de alteração mantendo proporção original
            aspect_ratio = item["height_cm"] / item["width_cm"] if item["width_cm"] > 0 else 1.0
            if "original_image" not in item:
                item["original_image"] = item["image"].copy()

            # Evita recursão infinita
            is_updating = False

            def make_w_handler(w_edit=w_input, h_edit=h_input, target_item=item):
                def on_w_change():
                    nonlocal is_updating
                    if is_updating:
                        return
                    try:
                        val_str = w_edit.text().replace(",", ".").strip()
                        if not val_str:
                            return
                        val = float(val_str)
                        if val <= 0:
                            return
                        is_updating = True
                        new_h = val * aspect_ratio
                        h_edit.setText(f"{new_h:.1f}")
                        
                        # Atualiza imagem e metadados no item
                        target_item["width_cm"] = val
                        target_item["height_cm"] = new_h
                        
                        from ...algorithms.image_ops import cm_to_px, update_image_cache_meta
                        new_w_px = cm_to_px(val)
                        new_h_px = cm_to_px(new_h)
                        target_item["image"] = target_item["original_image"].resize((new_w_px, new_h_px), Image.Resampling.LANCZOS)
                        target_item["width_px"] = new_w_px
                        target_item["height_px"] = new_h_px
                        
                        # Salva no cache
                        thresh = int(self.threshold_input.text())
                        if self._folder:
                            update_image_cache_meta(self._folder, target_item["name"], thresh, {
                                "width_cm": val,
                                "height_cm": new_h,
                                "width_px": new_w_px,
                                "height_px": new_h_px
                            })
                    except ValueError:
                        pass
                    finally:
                        is_updating = False
                return on_w_change

            def make_h_handler(w_edit=w_input, h_edit=h_input, target_item=item):
                def on_h_change():
                    nonlocal is_updating
                    if is_updating:
                        return
                    try:
                        val_str = h_edit.text().replace(",", ".").strip()
                        if not val_str:
                            return
                        val = float(val_str)
                        if val <= 0:
                            return
                        is_updating = True
                        new_w = val / aspect_ratio
                        w_edit.setText(f"{new_w:.1f}")
                        
                        # Atualiza imagem e metadados no item
                        target_item["width_cm"] = new_w
                        target_item["height_cm"] = val
                        
                        from ...algorithms.image_ops import cm_to_px, update_image_cache_meta
                        new_w_px = cm_to_px(new_w)
                        new_h_px = cm_to_px(val)
                        target_item["image"] = target_item["original_image"].resize((new_w_px, new_h_px), Image.Resampling.LANCZOS)
                        target_item["width_px"] = new_w_px
                        target_item["height_px"] = new_h_px
                        
                        # Salva no cache
                        thresh = int(self.threshold_input.text())
                        if self._folder:
                            update_image_cache_meta(self._folder, target_item["name"], thresh, {
                                "width_cm": new_w,
                                "height_cm": val,
                                "width_px": new_w_px,
                                "height_px": new_h_px
                            })
                    except ValueError:
                        pass
                    finally:
                        is_updating = False
                return on_h_change

            # Dispara a mudança apenas ao sair do campo ou pressionar Enter (evita lentidão ao digitar)
            w_input.editingFinished.connect(make_w_handler())
            h_input.editingFinished.connect(make_h_handler())

            # Informações de Inteligência (Material, Confiança e Qualidade Interativa)
            from ...algorithms.classifier import get_prod_classifier, get_quality_classifier, feed_back_to_training
            from ...algorithms.image_ops import update_image_cache_meta

            prod_cls = get_prod_classifier()
            qual_cls = get_quality_classifier()

            try:
                available_categories = list(prod_cls.category_names)
            except Exception:
                available_categories = []

            default_cats = ["3mm sp", "6mm cp", "poliondas", "adesivo", "lona"]
            for default_cat in default_cats:
                if default_cat not in available_categories:
                    available_categories.append(default_cat)

            if "N/A" not in available_categories:
                available_categories.append("N/A")

            current_cat = item.get("category", "N/A")
            if current_cat not in available_categories:
                available_categories.append(current_cat)

            available_categories.sort(key=lambda x: (x == "N/A", x.lower()))
            available_categories.append("+ Nova Categoria...")

            # Linha 1: Dropdown de Categoria + Badge de Confiança
            row1 = QHBoxLayout()
            row1.setSpacing(4)

            cat_combo = QComboBox()
            cat_combo.addItems(available_categories)
            cat_combo.setCurrentText(current_cat)
            cat_combo.setStyleSheet(
                "QComboBox {"
                "    background: #313244;"
                "    color: #CDD6F4;"
                "    border-radius: 4px;"
                "    padding: 2px 6px;"
                "    font-size: 10px;"
                "    font-weight: bold;"
                "    border: 1px solid rgba(255, 255, 255, 0.15);"
                "}"
                "QComboBox::drop-down { border: none; }"
                "QComboBox QAbstractItemView {"
                "    background-color: #1e1e2e;"
                "    color: #CDD6F4;"
                "    selection-background-color: #45475a;"
                "}"
            )

            # Badge de Confiança
            conf_val = float(item.get("category_confidence", 0.0))
            if conf_val >= 80:
                conf_bg = "#22c55e"
                conf_fg = "#ffffff"
            elif conf_val >= 50:
                conf_bg = "#eab308"
                conf_fg = "#000000"
            elif conf_val > 0:
                conf_bg = "#ef4444"
                conf_fg = "#ffffff"
            else:
                conf_bg = "#45475a"
                conf_fg = "#bac2de"

            conf_badge = QLabel(f"{conf_val:.0f}%" if conf_val > 0 else "--")
            conf_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            conf_badge.setFixedWidth(34)
            conf_badge.setStyleSheet(
                f"background: {conf_bg}; color: {conf_fg}; border-radius: 4px; font-size: 9px; font-weight: 800; padding: 2px;"
            )
            conf_tooltip = f"Confiança da IA: {conf_val:.1f}%\n"
            if item.get("features_summary"):
                fs = item["features_summary"]
                conf_tooltip += f"Dimensão: {fs.get('width_cm', 0):.1f}x{fs.get('height_cm', 0):.1f}cm\nFill Ratio: {fs.get('fill_ratio', 0):.1f}%"
            conf_badge.setToolTip(conf_tooltip)

            row1.addWidget(cat_combo, 1)
            row1.addWidget(conf_badge, 0)
            card_layout.addLayout(row1)

            # Linha 2: Dropdown de Qualidade Interativo + Label de Aprendizado
            row2 = QHBoxLayout()
            row2.setSpacing(4)

            qual_combo = QComboBox()
            qual_combo.addItems(["Boa", "Aceitável", "Ruim"])
            current_qual_raw = item.get("quality", "boa").lower()
            if "ruim" in current_qual_raw:
                qual_combo.setCurrentText("Ruim")
            elif "aceit" in current_qual_raw:
                qual_combo.setCurrentText("Aceitável")
            else:
                qual_combo.setCurrentText("Boa")

            def _apply_qual_style(combo: QComboBox, text: str):
                t_low = text.lower()
                color = "#A6E3A1" if "boa" in t_low else "#F9E2AF" if "aceit" in t_low else "#F38BA8"
                combo.setStyleSheet(
                    f"QComboBox {{ background: #313244; color: {color}; border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold; border: 1px solid {color}; }}"
                    "QComboBox::drop-down { border: none; }"
                    "QComboBox QAbstractItemView { background-color: #1e1e2e; color: #cdd6f4; selection-background-color: #45475a; }"
                )

            _apply_qual_style(qual_combo, qual_combo.currentText())

            learn_status_lbl = QLabel("")
            learn_status_lbl.setStyleSheet("font-size: 9px; color: #a6e3a1; font-weight: bold;")
            learn_status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Handlers de feedback em tempo real
            def make_cat_handler(target_item=item, combo=cat_combo, badge=conf_badge, status_lbl=learn_status_lbl):
                def on_cat_change(text):
                    if text == "+ Nova Categoria...":
                        new_cat, ok = QInputDialog.getText(self, "Nova Categoria", "Digite o nome da nova categoria:")
                        if ok and new_cat.strip():
                            clean_cat = new_cat.strip()
                            prod_cls.add_category(clean_cat)
                            combo.blockSignals(True)
                            combo.insertItem(combo.count() - 1, clean_cat)
                            combo.setCurrentText(clean_cat)
                            combo.blockSignals(False)
                            text = clean_cat
                        else:
                            combo.blockSignals(True)
                            combo.setCurrentText(target_item.get("category", "N/A"))
                            combo.blockSignals(False)
                            return

                    target_item["category"] = text
                    badge.setText("100%")
                    badge.setStyleSheet("background: #22c55e; color: white; border-radius: 4px; font-size: 9px; font-weight: 800; padding: 2px;")
                    status_lbl.setText("🧠 Aprendido!")
                    try:
                        thresh = int(self.threshold_input.text())
                        if self._folder:
                            update_image_cache_meta(self._folder, target_item["name"], thresh, {"category": text})
                            feed_back_to_training(self._folder, target_item["name"], thresh, category=text)
                    except Exception:
                        pass
                return on_cat_change

            def make_qual_handler(target_item=item, combo=qual_combo, status_lbl=learn_status_lbl):
                def on_qual_change(text):
                    _apply_qual_style(combo, text)
                    norm_qual = "boa" if text == "Boa" else "aceitavel" if text == "Aceitável" else "ruim"
                    target_item["quality"] = norm_qual
                    status_lbl.setText("🧠 Aprendido!")
                    try:
                        thresh = int(self.threshold_input.text())
                        if self._folder:
                            update_image_cache_meta(self._folder, target_item["name"], thresh, {"quality": norm_qual})
                            feed_back_to_training(self._folder, target_item["name"], thresh, quality=norm_qual)
                    except Exception:
                        pass
                return on_qual_change

            cat_combo.currentTextChanged.connect(make_cat_handler())
            qual_combo.currentTextChanged.connect(make_qual_handler())

            row2.addWidget(qual_combo, 1)
            row2.addWidget(learn_status_lbl, 1)
            card_layout.addLayout(row2)

            card.setFixedSize(220, 310)

            list_item = QListWidgetItem(self.debug_list)
            list_item.setSizeHint(card.size())
            self.debug_list.setItemWidget(list_item, card)

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

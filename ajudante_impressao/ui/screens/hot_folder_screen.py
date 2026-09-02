from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPixmap, QTextCursor
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
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...services.hot_folder_service import HotFolderConfig, HotFolderWorker
from ...services.roll_packer import RollerPackResult
from ..common import ScreenScaffold
from .roll_packer import _checkerboard_image, pil_to_qpixmap


class HotFolderWidget(QWidget, ScreenScaffold):
    def __init__(self):
        super().__init__()
        self._input_folder: Path | None = None
        self._output_folder: Path | None = None
        self._worker_thread: QThread | None = None
        self._worker: HotFolderWorker | None = None
        self._is_active: bool = False
        self._staged_items: list[dict] = []
        self._roll_history: list[RollerPackResult] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        sidebar = self.wrap_sidebar(self._build_sidebar(), 380)
        main_panel = self._build_main()
        layout.addWidget(sidebar, 0)
        layout.addWidget(main_panel, 1)

    def _build_sidebar(self) -> QWidget:
        frame, layout = self.build_sidebar_frame(380)
        layout.addWidget(self.build_sidebar_header("AGENTE MONITORADOR", "Hot Folder autônomo para pré-impressão"))

        # ── Pastas de Trabalho ───────────────────────────────────────────────
        layout.addWidget(self.section_label("PASTAS DO AGENTE"))
        
        # Pasta de Entrada (Hot Folder)
        layout.addWidget(self.field_label("Pasta de Entrada (Hot Folder)"))
        self.input_folder_label = QLabel("Nenhuma pasta selecionada")
        self.input_folder_label.setWordWrap(True)
        self.input_folder_label.setObjectName("muted")
        layout.addWidget(self.input_folder_label)

        pick_input_btn = QPushButton("Selecionar Pasta de Entrada")
        pick_input_btn.clicked.connect(self._choose_input_folder)
        layout.addWidget(pick_input_btn)

        # Pasta de Saída (Rolos Prontos)
        layout.addWidget(self.field_label("Pasta de Saída (Rolos Prontos)"))
        self.output_folder_label = QLabel("Nenhuma pasta selecionada")
        self.output_folder_label.setWordWrap(True)
        self.output_folder_label.setObjectName("muted")
        layout.addWidget(self.output_folder_label)

        pick_output_btn = QPushButton("Selecionar Pasta de Saída")
        pick_output_btn.clicked.connect(self._choose_output_folder)
        layout.addWidget(pick_output_btn)

        # ── Configurações do Rolo ────────────────────────────────────────────
        layout.addWidget(self.section_label("CONFIGURAÇÕES DO ROLO"))
        config_box = QGroupBox()
        config_layout = QVBoxLayout(config_box)
        config_layout.setContentsMargins(14, 14, 14, 14)
        config_layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self.width_input = self.add_field_card("Largura rolo", "125", "cm", grid, 0, 0)
        self.margin_input = self.add_field_card("Margem", "0.5", "cm", grid, 0, 1)
        self.spacing_input = self.add_field_card("Espaçamento", "0.3", "cm", grid, 1, 0)
        self.step_input = self.add_field_card("Precisão", "8", "px", grid, 1, 1)
        config_layout.addLayout(grid)

        config_layout.addWidget(self.field_label("Perfil de Performance"))
        self.performance_group = QButtonGroup(self)
        self.performance_radios = {}
        for text, value in (("Qualidade", "quality"), ("Balanceado", "balanced"), ("Rápido", "fast")):
            radio = QRadioButton(text)
            if value == "balanced":
                radio.setChecked(True)
            self.performance_group.addButton(radio)
            self.performance_radios[value] = radio
            config_layout.addWidget(radio)

        self.rotate_checkbox = QCheckBox("Permitir rotação automática")
        self.rotate_checkbox.setChecked(True)
        config_layout.addWidget(self.rotate_checkbox)
        layout.addWidget(config_box)

        # ── Regras de Disparo do Agente ──────────────────────────────────────
        layout.addWidget(self.section_label("REGRAS DO AGENTE"))
        rules_box = QGroupBox()
        rules_layout = QVBoxLayout(rules_box)
        rules_layout.setContentsMargins(14, 14, 14, 14)
        rules_layout.setSpacing(10)

        rules_grid = QGridLayout()
        rules_grid.setHorizontalSpacing(10)
        rules_grid.setVerticalSpacing(10)

        self.inactivity_input = self.add_field_card("Tempo Inatividade", "15", "seg", rules_grid, 0, 0)
        self.settle_input = self.add_field_card("Estabilização Cópia", "3", "seg", rules_grid, 0, 1)
        rules_layout.addLayout(rules_grid)

        self.group_material_checkbox = QCheckBox("Agrupar e separar por Material/Categoria")
        self.group_material_checkbox.setChecked(True)
        rules_layout.addWidget(self.group_material_checkbox)

        self.move_processed_checkbox = QCheckBox("Mover artes finalizadas para 'Processados/'")
        self.move_processed_checkbox.setChecked(True)
        rules_layout.addWidget(self.move_processed_checkbox)
        layout.addWidget(rules_box)

        layout.addStretch(1)

        # ── Botão de Ativação Principal ──────────────────────────────────────
        self.force_pack_btn = QPushButton("⚡ PROCESSAR FILA AGORA")
        self.force_pack_btn.setMinimumHeight(40)
        self.force_pack_btn.setEnabled(False)
        self.force_pack_btn.clicked.connect(self._force_pack_now)
        layout.addWidget(self.force_pack_btn)

        self.toggle_agent_btn = QPushButton("INICIAR AGENTE MONITORADOR")
        self.toggle_agent_btn.setObjectName("accent")
        self.toggle_agent_btn.setMinimumHeight(52)
        self.toggle_agent_btn.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; font-size: 13px; border-radius: 8px;"
        )
        self.toggle_agent_btn.clicked.connect(self._toggle_agent)
        layout.addWidget(self.toggle_agent_btn)

        return frame

    def _build_main(self) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # ── Top KPI & Status Card ────────────────────────────────────────────
        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(18, 14, 18, 14)
        status_layout.setSpacing(16)

        self.status_badge = QLabel("⚪ AGENTE PAUSADO")
        self.status_badge.setStyleSheet(
            "background: rgba(255, 255, 255, 0.1); color: #cdd6f4; font-weight: bold; "
            "font-size: 13px; border-radius: 6px; padding: 6px 14px; border: 1px solid rgba(255,255,255,0.2);"
        )
        status_layout.addWidget(self.status_badge)

        status_layout.addStretch(1)

        # KPI 1: Artes na Fila
        self.kpi_queue_lbl = QLabel("📥 0 Artes na Fila")
        self.kpi_queue_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #89b4fa;")
        status_layout.addWidget(self.kpi_queue_lbl)

        # KPI 2: Total Recebido
        self.kpi_received_lbl = QLabel("📦 0 Recebidas Hoje")
        self.kpi_received_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #a6e3a1;")
        status_layout.addWidget(self.kpi_received_lbl)

        # KPI 3: Rolos Gerados
        self.kpi_rolls_lbl = QLabel("🚀 0 Rolos Gerados")
        self.kpi_rolls_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #f9e2af;")
        status_layout.addWidget(self.kpi_rolls_lbl)

        # KPI 4: Última Atividade
        self.kpi_activity_lbl = QLabel("⏱️ Inativo")
        self.kpi_activity_lbl.setStyleSheet("font-size: 12px; color: #6c7086;")
        status_layout.addWidget(self.kpi_activity_lbl)

        layout.addWidget(status_card)

        # ── Tabs Centrais ────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_log_tab(), "Live Stream & Eventos")
        self.tabs.addTab(self._build_queue_tab(), "Fila ao Vivo (Staging)")
        self.tabs.addTab(self._build_history_tab(), "Histórico de Rolos Gerados")
        layout.addWidget(self.tabs, 1)

        return frame

    def _build_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.log_output = self.build_log_output()
        layout.addWidget(self.log_output)
        return widget

    def _build_queue_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.queue_list = QListWidget()
        self.queue_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.queue_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.queue_list.setMovement(QListWidget.Movement.Static)
        self.queue_list.setSpacing(16)
        self.queue_list.setIconSize(self.queue_list.size())
        layout.addWidget(self.queue_list)

        return widget

    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_content = QWidget()
        self.history_layout = QVBoxLayout(self.history_content)
        self.history_layout.setContentsMargins(8, 8, 8, 8)
        self.history_layout.setSpacing(10)
        self.history_layout.addStretch(1)

        self.history_scroll.setWidget(self.history_content)
        layout.addWidget(self.history_scroll)

        return widget

    def _choose_input_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Entrada (Hot Folder)")
        if not selected:
            return
        self._input_folder = Path(selected)
        self.input_folder_label.setText(f".../{self._input_folder.name}")
        self._append_log(f"📥 Pasta de Entrada configurada: {selected}\n", "info")

        # Sugere pasta de saída padrão se ainda não escolhida
        if self._output_folder is None:
            self._output_folder = self._input_folder / "Rolos_Prontos"
            self.output_folder_label.setText(f".../{self._output_folder.name}")
            self._append_log(f"📁 Pasta de Saída sugerida: {self._output_folder}\n", "muted")

    def _choose_output_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Saída de Rolos")
        if not selected:
            return
        self._output_folder = Path(selected)
        self.output_folder_label.setText(f".../{self._output_folder.name}")
        self._append_log(f"📁 Pasta de Saída configurada: {selected}\n", "info")

    def _toggle_agent(self) -> None:
        if self._is_active:
            self._stop_agent()
        else:
            self._start_agent()

    def _start_agent(self) -> None:
        if self._input_folder is None:
            QMessageBox.critical(self, "Erro", "Selecione a Pasta de Entrada (Hot Folder) primeiro.")
            return

        if self._output_folder is None:
            self._output_folder = self._input_folder / "Rolos_Prontos"

        try:
            largura = float(self.width_input.text())
            margem = float(self.margin_input.text())
            espaco = float(self.spacing_input.text())
            step = int(self.step_input.text())
            inactivity = int(self.inactivity_input.text())
            settle = int(self.settle_input.text())
        except ValueError:
            QMessageBox.critical(self, "Erro", "Verifique os valores numéricos das configurações.")
            return

        perf_mode = "balanced"
        for val, r in self.performance_radios.items():
            if r.isChecked():
                perf_mode = val
                break

        config = HotFolderConfig(
            input_folder=self._input_folder,
            output_folder=self._output_folder,
            largura_cm=largura,
            margem_cm=margem,
            espaco_cm=espaco,
            step_px=step,
            allow_rotate=self.rotate_checkbox.isChecked(),
            performance_mode=perf_mode,
            inactivity_seconds=inactivity,
            settle_seconds=settle,
            group_by_material=self.group_material_checkbox.isChecked(),
            move_processed=self.move_processed_checkbox.isChecked(),
        )

        self._worker_thread = QThread(self)
        self._worker = HotFolderWorker(config)
        self._worker.moveToThread(self._worker_thread)

        self._worker_thread.started.connect(self._worker.start)
        self._worker.log.connect(self._append_log)
        self._worker.status.connect(self._handle_status_changed)
        self._worker.file_detected.connect(self._handle_file_detected)
        self._worker.file_staged.connect(self._handle_file_staged)
        self._worker.queue_cleared.connect(self._handle_queue_cleared)
        self._worker.roll_completed.connect(self._handle_roll_completed)
        self._worker.stats_updated.connect(self._handle_stats_updated)

        self._worker_thread.start()
        self._is_active = True

        self.toggle_agent_btn.setText("PAUSAR AGENTE MONITORADOR")
        self.toggle_agent_btn.setStyleSheet(
            "background-color: #c62828; color: white; font-weight: bold; font-size: 13px; border-radius: 8px;"
        )
        self.force_pack_btn.setEnabled(True)

    def _stop_agent(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(2000)
            self._worker_thread = None
            self._worker = None

        self._is_active = False
        self.toggle_agent_btn.setText("INICIAR AGENTE MONITORADOR")
        self.toggle_agent_btn.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; font-size: 13px; border-radius: 8px;"
        )
        self.force_pack_btn.setEnabled(False)
        self._handle_status_changed("PAUSADO")

    def _force_pack_now(self) -> None:
        if self._worker is not None and self._staged_items:
            self._append_log("⚡ Disparo manual solicitado pelo operador!\n", "info")
            self._worker._pack_staged_batch()

    @Slot(str)
    def _handle_status_changed(self, status: str) -> None:
        if status == "MONITORANDO":
            self.status_badge.setText("🟢 AGENTE ATIVO - MONITORANDO")
            self.status_badge.setStyleSheet(
                "background: rgba(166, 227, 161, 0.2); color: #a6e3a1; font-weight: bold; "
                "font-size: 13px; border-radius: 6px; padding: 6px 14px; border: 1px solid #a6e3a1;"
            )
        elif status == "PROCESSANDO":
            self.status_badge.setText("🟡 MONTANDO ROLO AUTOMÁTICO...")
            self.status_badge.setStyleSheet(
                "background: rgba(249, 226, 175, 0.2); color: #f9e2af; font-weight: bold; "
                "font-size: 13px; border-radius: 6px; padding: 6px 14px; border: 1px solid #f9e2af;"
            )
        else:
            self.status_badge.setText("⚪ AGENTE PAUSADO")
            self.status_badge.setStyleSheet(
                "background: rgba(255, 255, 255, 0.1); color: #cdd6f4; font-weight: bold; "
                "font-size: 13px; border-radius: 6px; padding: 6px 14px; border: 1px solid rgba(255,255,255,0.2);"
            )

    @Slot(str)
    def _handle_file_detected(self, filename: str) -> None:
        pass

    @Slot(dict)
    def _handle_file_staged(self, item: dict) -> None:
        self._staged_items.append(item)
        self.kpi_queue_lbl.setText(f"📥 {len(self._staged_items)} Artes na Fila")

        # Adiciona miniatura visual na aba Fila
        thumb = item.get("thumbnail")
        if thumb is not None:
            pixmap = pil_to_qpixmap(thumb)
            category = item.get("category", "Geral")
            cat_conf = float(item.get("category_confidence", 0.0))
            quality = item.get("quality", "N/A")
            name = item.get("name", "Arte")
            conf_str = f" ({cat_conf:.0f}%)" if cat_conf > 0 else ""
            list_item = QListWidgetItem(f"{name}\n🏷️ {category}{conf_str}  ★ {quality.upper()}")
            list_item.setIcon(QIcon(pixmap))
            list_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.queue_list.addItem(list_item)

    @Slot()
    def _handle_queue_cleared(self) -> None:
        self._staged_items.clear()
        self.queue_list.clear()
        self.kpi_queue_lbl.setText("📥 0 Artes na Fila")

    @Slot(object)
    def _handle_roll_completed(self, result: RollerPackResult) -> None:
        self._roll_history.append(result)
        self._add_history_card(result)

    @Slot(dict)
    def _handle_stats_updated(self, stats: dict) -> None:
        self.kpi_received_lbl.setText(f"📦 {stats.get('received_count', 0)} Recebidas Hoje")
        self.kpi_rolls_lbl.setText(f"🚀 {stats.get('rolls_generated', 0)} Rolos Gerados")
        self.kpi_activity_lbl.setText(f"⏱️ {stats.get('last_active', 'Agora')}")

    def _add_history_card(self, result: RollerPackResult) -> None:
        card = QFrame()
        card.setObjectName("fieldCard")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(16)

        # Thumbnail do rolo
        max_thumb_h = 100
        img = result.final_image
        ratio = max_thumb_h / max(1, img.height)
        thumb_w = max(1, int(img.width * ratio))
        thumb_img = img.resize((thumb_w, max_thumb_h), Image.Resampling.BILINEAR)
        thumb_lbl = QLabel()
        thumb_lbl.setPixmap(pil_to_qpixmap(_checkerboard_image(thumb_img)))
        thumb_lbl.setFixedSize(thumb_w, max_thumb_h)
        card_layout.addWidget(thumb_lbl)

        # Informações
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        title_lbl = QLabel(f"📄 {result.output_path.name}")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #cdd6f4;")
        info_layout.addWidget(title_lbl)

        details_lbl = QLabel(
            f"Dimensões: {result.final_width_px}×{result.final_height_px}px "
            f"({result.final_width_px / 100 * 2.54:.1f}cm × {result.final_height_px / 100 * 2.54:.1f}cm)  ·  "
            f"Aproveitamento: {result.yield_pct}%  ·  Artes: {result.packed_count}"
        )
        details_lbl.setObjectName("muted")
        info_layout.addWidget(details_lbl)
        card_layout.addLayout(info_layout, 1)

        # Botão abrir pasta
        open_btn = QPushButton("Abrir Pasta")
        open_btn.setMinimumHeight(32)
        open_btn.clicked.connect(lambda: self._open_file_location(result.output_path))
        card_layout.addWidget(open_btn)

        # Insere no topo da lista
        self.history_layout.insertWidget(0, card)

    def _open_file_location(self, path: Path) -> None:
        if path.exists():
            if os.name == "nt":
                subprocess.run(["explorer", f"/select,{str(path)}"])
            else:
                subprocess.run(["xdg-open", str(path.parent)])

    def _append_log(self, text: str, level: str = "info") -> None:
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_output.setTextCursor(cursor)
        self.log_output.insertPlainText(text)
        self.log_output.ensureCursorVisible()

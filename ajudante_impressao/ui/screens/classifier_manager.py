from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from PIL import Image
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...algorithms.classifier import (
    ClassificationResult,
    get_prod_classifier,
    get_quality_classifier,
)
from ..common import ScreenScaffold
from .roll_packer import pil_to_qpixmap


class ClassifierManagerWidget(QWidget, ScreenScaffold):
    """Tela de Gerenciamento da Inteligência: Categorias, Regras, Treino e Diagnóstico."""

    def __init__(self):
        super().__init__()
        self.prod_cls = get_prod_classifier()
        self.qual_cls = get_quality_classifier()
        self._test_image: Optional[Image.Image] = None
        self._test_image_path: Optional[Path] = None
        self._build_ui()
        self._refresh_all_data()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        sidebar = self.wrap_sidebar(self._build_sidebar(), 360)
        main_panel = self._build_main()
        layout.addWidget(sidebar, 0)
        layout.addWidget(main_panel, 1)

    def _build_sidebar(self) -> QWidget:
        frame, layout = self.build_sidebar_frame(360)
        layout.addWidget(
            self.build_sidebar_header(
                "CENTRAL DE IA", "Controle de materiais, regras e aprendizado", "v2.0"
            )
        )

        # ── Pastas de Treinamento ─────────────────────────────────────────────
        layout.addWidget(self.section_label("DIRETÓRIO DE TREINAMENTO"))

        layout.addWidget(self.field_label("Pasta de Treino Ativa"))
        self.training_path_lbl = QLabel()
        self.training_path_lbl.setWordWrap(True)
        self.training_path_lbl.setObjectName("muted")
        layout.addWidget(self.training_path_lbl)

        btn_pick_dir = QPushButton("Alterar Pasta de Treino")
        btn_pick_dir.clicked.connect(self._change_training_dir)
        layout.addWidget(btn_pick_dir)

        btn_open_dir = QPushButton("Abrir Pasta no Explorer")
        btn_open_dir.clicked.connect(self._open_training_folder)
        layout.addWidget(btn_open_dir)

        # ── Operações de Treinamento ─────────────────────────────────────────
        layout.addWidget(self.section_label("AÇÕES DO MODELO"))

        self.btn_retrain = QPushButton("🔄 FORÇAR RETREINO COMPLETO")
        self.btn_retrain.setObjectName("accent")
        self.btn_retrain.setMinimumHeight(44)
        self.btn_retrain.clicked.connect(self._force_retrain)
        layout.addWidget(self.btn_retrain)

        btn_clear_cache = QPushButton("Limpar Cache Local")
        btn_clear_cache.clicked.connect(self._clear_cache)
        layout.addWidget(btn_clear_cache)

        # ── Status do Cache ──────────────────────────────────────────────────
        layout.addWidget(self.section_label("STATUS DA BASE"))
        self.status_box = QGroupBox()
        s_layout = QVBoxLayout(self.status_box)
        s_layout.setContentsMargins(12, 10, 12, 10)
        s_layout.setSpacing(6)

        self.lbl_cache_status = QLabel("Carregando...")
        self.lbl_cache_status.setObjectName("muted")
        s_layout.addWidget(self.lbl_cache_status)

        layout.addWidget(self.status_box)
        layout.addStretch(1)

        return frame

    def _build_main(self) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # ── KPI Cards no Topo ────────────────────────────────────────────────
        kpi_bar = QFrame()
        kpi_bar.setObjectName("card")
        kpi_layout = QHBoxLayout(kpi_bar)
        kpi_layout.setContentsMargins(18, 14, 18, 14)
        kpi_layout.setSpacing(16)

        self.kpi_categories = QLabel("🏷️ 0 Categorias")
        self.kpi_categories.setStyleSheet("font-weight: 800; font-size: 15px; color: #89B4FA;")
        kpi_layout.addWidget(self.kpi_categories)

        self.kpi_samples = QLabel("📦 0 Amostras Treinadas")
        self.kpi_samples.setStyleSheet("font-weight: 800; font-size: 15px; color: #A6E3A1;")
        kpi_layout.addWidget(self.kpi_samples)

        self.kpi_quality = QLabel("★ Qualidade Mapeada")
        self.kpi_quality.setStyleSheet("font-weight: 800; font-size: 15px; color: #F9E2AF;")
        kpi_layout.addWidget(self.kpi_quality)

        kpi_layout.addStretch(1)
        layout.addWidget(kpi_bar)

        # ── Tabs Centrais ────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_categories_tab(), "🏷️ Categorias de Materiais")
        self.tabs.addTab(self._build_rules_tab(), "📌 Regras por Nome & Palavras-Chave")
        self.tabs.addTab(self._build_test_lab_tab(), "🔬 Laboratório de Diagnóstico (Test Lab)")
        layout.addWidget(self.tabs, 1)

        return frame

    # ── Aba 1: Categorias ────────────────────────────────────────────────────
    def _build_categories_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Barra de ferramentas
        tb = QHBoxLayout()
        btn_add = QPushButton("+ Nova Categoria")
        btn_add.setObjectName("accent")
        btn_add.clicked.connect(self._add_category_dialog)
        tb.addWidget(btn_add)

        btn_rename = QPushButton("Renomear Selecionada")
        btn_rename.clicked.connect(self._rename_category_dialog)
        tb.addWidget(btn_rename)

        btn_delete = QPushButton("Excluir Categoria")
        btn_delete.setStyleSheet("background-color: #7f1d1d; color: #fca5a5; font-weight: bold;")
        btn_delete.clicked.connect(self._delete_category_dialog)
        tb.addWidget(btn_delete)

        tb.addStretch(1)
        btn_refresh = QPushButton("Atualizar Lista")
        btn_refresh.clicked.connect(self._refresh_all_data)
        tb.addWidget(btn_refresh)
        layout.addLayout(tb)

        # Tabela de Categorias
        self.cat_table = QTableWidget()
        self.cat_table.setColumnCount(4)
        self.cat_table.setHorizontalHeaderLabels([
            "Categoria / Material", "Amostras Treinadas", "Regras Vinculadas", "Ação"
        ])
        self.cat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cat_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.cat_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.cat_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.cat_table.verticalHeader().setVisible(False)
        self.cat_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.cat_table, 1)

        return widget

    # ── Aba 2: Regras de Palavras-Chave ──────────────────────────────────────
    def _build_rules_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        info_lbl = QLabel(
            "Configure palavras-chave e tags presentes no nome do arquivo. "
            "Quando uma regra corresponde, ela confere prioridade máxima e acelera a classificação."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setObjectName("muted")
        layout.addWidget(info_lbl)

        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(3)
        self.rules_table.setHorizontalHeaderLabels([
            "Categoria", "Termos / Palavras-chave (separadas por vírgula)", "Salvar"
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.verticalHeader().setVisible(False)
        layout.addWidget(self.rules_table, 1)

        return widget

    # ── Aba 3: Laboratório de Diagnóstico ────────────────────────────────────
    def _build_test_lab_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        # Painel Esquerdo: Imagem & Botão
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        btn_select_img = QPushButton("Selecionar Imagem para Teste")
        btn_select_img.setObjectName("accent")
        btn_select_img.setMinimumHeight(40)
        btn_select_img.clicked.connect(self._select_test_image)
        left_col.addWidget(btn_select_img)

        self.img_preview_lbl = QLabel("Nenhuma imagem selecionada\n\nClique no botão acima")
        self.img_preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_preview_lbl.setStyleSheet(
            "background: #111215; border: 2px dashed #313244; border-radius: 8px; color: #6c7086;"
        )
        self.img_preview_lbl.setFixedSize(280, 360)
        left_col.addWidget(self.img_preview_lbl)

        self.test_file_name_lbl = QLabel("")
        self.test_file_name_lbl.setWordWrap(True)
        self.test_file_name_lbl.setObjectName("muted")
        left_col.addWidget(self.test_file_name_lbl)
        left_col.addStretch(1)

        layout.addLayout(left_col, 0)

        # Painel Direito: Resultados Diagnósticos
        right_col = QVBoxLayout()
        right_col.setSpacing(14)

        # Card de Diagnóstico Principal
        diag_card = QFrame()
        diag_card.setObjectName("card")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setContentsMargins(16, 14, 16, 14)
        diag_layout.setSpacing(10)

        self.res_category_lbl = QLabel("🏷️ Material: --")
        self.res_category_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #89B4FA;")
        diag_layout.addWidget(self.res_category_lbl)

        self.conf_bar = QProgressBar()
        self.conf_bar.setRange(0, 100)
        self.conf_bar.setValue(0)
        self.conf_bar.setTextVisible(True)
        self.conf_bar.setFormat("Confiança da IA: %v%")
        self.conf_bar.setStyleSheet(
            "QProgressBar { background: #313244; border-radius: 6px; text-align: center; font-weight: bold; height: 24px; }"
            "QProgressBar::chunk { background: #A6E3A1; border-radius: 6px; }"
        )
        diag_layout.addWidget(self.conf_bar)

        self.res_quality_lbl = QLabel("★ Qualidade: --")
        self.res_quality_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #F9E2AF;")
        diag_layout.addWidget(self.res_quality_lbl)

        self.res_rule_lbl = QLabel("")
        self.res_rule_lbl.setObjectName("muted")
        diag_layout.addWidget(self.res_rule_lbl)

        right_col.addWidget(diag_card)

        # Card de Métricas Físicas e Geométricas
        metrics_card = QFrame()
        metrics_card.setObjectName("card")
        m_layout = QVBoxLayout(metrics_card)
        m_layout.setContentsMargins(16, 12, 16, 12)
        m_layout.setSpacing(8)

        m_title = QLabel("PARÂMETROS GEOMÉTRICOS & DE NITIDEZ")
        m_title.setObjectName("section")
        m_layout.addWidget(m_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        self.m_aspect = QLabel("--")
        self.m_dim = QLabel("--")
        self.m_fill = QLabel("--")
        self.m_contour = QLabel("--")
        self.m_edges = QLabel("--")
        self.m_sharpness = QLabel("--")

        grid.addWidget(QLabel("Proporção (AR):"), 0, 0)
        grid.addWidget(self.m_aspect, 0, 1)
        grid.addWidget(QLabel("Dimensão Física:"), 0, 2)
        grid.addWidget(self.m_dim, 0, 3)

        grid.addWidget(QLabel("Ocupação (Fill Ratio):"), 1, 0)
        grid.addWidget(self.m_fill, 1, 1)
        grid.addWidget(QLabel("Complexidade Contorno:"), 1, 2)
        grid.addWidget(self.m_contour, 1, 3)

        grid.addWidget(QLabel("Densidade de Bordas:"), 2, 0)
        grid.addWidget(self.m_edges, 2, 1)
        grid.addWidget(QLabel("Nitidez Normalizada:"), 2, 2)
        grid.addWidget(self.m_sharpness, 2, 3)

        m_layout.addLayout(grid)
        right_col.addWidget(metrics_card)

        # Alternativas
        self.alternatives_lbl = QLabel("Alternativas calculadas: Nenhuma análise executada.")
        self.alternatives_lbl.setObjectName("muted")
        right_col.addWidget(self.alternatives_lbl)

        # Botão Ensinar
        teach_row = QHBoxLayout()
        self.teach_btn = QPushButton("🧠 Ensinar esta imagem ao modelo")
        self.teach_btn.setStyleSheet(
            "background-color: #1e3a8a; color: #bfdbfe; font-weight: bold; padding: 10px; border-radius: 6px;"
        )
        self.teach_btn.setEnabled(False)
        self.teach_btn.clicked.connect(self._teach_current_test_image)
        teach_row.addWidget(self.teach_btn)
        teach_row.addStretch(1)
        right_col.addLayout(teach_row)

        right_col.addStretch(1)
        layout.addLayout(right_col, 1)

        return widget

    # ── Métodos de Dados e Ações ─────────────────────────────────────────────
    def _refresh_all_data(self) -> None:
        self.prod_cls = get_prod_classifier()
        self.qual_cls = get_quality_classifier()

        p_stats = self.prod_cls.get_stats()
        q_stats = self.qual_cls.get_stats()

        # Atualizar Sidebar
        self.training_path_lbl.setText(str(self.prod_cls.training_dir))
        self.lbl_cache_status.setText(
            f"Cache Produção: {'✓ Ativo' if p_stats['cache_exists'] else '✗ Ausente'}\n"
            f"Cache Qualidade: {'✓ Ativo' if q_stats['cache_exists'] else '✗ Ausente'}\n"
            f"Total Amostras Prod: {p_stats['total_samples']}\n"
            f"Total Amostras Qual: {q_stats['total_samples']}"
        )

        # Atualizar KPIs
        self.kpi_categories.setText(f"🏷️ {p_stats['total_categories']} Categorias")
        self.kpi_samples.setText(f"📦 {p_stats['total_samples']} Amostras Treinadas")
        self.kpi_quality.setText(f"★ {q_stats['total_categories']} Níveis de Qualidade")

        # Atualizar Tabela de Categorias
        self.cat_table.setRowCount(0)
        rules = self.prod_cls.rules_engine.rules
        counts = p_stats["category_counts"]

        for row_idx, cat_name in enumerate(sorted(self.prod_cls.category_names)):
            self.cat_table.insertRow(row_idx)

            # Coluna 0: Nome
            item_name = QTableWidgetItem(cat_name)
            item_name.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.cat_table.setItem(row_idx, 0, item_name)

            # Coluna 1: Amostras
            sample_count = counts.get(cat_name, 0)
            item_count = QTableWidgetItem(f"{sample_count} imagens")
            item_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cat_table.setItem(row_idx, 1, item_count)

            # Coluna 2: Regras
            cat_rules = rules.get(cat_name, [])
            rule_str = ", ".join(cat_rules) if cat_rules else "(Nenhuma regra de nome)"
            item_rules = QTableWidgetItem(rule_str)
            item_rules.setForeground(QColor("#9CA3AF"))
            self.cat_table.setItem(row_idx, 2, item_rules)

            # Coluna 3: Ação (Abrir Pasta)
            btn_open = QPushButton("Abrir")
            btn_open.setFixedHeight(26)
            btn_open.clicked.connect(lambda _, c=cat_name: self._open_category_folder(c))
            self.cat_table.setCellWidget(row_idx, 3, btn_open)

        # Atualizar Tabela de Regras
        self.rules_table.setRowCount(0)
        for row_idx, (cat_name, kws) in enumerate(rules.items()):
            self.rules_table.insertRow(row_idx)

            item_cat = QTableWidgetItem(cat_name)
            item_cat.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.rules_table.setItem(row_idx, 0, item_cat)

            kw_edit = QLineEdit(", ".join(kws))
            kw_edit.setObjectName("fieldInput")
            self.rules_table.setCellWidget(row_idx, 1, kw_edit)

            btn_save_rule = QPushButton("Salvar")
            btn_save_rule.setFixedHeight(28)
            btn_save_rule.clicked.connect(
                lambda _, c=cat_name, e=kw_edit: self._save_single_rule(c, e.text())
            )
            self.rules_table.setCellWidget(row_idx, 2, btn_save_rule)

    def _save_single_rule(self, category: str, raw_text: str) -> None:
        tokens = [t.strip().lower() for t in raw_text.split(",") if t.strip()]
        self.prod_cls.rules_engine.rules[category] = tokens
        self.prod_cls.rules_engine.save_rules()
        QMessageBox.information(
            self, "Regras Atualizadas", f"Regras para '{category}' salvas com sucesso!"
        )
        self._refresh_all_data()

    def _add_category_dialog(self) -> None:
        name, ok = QInputDialog.getText(self, "Nova Categoria", "Nome da categoria (ex: Adesivo Vinil):")
        if ok and name.strip():
            added = self.prod_cls.add_category(name.strip())
            if added:
                # Criar diretório físico se possível
                dest = self.prod_cls.training_dir / name.strip()
                dest.mkdir(parents=True, exist_ok=True)
                self._refresh_all_data()
                QMessageBox.information(self, "Sucesso", f"Categoria '{name.strip()}' criada com sucesso!")
            else:
                QMessageBox.warning(self, "Aviso", "Esta categoria já existe ou o nome é inválido.")

    def _rename_category_dialog(self) -> None:
        row = self.cat_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione uma categoria na tabela primeiro.")
            return
        old_name = self.cat_table.item(row, 0).text()
        new_name, ok = QInputDialog.getText(
            self, "Renomear Categoria", f"Novo nome para '{old_name}':", text=old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            renamed = self.prod_cls.rename_category(old_name, new_name.strip())
            if renamed:
                self._refresh_all_data()
                QMessageBox.information(self, "Sucesso", f"Categoria renomeada para '{new_name.strip()}'.")

    def _delete_category_dialog(self) -> None:
        row = self.cat_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione uma categoria na tabela primeiro.")
            return
        cat_name = self.cat_table.item(row, 0).text()
        confirm = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Deseja remover a categoria '{cat_name}' do modelo de classificação?\n(As imagens em disco serão mantidas).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.prod_cls.remove_category(cat_name)
            self._refresh_all_data()

    def _open_category_folder(self, category: str) -> None:
        cat_dir = self.prod_cls.training_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.run(["explorer", str(cat_dir)])
        else:
            subprocess.run(["xdg-open", str(cat_dir)])

    def _open_training_folder(self) -> None:
        t_dir = self.prod_cls.training_dir
        t_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.run(["explorer", str(t_dir)])
        else:
            subprocess.run(["xdg-open", str(t_dir)])

    def _change_training_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Selecione a Pasta de Treinamento")
        if chosen:
            self.prod_cls.training_dir = Path(chosen)
            self.prod_cls.train(force=True)
            self._refresh_all_data()
            QMessageBox.information(self, "Sucesso", f"Pasta de treino definida para:\n{chosen}")

    def _force_retrain(self) -> None:
        self.btn_retrain.setEnabled(False)
        self.btn_retrain.setText("Treinando...")
        try:
            self.prod_cls.train(force=True)
            self.qual_cls.train(force=True)
            self._refresh_all_data()
            QMessageBox.information(self, "Sucesso", "Retreinamento completo concluído com sucesso!")
        finally:
            self.btn_retrain.setEnabled(True)
            self.btn_retrain.setText("🔄 FORÇAR RETREINO COMPLETO")

    def _clear_cache(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Limpar Cache",
            "Deseja apagar os arquivos de cache locais e forçar releitura do disco?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if self.prod_cls.cache_file.exists():
                self.prod_cls.cache_file.unlink()
            if self.qual_cls.cache_file.exists():
                self.qual_cls.cache_file.unlink()
            self._force_retrain()

    # ── Métodos do Laboratório de Teste ──────────────────────────────────────
    def _select_test_image(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione uma Imagem para Testar",
            "",
            "Imagens (*.png *.jpg *.jpeg *.webp)",
        )
        if not chosen:
            return

        self._test_image_path = Path(chosen)
        try:
            with Image.open(self._test_image_path) as im:
                self._test_image = im.convert("RGBA").copy()

            # Gerar miniatura
            thumb = self._test_image.copy()
            thumb.thumbnail((260, 340), Image.Resampling.BILINEAR)
            self.img_preview_lbl.setPixmap(pil_to_qpixmap(thumb))
            self.test_file_name_lbl.setText(f"Arquivo: {self._test_image_path.name}")

            # Executar análise
            self._run_diagnostic_on_test_image()
            self.teach_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir a imagem: {e}")

    def _run_diagnostic_on_test_image(self) -> None:
        if self._test_image is None or self._test_image_path is None:
            return

        fname = self._test_image_path.name
        prod_res: ClassificationResult = self.prod_cls.classify_with_details(self._test_image, fname)
        qual_res: ClassificationResult = self.qual_cls.classify_with_details(self._test_image, fname)

        # Exibir Resultados
        self.res_category_lbl.setText(f"🏷️ Material: {prod_res.category}")
        self.conf_bar.setValue(int(prod_res.confidence_pct))

        # Cor da barra conforme confiança
        if prod_res.confidence_pct >= 80:
            bar_color = "#A6E3A1"  # Verde
        elif prod_res.confidence_pct >= 50:
            bar_color = "#F9E2AF"  # Amarelo
        else:
            bar_color = "#F38BA8"  # Vermelho

        self.conf_bar.setStyleSheet(
            "QProgressBar { background: #313244; border-radius: 6px; text-align: center; font-weight: bold; height: 24px; color: #CDD6F4; }"
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 6px; }}"
        )

        qual_color = "#A6E3A1" if qual_res.category == "boa" else "#F9E2AF" if qual_res.category == "aceitavel" else "#F38BA8"
        self.res_quality_lbl.setText(f"★ Qualidade: {qual_res.category.upper()} ({qual_res.confidence_pct:.0f}%)")
        self.res_quality_lbl.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {qual_color};")

        if prod_res.rule_matched:
            self.res_rule_lbl.setText(f"📌 Regra de Nome Casada: '{prod_res.rule_matched}' (+Bônus aplicado)")
        else:
            self.res_rule_lbl.setText("👁️ Classificação 100% Visual / Geométrica (Sem regra no nome)")

        # Métricas Físicas
        d = prod_res.details
        if d:
            self.m_aspect.setText(f"{d.get('aspect_ratio', 0):.2f}")
            self.m_dim.setText(f"{d.get('width_cm', 0):.1f} × {d.get('height_cm', 0):.1f} cm")
            self.m_fill.setText(f"{d.get('fill_ratio', 0):.1f}%")
            self.m_contour.setText(f"{d.get('contour_complexity', 0):.2f}")
            self.m_edges.setText(f"{d.get('edge_density', 0):.1f}%")
            self.m_sharpness.setText(f"{d.get('sharpness_tenengrad', 0):.1f} / {d.get('sharpness_laplacian_norm', 0):.1f}")

        # Alternativas
        if prod_res.alternatives:
            alts_str = " | ".join([f"<b>{c}</b>: {p:.1f}%" for c, p in prod_res.alternatives])
            self.alternatives_lbl.setText(f"Alternativas calculadas: {alts_str}")
        else:
            self.alternatives_lbl.setText("Sem alternativas próximas.")

    def _teach_current_test_image(self) -> None:
        if self._test_image is None or self._test_image_path is None:
            return

        cats = sorted(self.prod_cls.category_names)
        chosen_cat, ok = QInputDialog.getItem(
            self,
            "Ensinar Imagem ao Modelo",
            "Confirme ou selecione a categoria correta desta arte:",
            cats,
            0,
            False,
        )
        if ok and chosen_cat:
            success = self.prod_cls.learn_sample(
                image_or_path=self._test_image,
                category=chosen_cat,
                filename=self._test_image_path.name,
                save_to_disk=True,
            )
            if success:
                self._refresh_all_data()
                self._run_diagnostic_on_test_image()
                QMessageBox.information(
                    self,
                    "Aprendizado Concluído",
                    f"🧠 A imagem foi aprendida pelo modelo como '{chosen_cat}'!\n"
                    f"O classificador já foi atualizado em tempo real.",
                )

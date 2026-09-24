from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .screens.roll_packer import RoloPackerWidget
from .theme import build_stylesheet


class AjudanteImpressaoQtApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._theme = "light"
        self._build_ui()
        self._apply_theme(self._theme)

    def _build_ui(self) -> None:
        self.setWindowTitle("Studio de Impressao")
        self.resize(1420, 900)
        self.setMinimumSize(1220, 780)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("card")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)
        header_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)

        title = QLabel("STUDIO DE IMPRESSAO")
        title.setObjectName("title")
        title_row.addWidget(title)

        version_badge = QLabel("v1.1.0")
        version_badge.setObjectName("versionBadge")
        title_row.addWidget(version_badge, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch()

        self.theme_btn = QPushButton("🌙 Modo Escuro")
        self.theme_btn.setObjectName("toolBtn")
        self.theme_btn.setToolTip("Alternar entre Modo Claro e Modo Escuro")
        self.theme_btn.clicked.connect(self._toggle_theme)
        title_row.addWidget(self.theme_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        subtitle = QLabel("Operação inteligente de montagem de rolos, corte de painel e agente autônomo")
        subtitle.setObjectName("subtitle")

        header_layout.addLayout(title_row)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        self.main_content = RoloPackerWidget()
        layout.addWidget(self.main_content, 1)

    def _toggle_theme(self) -> None:
        new_theme = "dark" if self._theme == "light" else "light"
        self._apply_theme(new_theme)
        if new_theme == "light":
            self.theme_btn.setText("🌙 Modo Escuro")
        else:
            self.theme_btn.setText("☀️ Modo Claro")

    def _apply_theme(self, theme_name: str) -> None:
        self._theme = theme_name
        stylesheet = build_stylesheet(theme_name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)


def main() -> int:
    app = QApplication(sys.argv)
    window = AjudanteImpressaoQtApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

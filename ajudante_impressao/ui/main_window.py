from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .screens.cut_panel import CutPanelWidget
from .screens.roll_packer import RoloPackerWidget
from .theme import build_stylesheet


class AjudanteImpressaoQtApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._theme = "dark"
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
        layout.setSpacing(18)

        header = QFrame()
        header.setObjectName("card")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 18)
        header_layout.setSpacing(8)

        title = QLabel("STUDIO DE IMPRESSAO")
        title.setObjectName("title")
        title.setFont(QFont("Courier New", 22, QFont.Weight.Bold))
        subtitle = QLabel("Operacao focada em montagem de rolo e corte de painel")
        subtitle.setObjectName("subtitle")
        subtitle.setFont(QFont("Courier New", 11))

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(RoloPackerWidget(), "Rolo Packer")
        self.tabs.addTab(CutPanelWidget(), "Cut Panel")
        layout.addWidget(self.tabs, 1)

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

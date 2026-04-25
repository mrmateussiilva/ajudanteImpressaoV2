from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .screens.art_finisher import ArtFinisherWidget
from .screens.automation import AutomationWidget
from .screens.cut_panel import CutPanelWidget
from .screens.image_resizer import ImageResizerWidget
from .screens.roll_packer import RoloPackerWidget
from .theme import build_stylesheet


class AjudanteImpressaoQtApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._theme = "dark"
        self._build_ui()
        self._apply_theme(self._theme)

    def _build_ui(self) -> None:
        self.setWindowTitle("Ajudante de Impressao")
        self.resize(1440, 900)
        self.setMinimumSize(1180, 760)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("card")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(6)

        title = QLabel("AJUDANTE DE IMPRESSAO")
        title.setObjectName("title")
        title.setFont(QFont("Courier New", 22, QFont.Weight.Bold))
        subtitle = QLabel("Ferramentas separadas para montagem de rolo e corte de painel")
        subtitle.setObjectName("subtitle")
        subtitle.setFont(QFont("Courier New", 11))

        self.theme_selector = QComboBox()
        self.theme_selector.addItem("Dark", "dark")
        self.theme_selector.addItem("Light", "light")
        self.theme_selector.currentIndexChanged.connect(self._handle_theme_change)
        self.theme_selector.setMaximumWidth(140)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        header_layout.addWidget(self.theme_selector, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(RoloPackerWidget(), "Rolo Packer")
        self.tabs.addTab(CutPanelWidget(), "Cut Panel")
        self.tabs.addTab(ImageResizerWidget(), "Redimensionar")
        self.tabs.addTab(ArtFinisherWidget(), "Acabamento")
        self.tabs.addTab(AutomationWidget(), "Automacao")
        layout.addWidget(self.tabs, 1)

    def _handle_theme_change(self) -> None:
        self._apply_theme(self.theme_selector.currentData())

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

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ScreenScaffold:
    def wrap_sidebar(self, widget: QWidget, width: int) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(width)
        scroll.setWidget(widget)
        return scroll

    def build_sidebar_frame(self, width: int = 360) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setFixedWidth(width)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        return frame, layout

    def build_sidebar_header(self, title_text: str, subtitle_text: str) -> QFrame:
        header = QFrame()
        header.setObjectName("panel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("title")
        title.setFont(QFont("Courier New", 16, QFont.Weight.Bold))

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        return header

    def section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        label.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        return label

    def field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        label.setFont(QFont("Courier New", 10))
        return label

    def add_field_card(
        self,
        label_text: str,
        default: str,
        suffix: str,
        grid: QGridLayout,
        row: int,
        column: int,
        label_attr_name: str | None = None,
    ) -> QLineEdit:
        card = QFrame()
        card.setObjectName("fieldCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        label = label_text if not suffix else f"{label_text} ({suffix})"
        field_label = self.field_label(label)
        card_layout.addWidget(field_label)

        entry = QLineEdit()
        entry.setObjectName("fieldInput")
        entry.setText(default)
        entry.setMinimumHeight(36)
        card_layout.addWidget(entry)
        grid.addWidget(card, row, column)

        if label_attr_name:
            setattr(self, label_attr_name, field_label)
        return entry

    def build_status_panel(self, initial_text: str) -> tuple[QFrame, QLabel, QProgressBar]:
        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)

        status_label = QLabel(initial_text)
        status_label.setObjectName("muted")

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(False)
        progress.setMaximumWidth(220)

        status_layout.addWidget(status_label, 1)
        status_layout.addWidget(progress)
        return status_card, status_label, progress

    def build_log_output(self) -> QPlainTextEdit:
        output = QPlainTextEdit()
        output.setReadOnly(True)
        output.setFont(QFont("Courier New", 10))
        return output

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PIL import Image


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

    def build_sidebar_header(self, title_text: str, subtitle_text: str, version_text: str = "v1.0.1") -> QFrame:
        header = QFrame()
        header.setObjectName("panel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        header_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        title = QLabel(title_text)
        title.setObjectName("title")
        title_row.addWidget(title, 1)

        version_badge = QLabel(version_text)
        version_badge.setObjectName("versionBadge")
        title_row.addWidget(version_badge, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        header_layout.addLayout(title_row)
        header_layout.addWidget(subtitle)
        return header

    def section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
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
        output.setFont(QFont("Consolas", 11))
        return output


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    """Converte imagem Pillow (RGBA ou RGB) para QPixmap."""
    from PySide6.QtGui import QImage
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimage = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


class _InteractiveGraphicsView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setStyleSheet("QGraphicsView { background: transparent; border: none; }")

        # Fundo xadrez suave acelerado pelo Qt para visualizar transparência
        tile = 16
        bg_pix = QPixmap(tile * 2, tile * 2)
        p = QPainter(bg_pix)
        p.fillRect(0, 0, tile, tile, QColor("#14161A"))
        p.fillRect(tile, tile, tile, tile, QColor("#14161A"))
        p.fillRect(tile, 0, tile, tile, QColor("#1B1E24"))
        p.fillRect(0, tile, tile, tile, QColor("#1B1E24"))
        p.end()
        self.setBackgroundBrush(QBrush(bg_pix))

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._current_scale: float = 1.0

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.scene().clear()
        self._pixmap_item = self.scene().addPixmap(pixmap)
        self.setSceneRect(QRectF(pixmap.rect()))
        self.fit_in_view()

    def fit_in_view(self) -> None:
        if not self._pixmap_item:
            return
        if self.viewport().width() <= 10 or self.viewport().height() <= 10:
            QTimer.singleShot(50, self.fit_in_view)
            return
        self.resetTransform()
        rect = self.sceneRect()
        if rect.width() > 0 and rect.height() > 0:
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            transform = self.transform()
            self._current_scale = transform.m11()
            self.zoom_changed.emit(self._current_scale)

    def zoom_100(self) -> None:
        if not self._pixmap_item:
            return
        self.resetTransform()
        self._current_scale = 1.0
        self.zoom_changed.emit(self._current_scale)

    def zoom_by(self, factor: float) -> None:
        if not self._pixmap_item:
            return
        new_scale = self._current_scale * factor
        if 0.01 <= new_scale <= 40.0:
            self.scale(factor, factor)
            self._current_scale = new_scale
            self.zoom_changed.emit(self._current_scale)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._pixmap_item:
            super().wheelEvent(event)
            return
        factor = 1.18 if event.angleDelta().y() > 0 else 1.0 / 1.18
        self.zoom_by(factor)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._pixmap_item:
            self.fit_in_view()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class ZoomablePreviewWidget(QWidget):
    """
    Visualizador interativo de alta performance com suporte a Zoom (scroll do mouse),
    Pan (arrastar com botão esquerdo), centralização e ajuste automático.
    """
    def __init__(self, placeholder_text: str = "A prévia aparecerá aqui.", parent: QWidget | None = None):
        super().__init__(parent)
        self._placeholder_text = placeholder_text
        self._pixmap: QPixmap | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Viewport gráfica interativa (instanciada antes para os botões conectarem aos slots)
        self._view = _InteractiveGraphicsView(self)
        self._view.zoom_changed.connect(self._on_zoom_changed)

        # Barra de ferramentas superior
        self._toolbar = QFrame()
        self._toolbar.setObjectName("card")
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(8)

        self._info_label = QLabel(self._placeholder_text)
        self._info_label.setObjectName("muted")
        font = self._info_label.font()
        font.setPointSize(10)
        self._info_label.setFont(font)
        tb_layout.addWidget(self._info_label, 1)

        btn_style = (
            "QPushButton {"
            "  background: #1D2024;"
            "  border: 1px solid rgba(255,255,255,0.1);"
            "  border-radius: 4px;"
            "  color: #F3F4F6;"
            "  font-size: 11px;"
            "  font-weight: bold;"
            "  padding: 3px 8px;"
            "  min-height: 24px;"
            "}"
            "QPushButton:hover { background: #2563EB; border-color: #3B82F6; }"
        )

        self._btn_zoom_out = QPushButton("−")
        self._btn_zoom_out.setToolTip("Diminuir Zoom (ou role o mouse para baixo)")
        self._btn_zoom_out.setFixedWidth(28)
        self._btn_zoom_out.setStyleSheet(btn_style)
        self._btn_zoom_out.clicked.connect(lambda: self._view.zoom_by(1.0 / 1.25))
        tb_layout.addWidget(self._btn_zoom_out)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setFixedWidth(46)
        self._zoom_label.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: bold;")
        tb_layout.addWidget(self._zoom_label)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setToolTip("Aumentar Zoom (ou role o mouse para cima)")
        self._btn_zoom_in.setFixedWidth(28)
        self._btn_zoom_in.setStyleSheet(btn_style)
        self._btn_zoom_in.clicked.connect(lambda: self._view.zoom_by(1.25))
        tb_layout.addWidget(self._btn_zoom_in)

        self._btn_fit = QPushButton("Ajustar")
        self._btn_fit.setToolTip("Ajustar imagem inteira na tela (ou clique duplo)")
        self._btn_fit.setStyleSheet(btn_style)
        self._btn_fit.clicked.connect(self._view.fit_in_view)
        tb_layout.addWidget(self._btn_fit)

        self._btn_100 = QPushButton("1:1")
        self._btn_100.setToolTip("Tamanho real dos pixels (100%)")
        self._btn_100.setStyleSheet(btn_style)
        self._btn_100.clicked.connect(self._view.zoom_100)
        tb_layout.addWidget(self._btn_100)

        layout.addWidget(self._toolbar)
        layout.addWidget(self._view, 1)

        self.clear()

    def _on_zoom_changed(self, scale: float) -> None:
        pct = int(round(scale * 100))
        self._zoom_label.setText(f"{pct}%")

    def set_pixmap(self, pixmap: QPixmap, info_text: str = "") -> None:
        self._pixmap = pixmap
        self._view.set_pixmap(pixmap)
        if info_text:
            self._info_label.setText(info_text)
        else:
            self._info_label.setText(f"{pixmap.width()} × {pixmap.height()} px")

    def set_image(self, img: Image.Image, info_text: str = "") -> None:
        pixmap = pil_to_qpixmap(img)
        self.set_pixmap(pixmap, info_text)

    def clear(self, placeholder_text: str = "") -> None:
        self._pixmap = None
        self._view.scene().clear()
        txt = placeholder_text or self._placeholder_text
        self._info_label.setText(txt)
        self._zoom_label.setText("100%")
        placeholder_item = self._view.scene().addText(txt)
        placeholder_item.setDefaultTextColor(QColor("#6B7280"))
        font = placeholder_item.font()
        font.setPointSize(11)
        placeholder_item.setFont(font)

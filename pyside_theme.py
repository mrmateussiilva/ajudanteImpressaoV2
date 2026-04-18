from __future__ import annotations


THEMES = {
    "dark": {
        "bg": "#0F1117",
        "card": "#1A1D27",
        "card_alt": "#12151F",
        "panel": "#0D1520",
        "border": "#2C3242",
        "text": "#E8EAF0",
        "muted": "#5A5F72",
        "accent": "#00C2A8",
        "accent_hover": "#009E88",
    },
    "light": {
        "bg": "#F4F6FA",
        "card": "#FFFFFF",
        "card_alt": "#E9EEF5",
        "panel": "#DCE3EE",
        "border": "#CAD3E0",
        "text": "#111827",
        "muted": "#6B7280",
        "accent": "#00A892",
        "accent_hover": "#008A78",
    },
}


def build_stylesheet(theme_name: str) -> str:
    colors = THEMES.get(theme_name, THEMES["dark"])
    return f"""
    QMainWindow, QWidget {{
        background: {colors['bg']};
        color: {colors['text']};
    }}
    QFrame#card, QGroupBox, QTabWidget::pane, QPlainTextEdit, QListWidget, QScrollArea, QComboBox, QLineEdit {{
        background: {colors['card']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
    }}
    QFrame#panel {{
        background: {colors['panel']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
    }}
    QLabel#title {{
        color: {colors['accent']};
        font-size: 22px;
        font-weight: 700;
    }}
    QLabel#subtitle, QLabel#section, QLabel#muted {{
        color: {colors['muted']};
    }}
    QLabel#section {{
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QLabel#fieldLabel {{
        color: {colors['muted']};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.4px;
        text-transform: uppercase;
        background: transparent;
        border: none;
        padding: 0;
    }}
    QFrame#fieldCard {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
    }}
    QLineEdit, QPlainTextEdit, QListWidget, QComboBox {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        padding: 8px;
        color: {colors['text']};
        selection-background-color: {colors['accent']};
    }}
    QLineEdit#fieldInput {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
        min-height: 22px;
        padding: 2px 0 0 0;
        color: {colors['text']};
        font-size: 14px;
        font-weight: 600;
    }}
    QLineEdit#fieldInput:focus {{
        border-color: transparent;
    }}
    QLineEdit#fieldInput[invalid="true"] {{
        color: #FF6B6B;
    }}
    QLineEdit::placeholder {{
        color: {colors['muted']};
    }}
    QPushButton {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        padding: 10px 14px;
        color: {colors['text']};
        font-weight: 600;
    }}
    QPushButton:hover {{
        border-color: {colors['accent']};
    }}
    QPushButton#accent {{
        background: {colors['accent']};
        color: #041311;
        border: none;
    }}
    QPushButton#accent:hover {{
        background: {colors['accent_hover']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus, QComboBox:focus {{
        border: 1px solid {colors['accent']};
    }}
    QRadioButton, QCheckBox {{
        spacing: 8px;
    }}
    QRadioButton::indicator, QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}
    QRadioButton::indicator {{
        border-radius: 8px;
        border: 1px solid {colors['muted']};
        background: {colors['card_alt']};
    }}
    QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
        background: {colors['accent']};
        border: 1px solid {colors['accent']};
    }}
    QCheckBox::indicator {{
        border-radius: 4px;
        border: 1px solid {colors['muted']};
        background: {colors['card_alt']};
    }}
    QTabBar::tab {{
        background: {colors['card_alt']};
        color: {colors['muted']};
        padding: 10px 14px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        margin-right: 4px;
    }}
    QTabBar::tab:selected {{
        background: {colors['accent']};
        color: #041311;
    }}
    QProgressBar {{
        border: 1px solid {colors['border']};
        border-radius: 6px;
        background: {colors['card_alt']};
        min-height: 14px;
        max-height: 14px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {colors['accent']};
        border-radius: 5px;
    }}
    """

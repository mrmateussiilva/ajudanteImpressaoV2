from __future__ import annotations


THEMES = {
    "light": {
        "bg": "#F8FAFC",               # Slate 50
        "card": "#FFFFFF",             # White
        "card_alt": "#F1F5F9",         # Slate 100
        "panel": "#FFFFFF",            # White
        "border": "#E2E8F0",           # Slate 200
        "border_focus": "#3B82F6",     # Blue 500
        "text": "#0F172A",             # Slate 900 - máxima legibilidade
        "text_secondary": "#334155",   # Slate 700
        "muted": "#64748B",            # Slate 500
        "input_bg": "#FFFFFF",         # White
        "input_border": "#CBD5E1",     # Slate 300
        "accent": "#2563EB",           # Blue 600
        "accent_hover": "#1D4ED8",     # Blue 700
        "danger": "#DC2626",           # Red 600
        "tab_bg": "#F1F5F9",
        "tab_selected_bg": "#FFFFFF",
        "tab_text": "#475569",
        "tab_selected_text": "#2563EB",
        "badge_bg": "#EFF6FF",
        "badge_border": "#BFDBFE",
        "badge_text": "#1D4ED8",
        "scroll_track": "#F1F5F9",
        "scroll_thumb": "#CBD5E1",
        "scroll_thumb_hover": "#94A3B8",
    },
    "dark": {
        "bg": "#0F172A",               # Slate 900
        "card": "#1E293B",             # Slate 800
        "card_alt": "#334155",         # Slate 700
        "panel": "#1E293B",            # Slate 800
        "border": "#334155",           # Slate 700
        "border_focus": "#60A5FA",     # Blue 400
        "text": "#F8FAFC",             # Slate 50
        "text_secondary": "#E2E8F0",   # Slate 200
        "muted": "#94A3B8",            # Slate 400
        "input_bg": "#0F172A",         # Slate 900
        "input_border": "#475569",     # Slate 600
        "accent": "#3B82F6",           # Blue 500
        "accent_hover": "#2563EB",     # Blue 600
        "danger": "#EF4444",           # Red 500
        "tab_bg": "#0F172A",
        "tab_selected_bg": "#1E293B",
        "tab_text": "#94A3B8",
        "tab_selected_text": "#60A5FA",
        "badge_bg": "rgba(59, 130, 246, 0.15)",
        "badge_border": "rgba(59, 130, 246, 0.3)",
        "badge_text": "#93C5FD",
        "scroll_track": "#0F172A",
        "scroll_thumb": "#334155",
        "scroll_thumb_hover": "#475569",
    },
}


def build_stylesheet(theme_name: str = "light") -> str:
    colors = THEMES.get(theme_name, THEMES["light"])
    
    return f"""
    * {{
        font-family: "Segoe UI", "Inter", "Roboto", "Helvetica Neue", sans-serif;
    }}
    
    QMainWindow, QWidget {{
        background: {colors['bg']};
        color: {colors['text']};
    }}
    
    /* Cards e Containers */
    QFrame#card {{
        background: {colors['card']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
    }}
    
    QFrame#panel {{
        background: {colors['panel']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
    }}
    
    QFrame#fieldCard {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
    }}
    
    QGroupBox {{
        background: {colors['card']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 14px;
        font-weight: 700;
        font-size: 13px;
        color: {colors['text']};
    }}
    
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        color: {colors['text_secondary']};
    }}
    
    /* Tipografia e Títulos */
    QLabel#title {{
        color: {colors['text']};
        font-size: 24px;
        font-weight: 800;
        letter-spacing: -0.5px;
    }}
    
    QLabel#subtitle {{
        color: {colors['muted']};
        font-size: 13px;
        font-weight: 400;
    }}
    
    QLabel#versionBadge {{
        background: {colors['badge_bg']};
        color: {colors['badge_text']};
        font-size: 12px;
        font-weight: 700;
        border: 1px solid {colors['badge_border']};
        border-radius: 6px;
        padding: 3px 8px;
    }}
    
    QLabel#section {{
        color: {colors['text']};
        font-size: 12px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        padding-top: 12px;
        padding-bottom: 4px;
    }}
    
    QLabel#fieldLabel {{
        color: {colors['text_secondary']};
        font-size: 12px;
        font-weight: 600;
        background: transparent;
        border: none;
        padding: 0 0 2px 0;
    }}
    
    QLabel#muted {{
        color: {colors['muted']};
        font-size: 13px;
    }}
    
    /* Inputs: QLineEdit, QDoubleSpinBox, QDateEdit, QComboBox */
    QLineEdit, QDoubleSpinBox, QSpinBox, QDateEdit {{
        background: {colors['input_bg']};
        border: 1px solid {colors['input_border']};
        border-radius: 6px;
        min-height: 34px;
        padding: 6px 10px;
        color: {colors['text']};
        selection-background-color: {colors['accent']};
        font-size: 13px;
        font-weight: 500;
    }}
    
    QLineEdit#fieldInput {{
        background: {colors['input_bg']};
        border: 1px solid {colors['input_border']};
        border-radius: 6px;
        min-height: 34px;
        padding: 6px 10px;
        color: {colors['text']};
        font-size: 13px;
        font-weight: 500;
    }}
    
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus {{
        border: 2px solid {colors['border_focus']};
        background: {colors['input_bg']};
    }}
    
    QLineEdit:hover:!focus, QDoubleSpinBox:hover:!focus, QSpinBox:hover:!focus, QDateEdit:hover:!focus {{
        border: 1px solid {colors['border_focus']};
    }}
    
    QLineEdit[invalid="true"] {{
        border: 2px solid {colors['danger']};
    }}
    
    QLineEdit::placeholder {{
        color: {colors['muted']};
    }}
    
    QComboBox {{
        background: {colors['input_bg']};
        border: 1px solid {colors['input_border']};
        border-radius: 6px;
        min-height: 34px;
        padding: 6px 12px;
        color: {colors['text']};
        font-size: 13px;
        font-weight: 500;
    }}
    
    QComboBox:hover {{
        border: 1px solid {colors['border_focus']};
    }}
    
    QComboBox:focus {{
        border: 2px solid {colors['border_focus']};
    }}
    
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    
    QComboBox QAbstractItemView {{
        background: {colors['card']};
        color: {colors['text']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
        selection-background-color: {colors['badge_bg']};
        selection-color: {colors['accent']};
        padding: 4px;
        outline: none;
    }}
    
    /* Botões */
    QPushButton {{
        background: {colors['card_alt']};
        border: 1px solid {colors['input_border']};
        border-radius: 6px;
        padding: 8px 16px;
        color: {colors['text']};
        font-size: 13px;
        font-weight: 600;
        min-height: 32px;
    }}
    
    QPushButton:hover {{
        background: {colors['border']};
        border: 1px solid {colors['muted']};
    }}
    
    QPushButton:pressed {{
        background: {colors['card_alt']};
    }}
    
    QPushButton#accent {{
        background: {colors['accent']};
        border: 1px solid {colors['accent_hover']};
        color: #FFFFFF;
        font-size: 14px;
        font-weight: 700;
        border-radius: 8px;
    }}
    
    QPushButton#accent:hover {{
        background: {colors['accent_hover']};
        border: 1px solid {colors['accent_hover']};
    }}
    
    QPushButton#accent:pressed {{
        background: {colors['accent_hover']};
    }}
    
    QPushButton#toolBtn {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
        color: {colors['text']};
        font-size: 12px;
        font-weight: 600;
        padding: 4px 10px;
        min-height: 28px;
    }}
    
    QPushButton#toolBtn:hover {{
        background: {colors['border']};
    }}
    
    QPushButton:disabled {{
        background: {colors['bg']};
        border: 1px solid {colors['border']};
        color: {colors['muted']};
    }}
    
    /* QTabWidget e QTabBar */
    QTabWidget {{
        background: transparent;
        border: none;
    }}
    
    QTabWidget::pane {{
        border: 1px solid {colors['border']};
        background: {colors['card']};
        border-radius: 10px;
        top: -1px;
    }}
    
    QTabBar::tab {{
        background: {colors['tab_bg']};
        color: {colors['tab_text']};
        border: 1px solid {colors['border']};
        border-bottom: none;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        padding: 8px 18px;
        font-size: 13px;
        font-weight: 600;
        margin-right: 4px;
    }}
    
    QTabBar::tab:selected {{
        background: {colors['tab_selected_bg']};
        color: {colors['tab_selected_text']};
        border-bottom: 2px solid {colors['accent']};
        font-weight: 700;
    }}
    
    QTabBar::tab:hover:!selected {{
        background: {colors['border']};
        color: {colors['text']};
    }}
    
    /* Checkboxes e Radios */
    QRadioButton, QCheckBox {{
        spacing: 8px;
        font-size: 13px;
        color: {colors['text']};
        font-weight: 500;
    }}
    
    QRadioButton::indicator, QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        background: {colors['input_bg']};
        border: 2px solid {colors['input_border']};
    }}
    
    QRadioButton::indicator {{
        border-radius: 10px;
    }}
    
    QCheckBox::indicator {{
        border-radius: 4px;
    }}
    
    QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
        background: {colors['accent']};
        border: 2px solid {colors['accent']};
    }}
    
    /* QProgressBar */
    QProgressBar {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 4px;
        min-height: 10px;
        max-height: 10px;
        text-align: center;
    }}
    
    QProgressBar::chunk {{
        background: {colors['accent']};
        border-radius: 3px;
    }}
    
    /* Áreas de Log e Listas */
    QPlainTextEdit {{
        background: {colors['card']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        color: {colors['text']};
        padding: 10px;
        font-family: "Consolas", "Courier New", monospace;
        font-size: 12px;
        selection-background-color: {colors['accent']};
    }}
    
    QListWidget {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        color: {colors['text']};
        padding: 8px;
    }}
    
    /* Scrollbars Modernas */
    QScrollBar:vertical {{
        border: none;
        background: {colors['scroll_track']};
        width: 10px;
        margin: 0px;
        border-radius: 5px;
    }}
    
    QScrollBar::handle:vertical {{
        background: {colors['scroll_thumb']};
        min-height: 28px;
        border-radius: 5px;
    }}
    
    QScrollBar::handle:vertical:hover {{
        background: {colors['scroll_thumb_hover']};
    }}
    
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    
    QScrollBar:horizontal {{
        border: none;
        background: {colors['scroll_track']};
        height: 10px;
        margin: 0px;
        border-radius: 5px;
    }}
    
    QScrollBar::handle:horizontal {{
        background: {colors['scroll_thumb']};
        min-width: 28px;
        border-radius: 5px;
    }}
    
    QScrollBar::handle:horizontal:hover {{
        background: {colors['scroll_thumb_hover']};
    }}
    
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    """

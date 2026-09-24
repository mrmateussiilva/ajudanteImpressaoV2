from __future__ import annotations


THEMES = {
    "dark": {
        "bg": "#09090B",         # Vercel-like deep dark (Zinc 950)
        "card": "#18181B",       # Elevated card (Zinc 900)
        "card_alt": "#27272A",   # Input background (Zinc 800)
        "panel": "#18181B",      # Sidebar panel
        "border": "#27272A",     # Subtle borders
        "border_focus": "#3F3F46",
        "text": "#FAFAFA",       # Crisp white
        "muted": "#A1A1AA",      # Zinc 400
        "accent": "#3B82F6",     # Vibrant Blue
        "accent_hover": "#2563EB",
        "danger": "#EF4444",
    }
}


def build_stylesheet(theme_name: str) -> str:
    colors = THEMES.get(theme_name, THEMES["dark"])
    
    return f"""
    * {{
        font-family: "Inter", "Segoe UI", "Roboto", "Helvetica Neue", sans-serif;
    }}
    
    QMainWindow, QWidget {{
        background: {colors['bg']};
        color: {colors['text']};
    }}
    
    /* Estruturas principais com bordas sutis e mais arredondadas */
    QFrame#card, QGroupBox, QPlainTextEdit, QListWidget, QScrollArea {{
        background: {colors['card']};
        border: 1px solid {colors['border']};
        border-radius: 12px;
    }}
    
    QFrame#panel {{
        background: {colors['panel']};
        border: 1px solid {colors['border']};
        border-radius: 12px;
    }}
    
    /* Tipografia Moderna */
    QLabel#title {{
        color: {colors['text']};
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.5px;
    }}
    
    QLabel#subtitle {{
        color: {colors['muted']};
        font-size: 14px;
        font-weight: 400;
    }}
    
    QLabel#versionBadge {{
        background: rgba(59, 130, 246, 0.1);
        color: {colors['accent']};
        font-size: 12px;
        font-weight: 700;
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 6px;
        padding: 4px 8px;
    }}
    
    QLabel#section {{
        color: {colors['text']};
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding-top: 12px;
        padding-bottom: 6px;
    }}
    
    QLabel#fieldLabel {{
        color: {colors['muted']};
        font-size: 13px;
        font-weight: 500;
        background: transparent;
        border: none;
        padding: 0 0 4px 0;
    }}
    
    QLabel#muted {{
        color: {colors['muted']};
    }}
    
    /* Inputs minimalistas e premium */
    QFrame#fieldCard {{
        background: transparent;
        border: none;
    }}
    
    QLineEdit, QPlainTextEdit, QListWidget, QComboBox {{
        background: {colors['bg']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        padding: 10px 14px;
        color: {colors['text']};
        selection-background-color: {colors['accent']};
        font-size: 14px;
    }}
    
    QLineEdit#fieldInput {{
        background: {colors['bg']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        min-height: 40px;
        padding: 10px 14px;
        color: {colors['text']};
        font-size: 14px;
        font-weight: 500;
    }}
    
    QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus, QComboBox:focus {{
        border: 1px solid {colors['accent']};
        background: {colors['card']};
    }}
    
    QLineEdit:hover:!focus, QComboBox:hover:!focus {{
        border: 1px solid {colors['border_focus']};
    }}
    
    QLineEdit[invalid="true"] {{
        border: 1px solid {colors['danger']};
    }}
    
    QLineEdit::placeholder {{
        color: {colors['muted']};
    }}
    
    /* Botões Flat Premium */
    QPushButton {{
        background: {colors['card_alt']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        padding: 12px 18px;
        color: {colors['text']};
        font-size: 14px;
        font-weight: 600;
    }}
    
    QPushButton:hover {{
        background: {colors['border_focus']};
        border: 1px solid {colors['muted']};
    }}
    
    QPushButton#accent {{
        background: {colors['accent']};
        border: 1px solid {colors['accent_hover']};
        color: #FFFFFF;
        font-weight: 700;
    }}
    
    QPushButton#accent:hover {{
        background: {colors['accent_hover']};
        border: 1px solid #1D4ED8;
    }}
    
    QPushButton:disabled {{
        background: {colors['bg']};
        border: 1px solid {colors['border']};
        color: {colors['border_focus']};
    }}
    
    /* Checkboxes e Radios clean */
    QRadioButton, QCheckBox {{
        spacing: 12px;
        font-size: 14px;
        color: {colors['text']};
        font-weight: 500;
    }}
    
    QRadioButton::indicator, QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        background: {colors['bg']};
        border: 1px solid {colors['border']};
    }}
    
    QRadioButton::indicator {{
        border-radius: 11px;
    }}
    
    QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
        background: {colors['accent']};
        border: 1px solid {colors['accent']};
    }}
    
    QCheckBox::indicator {{
        border-radius: 6px;
    }}
    
    /* Barra de progresso lisa e moderna */
    QProgressBar {{
        background: {colors['bg']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
        min-height: 12px;
        max-height: 12px;
        text-align: center;
    }}
    
    QProgressBar::chunk {{
        background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 {colors['accent_hover']}, stop:1 {colors['accent']});
        border-radius: 5px;
    }}
    
    /* Scrollbars invisíveis / elegantes */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {colors['border_focus']};
        min-height: 30px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {colors['muted']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """

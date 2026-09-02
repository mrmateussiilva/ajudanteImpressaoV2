from __future__ import annotations


THEMES = {
    "dark": {
        "bg": "#0D0E10",         # Fundo principal ultra limpo
        "card": "#15171A",       # Fundo dos blocos principais (quase invisível contraste)
        "card_alt": "#1D2024",   # Fundo de campos/botões (ligeiramente mais claro)
        "panel": "#15171A",      # Painéis laterais
        "border": "transparent", # Sem bordas visíveis, focando em padding
        "text": "#F3F4F6",       # Texto branco suave
        "muted": "#9CA3AF",      # Cinza legível para labels secundárias
        "accent": "#3B82F6",     # Azul moderno de destaque (Blue 500 do Tailwind)
        "accent_hover": "#2563EB",
        "danger": "#EF4444",
    },
    "light": {
        "bg": "#F9FAFB",
        "card": "#FFFFFF",
        "card_alt": "#F3F4F6",
        "panel": "#FFFFFF",
        "border": "transparent",
        "text": "#111827",
        "muted": "#6B7280",
        "accent": "#2563EB",
        "accent_hover": "#1D4ED8",
        "danger": "#EF4444",
    },
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
    
    /* Remoção de bordas nas estruturas principais */
    QFrame#card, QGroupBox, QTabWidget::pane, QPlainTextEdit, QListWidget, QScrollArea {{
        background: {colors['card']};
        border: none;
        border-radius: 8px;
    }}
    
    QFrame#panel {{
        background: {colors['panel']};
        border: none;
        border-radius: 8px;
    }}
    
    /* Tipografia Limpa */
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
        background: {colors['card_alt']};
        color: {colors['accent']};
        font-size: 11px;
        font-weight: 700;
        border: 1px solid {colors['accent']};
        border-radius: 6px;
        padding: 2px 7px;
    }}
    
    QLabel#section {{
        color: {colors['text']};
        font-size: 13px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding-top: 8px;
        padding-bottom: 4px;
    }}
    
    QLabel#fieldLabel {{
        color: {colors['muted']};
        font-size: 12px;
        font-weight: 600;
        background: transparent;
        border: none;
        padding: 0;
    }}
    
    QLabel#muted {{
        color: {colors['muted']};
    }}
    
    /* Inputs minimalistas */
    QFrame#fieldCard {{
        background: {colors['card']};
        border: none;
        border-radius: 6px;
    }}
    
    QLineEdit, QPlainTextEdit, QListWidget, QComboBox {{
        background: {colors['card_alt']};
        border: 2px solid transparent; /* Reserva espaço para o outline de foco */
        border-radius: 6px;
        padding: 8px 12px;
        color: {colors['text']};
        selection-background-color: {colors['accent']};
    }}
    
    QLineEdit#fieldInput {{
        background: {colors['card_alt']};
        border-radius: 6px;
        min-height: 38px;
        padding: 8px 12px;
        color: {colors['text']};
        font-size: 14px;
        font-weight: 500;
    }}
    
    QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus, QComboBox:focus {{
        border: 2px solid {colors['accent']};
        background: {colors['card']};
    }}
    
    QLineEdit[invalid="true"] {{
        border: 2px solid {colors['danger']};
    }}
    
    QLineEdit::placeholder {{
        color: {colors['muted']};
    }}
    
    /* Botões Flat */
    QPushButton {{
        background: {colors['card_alt']};
        border: none;
        border-radius: 6px;
        padding: 12px 16px;
        color: {colors['text']};
        font-size: 13px;
        font-weight: 600;
    }}
    
    QPushButton:hover {{
        background: {colors['muted']};
        color: {colors['card']};
    }}
    
    QPushButton#accent {{
        background: {colors['accent']};
        color: #FFFFFF;
    }}
    
    QPushButton#accent:hover {{
        background: {colors['accent_hover']};
    }}
    
    QPushButton:disabled {{
        background: {colors['card']};
        color: {colors['muted']};
        opacity: 0.5;
    }}
    
    /* Checkboxes e Radios clean */
    QRadioButton, QCheckBox {{
        spacing: 10px;
        font-size: 13px;
        color: {colors['text']};
    }}
    
    QRadioButton::indicator, QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        background: {colors['card_alt']};
        border: none;
    }}
    
    QRadioButton::indicator {{
        border-radius: 9px;
    }}
    
    QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
        background: {colors['accent']};
    }}
    
    QCheckBox::indicator {{
        border-radius: 4px;
    }}
    
    /* Abas limpas */
    QTabBar::tab {{
        background: transparent;
        color: {colors['muted']};
        padding: 12px 20px;
        border: none;
        border-bottom: 2px solid transparent;
        font-size: 13px;
        font-weight: 600;
        margin-right: 4px;
    }}
    
    QTabBar::tab:selected {{
        color: {colors['accent']};
        border-bottom: 2px solid {colors['accent']};
    }}
    
    QTabBar::tab:hover:!selected {{
        color: {colors['text']};
        border-bottom: 2px solid {colors['card_alt']};
    }}
    
    /* Barra de progresso lisa */
    QProgressBar {{
        background: {colors['card_alt']};
        border: none;
        border-radius: 4px;
        min-height: 8px;
        max-height: 8px;
        text-align: center;
    }}
    
    QProgressBar::chunk {{
        background: {colors['accent']};
        border-radius: 4px;
    }}
    
    /* Scrollbars elegantes */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {colors['card_alt']};
        min-height: 20px;
        border-radius: 4px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """

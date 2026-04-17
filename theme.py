from __future__ import annotations

import customtkinter as ctk


ACCENT = "#00C2A8"
ACCENT2 = "#FF6B35"
ACCENT_HOVER = "#009E88"
ACCENT2_HOVER = "#D95A29"
PANEL_HOVER = ("#D9DEE8", "#1E2235")
BG_DARK = ("#F4F6FA", "#0F1117")
BG_CARD = ("#FFFFFF", "#1A1D27")
BG_INPUT = ("#E9EEF5", "#12151F")
TEXT = ("#111827", "#E8EAF0")
MUTED = ("#6B7280", "#5A5F72")
INFO_BAR = ("#3B82F6", "#1F538D")
ACTION_BAR = ("#F59E0B", "#D35400")
PROCESSING_BAR = ("#F97316", "#E67E22")
CANVAS_BG = {"Light": "#EEF2F7", "Dark": "#12151F"}
RULER_BG = {"Light": "#DCE3EE", "Dark": "#1A1D27"}
RULER_FG = {"Light": "#374151", "Dark": "#D8DDE8"}
CANVAS_TEXT = {"Light": "#111827", "Dark": "#FFFFFF"}


def setup_theme():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


def set_theme_mode(mode: str):
    ctk.set_appearance_mode(mode)


def current_mode() -> str:
    return ctk.get_appearance_mode()


def palette_color(palette: dict[str, str]) -> str:
    return palette.get(current_mode(), next(iter(palette.values())))

from __future__ import annotations

import customtkinter as ctk

from cut_panel import PainelCutFrame
from roler_packer import RoloPackerFrame
from theme import ACCENT, ACCENT_HOVER, BG_CARD, BG_DARK, BG_INPUT, PANEL_HOVER, TEXT, set_theme_mode, setup_theme


setup_theme()


class AjudanteImpressaoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Ajudante de Impressao")
        self.geometry("1380x860")
        self.minsize(1100, 720)
        self.configure(fg_color=BG_DARK)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_tools()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=72)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(
            header,
            text="AJUDANTE DE IMPRESSAO",
            font=ctk.CTkFont("Courier New", 22, "bold"),
            text_color=ACCENT,
        ).grid(row=0, column=0, padx=22, pady=(12, 0), sticky="w")

        ctk.CTkLabel(
            header,
            text="Ferramentas separadas para montagem de rolo e corte de painel",
            font=ctk.CTkFont("Courier New", 11),
            text_color=TEXT,
        ).grid(row=1, column=0, padx=22, pady=(2, 12), sticky="w")

        self.theme_selector = ctk.CTkOptionMenu(
            header,
            values=["Dark", "Light"],
            command=self._change_theme,
            fg_color=BG_INPUT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            text_color=TEXT,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=PANEL_HOVER,
        )
        self.theme_selector.set("Dark")
        self.theme_selector.grid(row=0, column=1, rowspan=2, padx=22, pady=16, sticky="e")

    def _build_tools(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        tabs = ctk.CTkTabview(
            container,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_INPUT,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=BG_INPUT,
            segmented_button_unselected_hover_color=PANEL_HOVER,
            text_color=TEXT,
            corner_radius=10,
        )
        tabs.grid(row=0, column=0, sticky="nsew")
        tabs.add("Rolo Packer")
        tabs.add("Cut Panel")

        rolo_tab = tabs.tab("Rolo Packer")
        rolo_tab.grid_rowconfigure(0, weight=1)
        rolo_tab.grid_columnconfigure(0, weight=1)
        self.rolo_packer = RoloPackerFrame(rolo_tab)
        self.rolo_packer.grid(row=0, column=0, sticky="nsew")

        cut_tab = tabs.tab("Cut Panel")
        cut_tab.grid_rowconfigure(0, weight=1)
        cut_tab.grid_columnconfigure(0, weight=1)
        self.cut_panel = PainelCutFrame(cut_tab)
        self.cut_panel.pack(fill="both", expand=True)

    def _change_theme(self, mode: str):
        set_theme_mode(mode)
        self.configure(fg_color=BG_DARK)
        if hasattr(self.cut_panel, "refresh_theme"):
            self.cut_panel.refresh_theme()


if __name__ == "__main__":
    app = AjudanteImpressaoApp()
    app.mainloop()

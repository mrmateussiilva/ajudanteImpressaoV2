from __future__ import annotations

import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from art_finishing_processing import process_finishing_folder
from theme import ACCENT, ACCENT2, ACCENT_HOVER, BG_CARD, BG_DARK, BG_INPUT, MUTED, PANEL_HOVER, TEXT


class ArtFinisherFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._folder = ""
        self._running = False
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=340)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, width=340)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(99, weight=1)

        header = ctk.CTkFrame(sidebar, fg_color=BG_DARK, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            header,
            text="ACABAMENTO",
            font=ctk.CTkFont("Courier New", 16, "bold"),
            text_color=ACCENT,
        ).grid(row=0, column=0, padx=20, pady=(18, 4))

        ctk.CTkLabel(
            header,
            text="Adiciona contorno, pad e nome do cliente em lote",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
            wraplength=285,
            justify="left",
        ).grid(row=1, column=0, padx=20, pady=(0, 14))

        self._section(sidebar, "PASTA DE IMAGENS", row=1)
        self._folder_label = ctk.CTkLabel(
            sidebar,
            text="Nenhuma pasta selecionada",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
            wraplength=275,
            justify="left",
        )
        self._folder_label.grid(row=2, column=0, padx=20, pady=(0, 6), sticky="w")

        ctk.CTkButton(
            sidebar,
            text="Selecionar Pasta",
            command=self._choose_folder,
            fg_color=BG_INPUT,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
            font=ctk.CTkFont("Courier New", 12, "bold"),
        ).grid(row=3, column=0, padx=20, pady=(0, 16), sticky="ew")

        self._section(sidebar, "CONFIGURACAO", row=4)
        params = ctk.CTkFrame(sidebar, fg_color="transparent")
        params.grid(row=5, column=0, padx=20, pady=(0, 16), sticky="ew")
        params.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            params,
            text="Lado do pad",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w", pady=(6, 0))
        self._side_var = ctk.StringVar(value="auto")
        self._side_menu = ctk.CTkOptionMenu(
            params,
            fg_color=BG_INPUT,
            text_color=TEXT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=PANEL_HOVER,
            values=["auto", "bottom", "right"],
            variable=self._side_var,
        )
        self._side_menu.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        ctk.CTkLabel(
            params,
            text="DPI manual (opcional)",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))
        self._dpi_entry = ctk.CTkEntry(
            params,
            fg_color=BG_INPUT,
            border_color=MUTED,
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 12),
            placeholder_text="Ex.: 100",
        )
        self._dpi_entry.grid(row=3, column=0, sticky="ew", pady=(2, 0))

        ctk.CTkLabel(
            params,
            text="Subpasta de saida",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
        ).grid(row=4, column=0, sticky="w", pady=(10, 0))
        self._output_entry = ctk.CTkEntry(
            params,
            fg_color=BG_INPUT,
            border_color=MUTED,
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 12),
        )
        self._output_entry.insert(0, "ACABAMENTO")
        self._output_entry.grid(row=5, column=0, sticky="ew", pady=(2, 0))

        self._help_label = ctk.CTkLabel(
            params,
            text="Regra atual: 155x155 usa pad 2 cm. Outras medidas usam pad 1 cm. O nome sai do prefixo antes do '-' ou do primeiro espaco.",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
            wraplength=275,
            justify="left",
        )
        self._help_label.grid(row=6, column=0, sticky="w", pady=(10, 0))

        self._run_btn = ctk.CTkButton(
            sidebar,
            text="PROCESSAR ACABAMENTO",
            command=self._run,
            fg_color=ACCENT2,
            hover_color=ACCENT_HOVER,
            text_color="#000000",
            font=ctk.CTkFont("Courier New", 14, "bold"),
            height=46,
            corner_radius=6,
        )
        self._run_btn.grid(row=99, column=0, padx=20, pady=20, sticky="sew")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        status_frame = ctk.CTkFrame(main, fg_color=BG_CARD, corner_radius=8, height=40)
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_propagate(False)
        status_frame.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            status_frame,
            text="Aguardando...",
            font=ctk.CTkFont("Courier New", 11),
            text_color=MUTED,
        )
        self._status_label.grid(row=0, column=0, padx=14, sticky="w")

        self._progress = ctk.CTkProgressBar(status_frame, mode="indeterminate", fg_color=BG_INPUT, progress_color=ACCENT)
        self._progress.grid(row=0, column=1, padx=14, pady=10, sticky="e")
        self._progress.set(0)

        self._log = ctk.CTkTextbox(
            main,
            fg_color=BG_INPUT,
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 11),
            corner_radius=8,
            wrap="word",
        )
        self._log.grid(row=1, column=0, sticky="nsew")
        self._log.configure(state="disabled")

    def _section(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("Courier New", 10, "bold"), text_color=MUTED).grid(
            row=row, column=0, padx=20, pady=(12, 4), sticky="w"
        )

    def _choose_folder(self):
        path = filedialog.askdirectory(title="Selecionar pasta de imagens")
        if path:
            self._folder = path
            self._folder_label.configure(text=path, text_color=TEXT)
            self._log_write(f"Pasta selecionada: {path}\n")

    def _run(self):
        if self._running:
            return
        if not self._folder:
            messagebox.showerror("Erro", "Selecione uma pasta primeiro.")
            return

        dpi_override = None
        raw_dpi = self._dpi_entry.get().strip()
        if raw_dpi:
            try:
                dpi_override = int(float(raw_dpi.replace(",", ".")))
            except ValueError:
                messagebox.showerror("Erro", "O DPI manual deve ser um numero valido.")
                return
            if dpi_override <= 0:
                messagebox.showerror("Erro", "O DPI manual deve ser maior que zero.")
                return

        output_name = self._output_entry.get().strip() or "ACABAMENTO"
        side_mode = self._side_var.get()

        self._set_running(True)
        self._clear_log()
        thread = threading.Thread(
            target=self._process,
            args=(Path(self._folder), output_name, dpi_override, side_mode),
            daemon=True,
        )
        thread.start()

    def _process(self, folder: Path, output_name: str, dpi_override: int | None, side_mode: str):
        try:
            self._status("Processando acabamento em lote...")
            results = process_finishing_folder(
                folder=folder,
                output_name=output_name,
                dpi_override=dpi_override,
                side_mode=side_mode,
            )
            for item in results:
                self._log_write(
                    f"OK {item['file']} -> cliente: {item['client_name']} | pad: {item['pad_cm']:.1f} cm | lado: {item['pad_side']}\n"
                )
            self._status(f"{len(results)} arquivo(s) processado(s).")
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("Erro", str(exc)))
            self._status("Erro no processamento.")
        finally:
            self._set_running(False)

    def _set_running(self, running: bool):
        def _apply():
            self._running = running
            state = "disabled" if running else "normal"
            self._run_btn.configure(state=state)
            if running:
                self._progress.start()
            else:
                self._progress.stop()
                self._progress.set(0)

        self.after(0, _apply)

    def _status(self, text: str):
        self.after(0, lambda: self._status_label.configure(text=text, text_color=TEXT if self._running else MUTED))

    def _clear_log(self):
        def _apply():
            self._log.configure(state="normal")
            self._log.delete("1.0", "end")
            self._log.configure(state="disabled")

        self.after(0, _apply)

    def _log_write(self, text: str):
        def _apply():
            self._log.configure(state="normal")
            self._log.insert("end", text)
            self._log.see("end")
            self._log.configure(state="disabled")

        self.after(0, _apply)

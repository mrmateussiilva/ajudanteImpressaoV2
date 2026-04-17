from __future__ import annotations

import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from image_resize_processing import process_resize_folder
from theme import ACCENT, ACCENT2, ACCENT_HOVER, BG_CARD, BG_DARK, BG_INPUT, MUTED, PANEL_HOVER, TEXT


class ImageResizerFrame(ctk.CTkFrame):
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
            text="REDIMENSIONAR IMAGENS",
            font=ctk.CTkFont("Courier New", 16, "bold"),
            text_color=ACCENT,
        ).grid(row=0, column=0, padx=20, pady=(18, 4))

        ctk.CTkLabel(
            header,
            text="Reduz ou amplia em lote mantendo a proporcao",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
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

        ctk.CTkLabel(params, text="Modo de redimensionamento", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(
            row=0, column=0, sticky="w", pady=(6, 0)
        )
        self._mode_var = ctk.StringVar(value="percent")
        self._mode_menu = ctk.CTkOptionMenu(
            params,
            fg_color=BG_INPUT,
            text_color=TEXT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=PANEL_HOVER,
            values=["percent", "width_cm", "width_px"],
            variable=self._mode_var,
            command=self._update_mode_ui,
        )
        self._mode_menu.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self._value_label = ctk.CTkLabel(params, text="Percentual final (%)", font=ctk.CTkFont("Courier New", 10), text_color=MUTED)
        self._value_label.grid(row=2, column=0, sticky="w", pady=(10, 0))
        self._value_entry = ctk.CTkEntry(
            params,
            fg_color=BG_INPUT,
            border_color=MUTED,
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 12),
        )
        self._value_entry.insert(0, "25")
        self._value_entry.grid(row=3, column=0, sticky="ew", pady=(2, 0))

        ctk.CTkLabel(params, text="Destino", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(
            row=4, column=0, sticky="w", pady=(10, 0)
        )
        self._destination_var = ctk.StringVar(value="subfolder")
        destination_frame = ctk.CTkFrame(params, fg_color="transparent")
        destination_frame.grid(row=5, column=0, sticky="ew", pady=(2, 0))
        destination_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkRadioButton(
            destination_frame,
            text="Salvar em subpasta",
            variable=self._destination_var,
            value="subfolder",
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 11),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            border_color=MUTED,
            command=self._update_destination_ui,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        ctk.CTkRadioButton(
            destination_frame,
            text="Sobrescrever originais",
            variable=self._destination_var,
            value="overwrite",
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 11),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            border_color=MUTED,
            command=self._update_destination_ui,
        ).grid(row=1, column=0, sticky="w")

        self._output_label = ctk.CTkLabel(params, text="Nome da subpasta", font=ctk.CTkFont("Courier New", 10), text_color=MUTED)
        self._output_label.grid(
            row=6, column=0, sticky="w", pady=(10, 0)
        )
        self._output_entry = ctk.CTkEntry(
            params,
            fg_color=BG_INPUT,
            border_color=MUTED,
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 12),
        )
        self._output_entry.insert(0, "REDIMENSIONADAS")
        self._output_entry.grid(row=7, column=0, sticky="ew", pady=(2, 0))

        self._help_label = ctk.CTkLabel(
            params,
            text="Exemplo: 25 reduz para 25% do tamanho atual.",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
            wraplength=275,
            justify="left",
        )
        self._help_label.grid(row=8, column=0, sticky="w", pady=(10, 0))
        self._update_mode_ui("percent")
        self._update_destination_ui()

        self._run_btn = ctk.CTkButton(
            sidebar,
            text="PROCESSAR LOTE",
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

        try:
            target_value = float(self._value_entry.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Erro", "Informe um valor valido.")
            return

        if target_value <= 0:
            messagebox.showerror("Erro", "O valor deve ser maior que zero.")
            return

        mode = self._mode_var.get()
        destination_mode = self._destination_var.get()
        output_name = self._output_entry.get().strip() or "REDIMENSIONADAS"
        if destination_mode == "overwrite":
            confirmed = messagebox.askyesno(
                "Confirmar sobrescrita",
                "Isso vai sobrescrever as imagens originais da pasta selecionada. Deseja continuar?",
            )
            if not confirmed:
                return
        self._set_running(True)
        self._clear_log()
        thread = threading.Thread(
            target=self._process,
            args=(Path(self._folder), mode, target_value, output_name, destination_mode),
            daemon=True,
        )
        thread.start()

    def _process(self, folder: Path, mode: str, target_value: float, output_name: str, destination_mode: str):
        try:
            self._set_status("Processando imagens...")
            self._log_write(f"Modo: {mode}\n")
            self._log_write(f"Valor alvo: {target_value}\n")
            self._log_write(f"Destino: {'sobrescrever originais' if destination_mode == 'overwrite' else folder / output_name}\n\n")

            try:
                results = process_resize_folder(folder, mode, target_value, output_name, destination_mode)
            except ValueError:
                self._set_status("Nenhuma imagem encontrada.")
                self._log_write("Nenhuma imagem compativel encontrada na pasta.\n")
                return

            for result in results:
                self._log_write(
                    f"OK {result['file']} -> {result['width']}x{result['height']}px (escala {result['scale']:.3f})\n"
                )

            self._set_status("Concluido.")
            self._log_write("\nLote finalizado.\n")
        finally:
            self._set_running(False)

    def _log_write(self, text: str):
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", text)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        def _do():
            self._log.configure(state="normal")
            self._log.delete("1.0", "end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _update_mode_ui(self, mode: str):
        labels = {
            "percent": ("Percentual final (%)", "Exemplo: 25 reduz para 25% do tamanho atual."),
            "width_cm": ("Largura final (cm)", "Usa o DPI da imagem para converter a largura alvo em cm."),
            "width_px": ("Largura final (px)", "Define uma largura final em pixels e mantem a proporcao."),
        }
        label, help_text = labels.get(mode, labels["percent"])
        self._value_label.configure(text=label)
        self._help_label.configure(text=help_text)
        defaults = {"percent": "25", "width_cm": "50", "width_px": "1000"}
        self._value_entry.delete(0, "end")
        self._value_entry.insert(0, defaults.get(mode, "25"))

    def _update_destination_ui(self):
        is_subfolder = self._destination_var.get() == "subfolder"
        if is_subfolder:
            self._output_label.grid()
            self._output_entry.grid()
        else:
            self._output_label.grid_remove()
            self._output_entry.grid_remove()

    def _set_status(self, text: str):
        self.after(0, lambda: self._status_label.configure(text=text))

    def _set_running(self, running: bool):
        self._running = running

        def _do():
            if running:
                self._run_btn.configure(state="disabled", text="PROCESSANDO...", fg_color=MUTED)
                self._progress.start()
            else:
                self._run_btn.configure(state="normal", text="PROCESSAR LOTE", fg_color=ACCENT2)
                self._progress.stop()
                self._progress.set(0)
        self.after(0, _do)

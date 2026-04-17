from __future__ import annotations

import threading
import time
from pathlib import Path

import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, messagebox

from cut_processing import build_cut_points_from_plate_width, process_cut_images
from image_resize_processing import resize_image_file
from image_utils import VALID_EXT
from theme import ACCENT, ACCENT2, ACCENT_HOVER, BG_CARD, BG_DARK, BG_INPUT, MUTED, PANEL_HOVER, TEXT


class AutomationFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._source_folder = ""
        self._template_path = ""
        self._running = False
        self._watcher_thread = None
        self._known_files: dict[str, tuple[int, int]] = {}
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=360)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, width=360)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(99, weight=1)

        header = ctk.CTkFrame(sidebar, fg_color=BG_DARK, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(header, text="AUTOMACAO", font=ctk.CTkFont("Courier New", 16, "bold"), text_color=ACCENT).grid(
            row=0, column=0, padx=20, pady=(18, 4)
        )
        ctk.CTkLabel(
            header,
            text="Monitora uma pasta e executa a acao configurada em novos arquivos",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
            wraplength=300,
            justify="left",
        ).grid(row=1, column=0, padx=20, pady=(0, 14))

        self._section(sidebar, "ORIGEM", 1)
        self._source_label = ctk.CTkLabel(
            sidebar,
            text="Nenhuma pasta monitorada",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
            wraplength=300,
            justify="left",
        )
        self._source_label.grid(row=2, column=0, padx=20, pady=(0, 6), sticky="w")

        ctk.CTkButton(
            sidebar,
            text="Selecionar Pasta",
            command=self._choose_source_folder,
            fg_color=BG_INPUT,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
            font=ctk.CTkFont("Courier New", 12, "bold"),
        ).grid(row=3, column=0, padx=20, pady=(0, 16), sticky="ew")

        self._section(sidebar, "ACAO", 4)
        params = ctk.CTkFrame(sidebar, fg_color="transparent")
        params.grid(row=5, column=0, padx=20, pady=(0, 16), sticky="ew")
        params.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(params, text="Tipo de acao", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=0, column=0, sticky="w")
        self._action_var = ctk.StringVar(value="resize")
        self._action_menu = ctk.CTkOptionMenu(
            params,
            values=["resize", "cut_batch"],
            variable=self._action_var,
            command=self._update_action_ui,
            fg_color=BG_INPUT,
            text_color=TEXT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=PANEL_HOVER,
        )
        self._action_menu.grid(row=1, column=0, sticky="ew", pady=(2, 10))

        ctk.CTkLabel(params, text="Intervalo de leitura (s)", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=2, column=0, sticky="w")
        self._poll_entry = ctk.CTkEntry(params, fg_color=BG_INPUT, border_color=MUTED, text_color=TEXT, font=ctk.CTkFont("Courier New", 12))
        self._poll_entry.insert(0, "2")
        self._poll_entry.grid(row=3, column=0, sticky="ew", pady=(2, 10))

        self._resize_group = ctk.CTkFrame(params, fg_color="transparent")
        self._resize_group.grid(row=4, column=0, sticky="ew")
        self._resize_group.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._resize_group, text="Modo resize", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=0, column=0, sticky="w")
        self._resize_mode = ctk.StringVar(value="percent")
        self._resize_mode_menu = ctk.CTkOptionMenu(
            self._resize_group,
            values=["percent", "width_cm", "width_px"],
            variable=self._resize_mode,
            fg_color=BG_INPUT,
            text_color=TEXT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=PANEL_HOVER,
        )
        self._resize_mode_menu.grid(row=1, column=0, sticky="ew", pady=(2, 6))

        ctk.CTkLabel(self._resize_group, text="Valor", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=2, column=0, sticky="w")
        self._resize_value = ctk.CTkEntry(self._resize_group, fg_color=BG_INPUT, border_color=MUTED, text_color=TEXT, font=ctk.CTkFont("Courier New", 12))
        self._resize_value.insert(0, "25")
        self._resize_value.grid(row=3, column=0, sticky="ew", pady=(2, 6))

        ctk.CTkLabel(self._resize_group, text="Destino resize", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=4, column=0, sticky="w")
        self._resize_destination = ctk.StringVar(value="subfolder")
        ctk.CTkRadioButton(self._resize_group, text="Subpasta", variable=self._resize_destination, value="subfolder", text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=MUTED, command=self._update_resize_destination_ui).grid(row=5, column=0, sticky="w")
        ctk.CTkRadioButton(self._resize_group, text="Sobrescrever", variable=self._resize_destination, value="overwrite", text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=MUTED, command=self._update_resize_destination_ui).grid(row=6, column=0, sticky="w")

        self._resize_output_label = ctk.CTkLabel(self._resize_group, text="Nome da subpasta", font=ctk.CTkFont("Courier New", 10), text_color=MUTED)
        self._resize_output_label.grid(row=7, column=0, sticky="w", pady=(6, 0))
        self._resize_output = ctk.CTkEntry(self._resize_group, fg_color=BG_INPUT, border_color=MUTED, text_color=TEXT, font=ctk.CTkFont("Courier New", 12))
        self._resize_output.insert(0, "AUTO_REDIMENSIONADAS")
        self._resize_output.grid(row=8, column=0, sticky="ew", pady=(2, 0))

        self._cut_group = ctk.CTkFrame(params, fg_color="transparent")
        self._cut_group.grid(row=5, column=0, sticky="ew")
        self._cut_group.grid_columnconfigure(0, weight=1)

        self._template_label = ctk.CTkLabel(self._cut_group, text="Nenhum gabarito", font=ctk.CTkFont("Courier New", 10), text_color=MUTED, wraplength=300, justify="left")
        self._template_label.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            self._cut_group,
            text="Carregar Gabarito",
            command=self._choose_template,
            fg_color=BG_INPUT,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
            font=ctk.CTkFont("Courier New", 12, "bold"),
        ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

        ctk.CTkLabel(self._cut_group, text="Largura da placa (cm)", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=2, column=0, sticky="w")
        self._cut_measures = ctk.CTkTextbox(self._cut_group, height=80, fg_color=BG_INPUT, text_color=TEXT, font=ctk.CTkFont("Courier New", 11), corner_radius=6)
        self._cut_measures.insert("1.0", "150")
        self._cut_measures.grid(row=3, column=0, sticky="ew", pady=(2, 6))

        ctk.CTkLabel(self._cut_group, text="DPI manual (opcional)", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=4, column=0, sticky="w")
        self._cut_dpi = ctk.CTkEntry(self._cut_group, fg_color=BG_INPUT, border_color=MUTED, text_color=TEXT, font=ctk.CTkFont("Courier New", 12))
        self._cut_dpi.grid(row=5, column=0, sticky="ew", pady=(2, 6))

        ctk.CTkLabel(self._cut_group, text="Margem branca (cm)", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=6, column=0, sticky="w")
        self._cut_pad = ctk.CTkEntry(self._cut_group, fg_color=BG_INPUT, border_color=MUTED, text_color=TEXT, font=ctk.CTkFont("Courier New", 12))
        self._cut_pad.insert(0, "1.0")
        self._cut_pad.grid(row=7, column=0, sticky="ew", pady=(2, 0))

        self._update_action_ui("resize")
        self._update_resize_destination_ui()

        action_buttons = ctk.CTkFrame(sidebar, fg_color="transparent")
        action_buttons.grid(row=99, column=0, padx=20, pady=20, sticky="sew")
        action_buttons.grid_columnconfigure((0, 1), weight=1)

        self._start_btn = ctk.CTkButton(action_buttons, text="INICIAR", command=self._start_watching, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#000000", font=ctk.CTkFont("Courier New", 14, "bold"), height=46)
        self._start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._stop_btn = ctk.CTkButton(action_buttons, text="PARAR", command=self._stop_watching, fg_color=ACCENT2, hover_color=ACCENT_HOVER, text_color="#000000", font=ctk.CTkFont("Courier New", 14, "bold"), height=46, state="disabled")
        self._stop_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        status = ctk.CTkFrame(main, fg_color=BG_CARD, corner_radius=8, height=40)
        status.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status.grid_propagate(False)
        status.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(status, text="Parado.", font=ctk.CTkFont("Courier New", 11), text_color=MUTED)
        self._status_label.grid(row=0, column=0, padx=14, sticky="w")

        self._progress = ctk.CTkProgressBar(status, mode="indeterminate", fg_color=BG_INPUT, progress_color=ACCENT)
        self._progress.grid(row=0, column=1, padx=14, pady=10, sticky="e")
        self._progress.set(0)

        self._log = ctk.CTkTextbox(main, fg_color=BG_INPUT, text_color=TEXT, font=ctk.CTkFont("Courier New", 11), corner_radius=8, wrap="word")
        self._log.grid(row=1, column=0, sticky="nsew")
        self._log.configure(state="disabled")

    def _section(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("Courier New", 10, "bold"), text_color=MUTED).grid(row=row, column=0, padx=20, pady=(12, 4), sticky="w")

    def _choose_source_folder(self):
        path = filedialog.askdirectory(title="Selecionar pasta para monitorar")
        if path:
            self._source_folder = path
            self._source_label.configure(text=path, text_color=TEXT)
            self._log_write(f"Pasta monitorada: {path}\n")

    def _choose_template(self):
        path = filedialog.askopenfilename(filetypes=[("Imagens", "*.png *.jpg *.jpeg *.tif *.tiff")])
        if path:
            self._template_path = path
            self._template_label.configure(text=path, text_color=TEXT)

    def _update_action_ui(self, action: str):
        if action == "resize":
            self._resize_group.grid()
            self._cut_group.grid_remove()
        else:
            self._resize_group.grid_remove()
            self._cut_group.grid()

    def _update_resize_destination_ui(self):
        if self._resize_destination.get() == "subfolder":
            self._resize_output_label.grid()
            self._resize_output.grid()
        else:
            self._resize_output_label.grid_remove()
            self._resize_output.grid_remove()

    def _parse_plate_width(self) -> float:
        raw = self._cut_measures.get("1.0", "end").strip()
        if not raw:
            raise ValueError("Digite a largura da placa para o corte.")
        plate_width = float(raw.replace(",", "."))
        if plate_width <= 0:
            raise ValueError("A largura da placa deve ser maior que zero.")
        return plate_width

    def _manual_dpi(self) -> int | None:
        raw = self._cut_dpi.get().strip()
        if not raw:
            return None
        value = int(float(raw.replace(",", ".")))
        return value if value > 0 else None

    def _start_watching(self):
        if self._running:
            return
        if not self._source_folder:
            messagebox.showerror("Erro", "Selecione a pasta para monitorar.")
            return

        try:
            self._build_config()
        except Exception as e:
            messagebox.showerror("Erro", str(e))
            return

        self._running = True
        self._known_files = self._snapshot_files()
        self._watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher_thread.start()
        self._set_status("Monitorando pasta...")
        self._progress.start()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._log_write("Monitor iniciado. Arquivos atuais foram ignorados; so novos/alterados serao processados.\n")

    def _stop_watching(self):
        self._running = False
        self._set_status("Parado.")
        self._progress.stop()
        self._progress.set(0)
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._log_write("Monitor parado.\n")

    def _build_config(self):
        poll_interval = float(self._poll_entry.get().replace(",", "."))
        if poll_interval <= 0:
            raise ValueError("O intervalo deve ser maior que zero.")

        action = self._action_var.get()
        config = {"poll_interval": poll_interval, "action": action}

        if action == "resize":
            target_value = float(self._resize_value.get().replace(",", "."))
            if target_value <= 0:
                raise ValueError("O valor de resize deve ser maior que zero.")
            config.update(
                {
                    "mode": self._resize_mode.get(),
                    "target_value": target_value,
                    "destination_mode": self._resize_destination.get(),
                    "output_name": self._resize_output.get().strip() or "AUTO_REDIMENSIONADAS",
                }
            )
        else:
            if not self._template_path:
                raise ValueError("Carregue um gabarito para o corte automatico.")
            plate_width = self._parse_plate_width()
            pad_cm = float(self._cut_pad.get().replace(",", "."))
            if pad_cm <= 0:
                raise ValueError("A margem branca deve ser maior que zero.")
            config.update(
                {
                    "template_path": self._template_path,
                    "plate_width_cm": plate_width,
                    "pad_cm": pad_cm,
                    "dpi_override": self._manual_dpi(),
                }
            )

        self._config = config
        return config

    def _snapshot_files(self):
        folder = Path(self._source_folder)
        snapshot = {}
        for file in folder.iterdir():
            if file.is_file() and file.suffix.lower() in VALID_EXT:
                stat = file.stat()
                snapshot[str(file)] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    def _watch_loop(self):
        while self._running:
            try:
                current = self._snapshot_files()
                for file_path, signature in current.items():
                    if self._known_files.get(file_path) == signature:
                        continue
                    self._known_files[file_path] = signature
                    self._process_file(Path(file_path))
                time.sleep(self._config["poll_interval"])
            except Exception as e:
                self._log_write(f"ERRO no monitor: {e}\n")
                time.sleep(2)

    def _process_file(self, file: Path):
        self._log_write(f"Detectado: {file.name}\n")
        action = self._config["action"]
        try:
            if action == "resize":
                result = resize_image_file(
                    file=file,
                    mode=self._config["mode"],
                    target_value=self._config["target_value"],
                    output_name=self._config["output_name"],
                    destination_mode=self._config["destination_mode"],
                )
                self._log_write(
                    f"Resize OK {result['file']} -> {result['width']}x{result['height']}px em {result['save_path']}\n"
                )
            else:
                with Image.open(self._config["template_path"]) as template, Image.open(file) as image:
                    cut_points = build_cut_points_from_plate_width(
                        image,
                        self._config["plate_width_cm"],
                        dpi_override=self._config["dpi_override"],
                    )
                    output_dir, total_parts = process_cut_images(
                        original_image=image.copy(),
                        template_image=template.copy(),
                        image_path=str(file),
                        real_cut_points=cut_points,
                        pad_cm=self._config["pad_cm"],
                        dpi_override=self._config["dpi_override"],
                    )
                self._log_write(f"Corte OK {file.name} -> {total_parts} partes em {output_dir}\n")
        except Exception as e:
            self._log_write(f"ERRO {file.name}: {e}\n")

    def _log_write(self, text: str):
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", text)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _set_status(self, text: str):
        self.after(0, lambda: self._status_label.configure(text=text))

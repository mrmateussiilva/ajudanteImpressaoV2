from __future__ import annotations

import threading
from pathlib import Path
from typing import List

import customtkinter as ctk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox

from image_utils import cm_to_px, process_images, rgba_to_white_background
from packing_algorithms import build_canvas, pack_images_fast, pack_images_gallery, pack_images_tight
from theme import ACCENT, ACCENT_HOVER, BG_CARD, BG_DARK, BG_INPUT, MUTED, PANEL_HOVER, TEXT


PERFORMANCE_PROFILES = {
    "quality": {"label": "Qualidade", "step_multiplier": 0.75, "max_workers": 4, "debug_limit": 0, "jpeg_quality": 95},
    "balanced": {"label": "Balanceado", "step_multiplier": 1.0, "max_workers": 6, "debug_limit": 24, "jpeg_quality": 92},
    "fast": {"label": "Rapido", "step_multiplier": 2.0, "max_workers": 8, "debug_limit": 12, "jpeg_quality": 88},
}


class RoloPackerFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._pasta: str = ""
        self._preview_img = None
        self._debug_thumbs = []
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

        header = ctk.CTkFrame(sidebar, fg_color="#0D1520", corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="ROLO PACKER", font=ctk.CTkFont("Courier New", 16, "bold"), text_color=ACCENT).grid(
            row=0, column=0, padx=20, pady=(18, 4)
        )
        ctk.CTkLabel(
            header,
            text="Layout horizontal para impressao em rolo",
            font=ctk.CTkFont("Courier New", 10),
            text_color=MUTED,
        ).grid(row=1, column=0, padx=20, pady=(0, 14))

        self._section(sidebar, "PASTA DE IMAGENS", row=1)
        self._pasta_label = ctk.CTkLabel(sidebar, text="Nenhuma pasta selecionada", font=ctk.CTkFont("Courier New", 10), text_color=MUTED, wraplength=275, justify="left")
        self._pasta_label.grid(row=2, column=0, padx=20, pady=(0, 6), sticky="w")

        ctk.CTkButton(
            sidebar,
            text="Selecionar Pasta",
            fg_color=BG_INPUT,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
            font=ctk.CTkFont("Courier New", 12, "bold"),
            command=self._choose_folder,
        ).grid(row=3, column=0, padx=20, pady=(0, 16), sticky="ew")

        self._section(sidebar, "CONFIGURACOES", row=4)
        params_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        params_frame.grid(row=5, column=0, padx=20, pady=(0, 16), sticky="ew")
        params_frame.grid_columnconfigure(0, weight=1)

        self._largura = self._param(params_frame, "Largura do rolo (cm)", "125", row=0)
        self._margem = self._param(params_frame, "Margem nas bordas (cm)", "0.5", row=1)
        self._espaco = self._param(params_frame, "Espacamento entre imagens (cm)", "0.3", row=2)
        self._threshold = self._param(params_frame, "Threshold fundo branco", "245", row=3)
        self._step = self._param(params_frame, "Precisao do encaixe (px)", "8", row=4)
        self._row_height = self._param(params_frame, "Altura base do mosaico (cm)", "18", row=5)

        ctk.CTkLabel(params_frame, text="Perfil de performance", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=12, column=0, sticky="w", pady=(10, 0))
        self._performance_mode = ctk.StringVar(value="balanced")
        performance_frame = ctk.CTkFrame(params_frame, fg_color="transparent")
        performance_frame.grid(row=13, column=0, sticky="ew", pady=(4, 0))
        performance_frame.grid_columnconfigure(0, weight=1)

        for idx, (text, value) in enumerate((("Qualidade", "quality"), ("Balanceado", "balanced"), ("Rapido", "fast"))):
            ctk.CTkRadioButton(
                performance_frame,
                text=text,
                variable=self._performance_mode,
                value=value,
                text_color=TEXT,
                font=ctk.CTkFont("Courier New", 11),
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                border_color=MUTED,
            ).grid(row=idx, column=0, sticky="w", pady=(0, 4 if idx < 2 else 0))

        ctk.CTkLabel(params_frame, text="Modo de encaixe", font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(row=14, column=0, sticky="w", pady=(12, 0))
        self._packing_mode = ctk.StringVar(value="gallery")
        mode_frame = ctk.CTkFrame(params_frame, fg_color="transparent")
        mode_frame.grid(row=15, column=0, sticky="ew", pady=(4, 0))
        mode_frame.grid_columnconfigure(0, weight=1)

        modes = (
            ("Mosaico por linhas (recomendado)", "gallery"),
            ("Rapido - Linhas inteligentes", "fast"),
            ("Compacto - Skyline", "tight"),
        )
        for idx, (text, value) in enumerate(modes):
            ctk.CTkRadioButton(
                mode_frame,
                text=text,
                variable=self._packing_mode,
                value=value,
                text_color=TEXT,
                font=ctk.CTkFont("Courier New", 11),
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                border_color=MUTED,
            ).grid(row=idx, column=0, sticky="w", pady=(0, 6 if idx < 2 else 0))

        self._rotate_var = ctk.BooleanVar(value=False)
        self._rotate_chk = ctk.CTkCheckBox(
            params_frame,
            text="Permitir rotacao automatica",
            variable=self._rotate_var,
            onvalue=True,
            offvalue=False,
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 11),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        )
        self._rotate_chk.grid(row=16, column=0, sticky="w", pady=(12, 0))

        self._section(sidebar, "ARQUIVO DE SAIDA", row=6)
        self._output_entry = ctk.CTkEntry(
            sidebar,
            placeholder_text="rolo_125cm.jpg",
            fg_color=BG_INPUT,
            border_color=MUTED,
            text_color=TEXT,
            font=ctk.CTkFont("Courier New", 12),
        )
        self._output_entry.grid(row=7, column=0, padx=20, pady=(0, 16), sticky="ew")

        self._run_btn = ctk.CTkButton(
            sidebar,
            text="GERAR ROLO",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#000000",
            font=ctk.CTkFont("Courier New", 14, "bold"),
            height=46,
            corner_radius=6,
            command=self._run,
        )
        self._run_btn.grid(row=99, column=0, padx=20, pady=20, sticky="sew")

    def _section(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("Courier New", 10, "bold"), text_color=MUTED).grid(
            row=row, column=0, padx=20, pady=(12, 4), sticky="w"
        )

    def _param(self, parent, label, default, row):
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont("Courier New", 10), text_color=MUTED).grid(
            row=row * 2, column=0, sticky="w", pady=(6, 0)
        )
        entry = ctk.CTkEntry(parent, fg_color=BG_INPUT, border_color=MUTED, text_color=TEXT, font=ctk.CTkFont("Courier New", 12))
        entry.insert(0, default)
        entry.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(2, 0))
        return entry

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        status_frame = ctk.CTkFrame(main, fg_color=BG_CARD, corner_radius=8, height=40)
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_propagate(False)
        status_frame.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(status_frame, text="Aguardando...", font=ctk.CTkFont("Courier New", 11), text_color=MUTED)
        self._status_label.grid(row=0, column=0, padx=14, sticky="w")

        self._progress = ctk.CTkProgressBar(status_frame, mode="indeterminate", fg_color=BG_INPUT, progress_color=ACCENT)
        self._progress.grid(row=0, column=1, padx=14, pady=10, sticky="e")
        self._progress.set(0)

        self._tabs = ctk.CTkTabview(
            main,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_INPUT,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=BG_INPUT,
            segmented_button_unselected_hover_color=PANEL_HOVER,
            text_color=TEXT,
            corner_radius=8,
        )
        self._tabs.grid(row=1, column=0, sticky="nsew")
        self._tabs.add("Log")
        self._tabs.add("Preview")
        self._tabs.add("Debug")

        log_tab = self._tabs.tab("Log")
        log_tab.grid_rowconfigure(0, weight=1)
        log_tab.grid_columnconfigure(0, weight=1)
        self._log = ctk.CTkTextbox(log_tab, fg_color=BG_INPUT, text_color=TEXT, font=ctk.CTkFont("Courier New", 11), corner_radius=6, wrap="word")
        self._log.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._log.configure(state="disabled")

        preview_tab = self._tabs.tab("Preview")
        preview_tab.grid_rowconfigure(0, weight=1)
        preview_tab.grid_columnconfigure(0, weight=1)
        self._preview_frame = ctk.CTkScrollableFrame(preview_tab, fg_color=BG_INPUT, corner_radius=6)
        self._preview_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._preview_label = ctk.CTkLabel(self._preview_frame, text="A previa aparecera aqui apos gerar o rolo.", text_color=MUTED, font=ctk.CTkFont("Courier New", 11))
        self._preview_label.pack(expand=True, pady=40)

        debug_tab = self._tabs.tab("Debug")
        debug_tab.grid_rowconfigure(0, weight=1)
        debug_tab.grid_columnconfigure(0, weight=1)
        self._debug_frame = ctk.CTkScrollableFrame(debug_tab, fg_color=BG_INPUT, corner_radius=6)
        self._debug_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._debug_label = ctk.CTkLabel(self._debug_frame, text="O debug das imagens aparecera aqui apos o processamento.", text_color=MUTED, font=ctk.CTkFont("Courier New", 11))
        self._debug_label.pack(expand=True, pady=40)

    def _choose_folder(self):
        path = filedialog.askdirectory(title="Selecionar pasta de imagens")
        if path:
            self._pasta = path
            self._pasta_label.configure(text=f".../{Path(path).name}", text_color=TEXT)
            self._log_write(f"📂  Pasta selecionada:\n    {path}\n", "info")

    def _run(self):
        if self._running:
            return
        if not self._pasta:
            messagebox.showerror("Erro", "Selecione uma pasta de imagens primeiro.")
            return

        try:
            largura = float(self._largura.get())
            margem = float(self._margem.get())
            espaco = float(self._espaco.get())
            threshold = int(self._threshold.get())
            step = int(self._step.get())
            row_height_cm = float(self._row_height.get())
        except ValueError:
            messagebox.showerror("Erro", "Verifique os valores dos parametros.")
            return

        output_name = self._output_entry.get().strip() or f"rolo_{int(largura)}cm.jpg"
        if not Path(output_name).suffix:
            output_name = f"{output_name}.jpg"
        elif Path(output_name).suffix.lower() not in {".jpg", ".jpeg"}:
            output_name = f"{Path(output_name).stem}.jpg"

        self._log_clear()
        self._set_running(True)

        thread = threading.Thread(
            target=self._process_thread,
            args=(
                Path(self._pasta),
                largura,
                margem,
                espaco,
                threshold,
                step,
                self._rotate_var.get(),
                self._packing_mode.get(),
                row_height_cm,
                output_name,
                self._performance_mode.get(),
            ),
            daemon=True,
        )
        thread.start()

    def _process_thread(self, folder: Path, largura: float, margem: float, espaco: float, threshold: int, step: int, allow_rotate: bool, packing_mode: str, row_height_cm: float, output_name: str, performance_mode: str):
        try:
            profile = PERFORMANCE_PROFILES.get(performance_mode, PERFORMANCE_PROFILES["balanced"])
            roll_px = cm_to_px(largura)
            spacing_px = cm_to_px(espaco)
            margin_px = cm_to_px(margem)
            row_height_px = cm_to_px(row_height_cm)
            usable_width = max(1, roll_px - 2 * margin_px)
            effective_step = max(1, int(round(max(1, step) * profile["step_multiplier"])))

            self._log_write(f"{'─' * 58}\n", "muted")
            self._log_write(f"  Rolo: {largura}cm = {roll_px}px\n", "info")
            self._log_write(f"  Margem: {margem}cm = {margin_px}px\n", "info")
            self._log_write(f"  Espacamento: {espaco}cm = {spacing_px}px\n", "info")
            self._log_write(f"  Altura base do mosaico: {row_height_cm}cm = {row_height_px}px\n", "info")
            self._log_write(f"  Area util: {usable_width}px\n", "info")
            self._log_write(f"  Threshold: {threshold}\n", "info")
            self._log_write(f"  Perfil: {profile['label']}\n", "info")
            self._log_write(f"  Step encaixe: {effective_step}px\n", "info")
            self._log_write(f"  Rotacao automatica: {'SIM' if allow_rotate else 'NAO'}\n", "info")
            self._log_write(f"  Modo: {packing_mode}\n", "info")
            self._log_write(f"{'─' * 58}\n\n", "muted")

            self._set_status("Processando imagens...")
            image_items = process_images(folder, usable_width, threshold, self._log_write, max_workers=profile["max_workers"])
            if not image_items:
                self._set_running(False)
                return

            images = [item["image"] for item in image_items]
            self._show_debug_images(image_items, debug_limit=profile["debug_limit"])
            self._set_status("Calculando layout...")

            if packing_mode == "gallery":
                self._log_write("\nGerando mosaico horizontal por linhas...\n", "info")
                packed, final_w, final_h = pack_images_gallery(images=images, max_width=roll_px, spacing=spacing_px, margin=margin_px, row_height=max(30, row_height_px), allow_rotate=allow_rotate)
            elif packing_mode == "fast":
                self._log_write("\nCalculando layout rapido...\n", "info")
                packed, final_w, final_h = pack_images_fast(images=images, max_width=roll_px, spacing=spacing_px, margin=margin_px, allow_rotate=allow_rotate)
            else:
                self._log_write("\nCalculando layout compacto...\n", "info")
                packed, final_w, final_h = pack_images_tight(images=images, max_width=roll_px, spacing=spacing_px, margin=margin_px, step=effective_step, allow_rotate=allow_rotate)

            self._log_write(
                f"  Canvas final: {final_w}×{final_h}px  ({final_w / 100 * 2.54:.1f}cm × {final_h / 100 * 2.54:.1f}cm)\n",
                "info",
            )

            self._set_status("Gerando imagem final...")
            self._log_write("\nGerando imagem final...\n", "info")
            final = build_canvas(packed, final_w, final_h)
            final_jpeg = rgba_to_white_background(final)

            output_path = folder / output_name
            final_jpeg.save(str(output_path), format="JPEG", dpi=(100, 100), quality=profile["jpeg_quality"])

            self._log_write(f"\nSalvo em:\n    {output_path}\n", "ok")
            self._log_write(f"    {len(packed)} imagens posicionadas.\n", "ok")
            self._log_write(f"\n{'─' * 58}\n", "muted")

            self._set_status(f"Concluido - {output_name}")
            self._show_preview(final)
        except Exception as e:
            self._log_write(f"\nErro inesperado: {e}\n", "err")
            self._set_status("Erro durante o processamento.")
        finally:
            self._set_running(False)

    def _log_write(self, text: str, level: str = "info"):
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", text)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _set_status(self, text: str):
        self.after(0, lambda: self._status_label.configure(text=text))

    def _set_running(self, running: bool):
        self._running = running

        def _do():
            if running:
                self._run_btn.configure(state="disabled", text="Processando...", fg_color=MUTED)
                self._progress.start()
            else:
                self._run_btn.configure(state="normal", text="GERAR ROLO", fg_color=ACCENT)
                self._progress.stop()
                self._progress.set(0)
        self.after(0, _do)

    def _log_clear(self):
        def _do():
            self._log.configure(state="normal")
            self._log.delete("1.0", "end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _show_preview(self, img: Image.Image):
        def _do():
            for w in self._preview_frame.winfo_children():
                w.destroy()

            max_w = 520
            ratio = max_w / img.width if img.width > max_w else 1.0
            thumb = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)

            checker = Image.new("RGBA", thumb.size, (30, 30, 30, 255))
            block = 16
            for cy in range(0, thumb.height, block):
                for cx in range(0, thumb.width, block):
                    if (cx // block + cy // block) % 2 == 0:
                        x1 = min(cx + block, thumb.width)
                        y1 = min(cy + block, thumb.height)
                        tile = Image.new("RGBA", (x1 - cx, y1 - cy), (50, 50, 50, 255))
                        checker.alpha_composite(tile, (cx, cy))

            combined = Image.alpha_composite(checker, thumb)
            self._preview_img = ImageTk.PhotoImage(combined)
            ctk.CTkLabel(self._preview_frame, image=self._preview_img, text="").pack(padx=8, pady=8)
            ctk.CTkLabel(
                self._preview_frame,
                text=f"{img.width}×{img.height}px  ·  {img.width / 100 * 2.54:.1f}×{img.height / 100 * 2.54:.1f}cm",
                font=ctk.CTkFont("Courier New", 10),
                text_color=MUTED,
            ).pack(pady=(0, 8))
            self._tabs.set("Preview")
        self.after(0, _do)

    def _show_debug_images(self, image_items: List[dict], debug_limit: int = 0):
        def _do():
            for widget in self._debug_frame.winfo_children():
                widget.destroy()

            self._debug_thumbs = []
            avg_width_cm = sum(item["width_cm"] for item in image_items) / len(image_items)
            avg_height_cm = sum(item["height_cm"] for item in image_items) / len(image_items)

            summary = ctk.CTkFrame(self._debug_frame, fg_color=BG_CARD, corner_radius=8)
            summary.pack(fill="x", padx=8, pady=(8, 10))
            ctk.CTkLabel(
                summary,
                text=f"{len(image_items)} imagens processadas  ·  media: {avg_width_cm:.1f} × {avg_height_cm:.1f} cm",
                text_color=TEXT,
                font=ctk.CTkFont("Courier New", 11, "bold"),
            ).pack(anchor="w", padx=12, pady=12)

            visible_items = image_items if debug_limit <= 0 else image_items[:debug_limit]
            if debug_limit > 0 and len(image_items) > debug_limit:
                ctk.CTkLabel(
                    summary,
                    text=f"Mostrando {debug_limit} previews para manter a interface responsiva.",
                    text_color=MUTED,
                    font=ctk.CTkFont("Courier New", 10),
                ).pack(anchor="w", padx=12, pady=(0, 12))

            for item in visible_items:
                card = ctk.CTkFrame(self._debug_frame, fg_color=BG_CARD, corner_radius=8)
                card.pack(fill="x", padx=8, pady=(0, 8))

                inner = ctk.CTkFrame(card, fg_color="transparent")
                inner.pack(fill="x", padx=10, pady=10)
                inner.grid_columnconfigure(0, weight=0)
                inner.grid_columnconfigure(1, weight=1)

                preview = item["image"].copy()
                preview.thumbnail((120, 120), Image.Resampling.LANCZOS)
                checker = Image.new("RGBA", preview.size, (30, 30, 30, 255))
                block = 12

                for cy in range(0, preview.height, block):
                    for cx in range(0, preview.width, block):
                        if (cx // block + cy // block) % 2 == 0:
                            x1 = min(cx + block, preview.width)
                            y1 = min(cy + block, preview.height)
                            tile = Image.new("RGBA", (x1 - cx, y1 - cy), (50, 50, 50, 255))
                            checker.alpha_composite(tile, (cx, cy))

                combined = Image.alpha_composite(checker, preview)
                tk_img = ImageTk.PhotoImage(combined)
                self._debug_thumbs.append(tk_img)

                ctk.CTkLabel(inner, image=tk_img, text="").grid(row=0, column=0, sticky="nw")
                info = ctk.CTkFrame(inner, fg_color="transparent")
                info.grid(row=0, column=1, sticky="ew", padx=(12, 0))

                ctk.CTkLabel(info, text=item["name"], text_color=TEXT, font=ctk.CTkFont("Courier New", 11, "bold"), anchor="w").pack(anchor="w")
                ctk.CTkLabel(info, text=f"{item['width_px']}×{item['height_px']} px", text_color=MUTED, font=ctk.CTkFont("Courier New", 10), anchor="w").pack(anchor="w", pady=(4, 0))
                ctk.CTkLabel(info, text=f"{item['width_cm']:.1f} × {item['height_cm']:.1f} cm", text_color=ACCENT, font=ctk.CTkFont("Courier New", 11, "bold"), anchor="w").pack(anchor="w", pady=(4, 0))
        self.after(0, _do)

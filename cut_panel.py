from __future__ import annotations

import os
import re

import customtkinter as ctk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox

from cut_processing import build_cut_points_from_measures, process_cut_folder, process_cut_images
from image_utils import cm_to_px, px_to_cm
from theme import (
    ACCENT,
    ACCENT2,
    ACCENT2_HOVER,
    ACCENT_HOVER,
    ACTION_BAR,
    BG_CARD,
    BG_DARK,
    BG_INPUT,
    CANVAS_BG,
    CANVAS_TEXT,
    INFO_BAR,
    MUTED,
    PANEL_HOVER,
    PROCESSING_BAR,
    RULER_BG,
    RULER_FG,
    current_mode,
    palette_color,
)


class PainelCutFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.original_image = None
        self.display_image = None
        self.template_image = None
        self.image_path = ""
        self.scale_factor = 1.0
        self.selected_guide = None
        self.guide_positions: list[int] = []
        self.pad_cm = 1.0
        self.x_offset = 0
        self.y_offset = 0
        self.batch_folder = ""
        self.setup_ui()
        self.after(50, self.update_canvas_image)

    def setup_ui(self):
        self.pack_propagate(False)

        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=BG_CARD)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="PainelCut PRO", font=ctk.CTkFont("Courier New", 24, "bold"), text_color=ACCENT)
        self.logo_label.pack(padx=20, pady=(30, 20))

        self.files_group = ctk.CTkFrame(self.sidebar_frame, fg_color=BG_INPUT, corner_radius=10)
        self.files_group.pack(padx=15, pady=10, fill="x")

        ctk.CTkLabel(self.files_group, text="1. Importacao", font=ctk.CTkFont("Courier New", 14, "bold"), text_color=MUTED).pack(anchor="w", padx=15, pady=(10, 5))

        self.btn_load_template = ctk.CTkButton(
            self.files_group,
            text="Carregar Gabarito",
            command=self.load_template,
            height=35,
            fg_color=BG_DARK,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
        )
        self.btn_load_template.pack(padx=15, pady=(5, 0), fill="x")

        self.lbl_status_template = ctk.CTkLabel(self.files_group, text="Nenhum gabarito", text_color=ACCENT2, font=ctk.CTkFont("Courier New", 11))
        self.lbl_status_template.pack(anchor="w", padx=15, pady=(0, 10))

        self.btn_load = ctk.CTkButton(
            self.files_group,
            text="Carregar Imagem Principal",
            command=self.load_image,
            height=35,
            fg_color=BG_DARK,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
        )
        self.btn_load.pack(padx=15, pady=(5, 0), fill="x")

        self.lbl_status_img = ctk.CTkLabel(self.files_group, text="Nenhuma imagem", text_color=ACCENT2, font=ctk.CTkFont("Courier New", 11))
        self.lbl_status_img.pack(anchor="w", padx=15, pady=(0, 15))

        rotate_frame = ctk.CTkFrame(self.files_group, fg_color="transparent")
        rotate_frame.pack(padx=15, pady=(0, 15), fill="x")
        rotate_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_rotate_left = ctk.CTkButton(
            rotate_frame,
            text="Rotacionar -90",
            command=lambda: self.rotate_image(-90),
            height=32,
            fg_color=BG_DARK,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
        )
        self.btn_rotate_left.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_rotate_right = ctk.CTkButton(
            rotate_frame,
            text="Rotacionar +90",
            command=lambda: self.rotate_image(90),
            height=32,
            fg_color=BG_DARK,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
        )
        self.btn_rotate_right.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.tools_group = ctk.CTkFrame(self.sidebar_frame, fg_color=BG_INPUT, corner_radius=10)
        self.tools_group.pack(padx=15, pady=10, fill="x")

        ctk.CTkLabel(self.tools_group, text="2. Guias de Corte", font=ctk.CTkFont("Courier New", 14, "bold"), text_color=MUTED).pack(anchor="w", padx=15, pady=(10, 10))

        self.btn_add_guide = ctk.CTkButton(self.tools_group, text="+ Adicionar Regua", command=self.add_guide, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#000000", height=35)
        self.btn_add_guide.pack(padx=15, pady=5, fill="x")

        ctk.CTkLabel(
            self.tools_group,
            text="Medidas das placas (cm)",
            font=ctk.CTkFont("Courier New", 11, "bold"),
            text_color=MUTED,
        ).pack(anchor="w", padx=15, pady=(10, 4))

        self.measure_entry = ctk.CTkTextbox(
            self.tools_group,
            height=84,
            fg_color=BG_DARK,
            text_color=CANVAS_TEXT[current_mode()],
            font=ctk.CTkFont("Courier New", 11),
            corner_radius=6,
        )
        self.measure_entry.pack(padx=15, pady=(0, 8), fill="x")
        self.measure_entry.insert("1.0", "50, 50, 50")

        ctk.CTkLabel(
            self.tools_group,
            text="DPI manual (opcional)",
            font=ctk.CTkFont("Courier New", 11, "bold"),
            text_color=MUTED,
        ).pack(anchor="w", padx=15, pady=(4, 4))

        self.dpi_entry = ctk.CTkEntry(
            self.tools_group,
            placeholder_text="Ex.: 100",
            fg_color=BG_DARK,
            border_color=MUTED,
            text_color=CANVAS_TEXT[current_mode()],
            font=ctk.CTkFont("Courier New", 11),
        )
        self.dpi_entry.pack(padx=15, pady=(0, 8), fill="x")
        self.dpi_entry.bind("<KeyRelease>", self._on_dpi_change)

        self.lbl_dpi_info = ctk.CTkLabel(
            self.tools_group,
            text="DPI em uso: automatico",
            text_color=MUTED,
            font=ctk.CTkFont("Courier New", 10),
            wraplength=250,
            justify="left",
        )
        self.lbl_dpi_info.pack(anchor="w", padx=15, pady=(0, 8))

        self.btn_apply_measures = ctk.CTkButton(
            self.tools_group,
            text="Aplicar Medidas",
            command=self.apply_measurements,
            fg_color=BG_DARK,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
            height=35,
        )
        self.btn_apply_measures.pack(padx=15, pady=(0, 8), fill="x")

        self.lbl_measure_info = ctk.CTkLabel(
            self.tools_group,
            text="Digite medidas separadas por virgula, espaco ou linha.",
            text_color=MUTED,
            font=ctk.CTkFont("Courier New", 10),
            wraplength=250,
            justify="left",
        )
        self.lbl_measure_info.pack(anchor="w", padx=15, pady=(0, 10))

        self.btn_clear_guides = ctk.CTkButton(self.tools_group, text="Limpar Todas", command=self.clear_guides, fg_color=ACCENT2, hover_color=ACCENT2_HOVER, text_color="#000000", height=35)
        self.btn_clear_guides.pack(padx=15, pady=(5, 15), fill="x")

        self.action_group = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.action_group.pack(padx=15, pady=10, fill="x", side="bottom")

        self.btn_cut = ctk.CTkButton(self.action_group, text="PROCESSAR CORTES", command=self.process_cuts, font=ctk.CTkFont("Courier New", 16, "bold"), height=50, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#000000")
        self.btn_cut.pack(padx=0, pady=20, fill="x")

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.mode_tabs = ctk.CTkTabview(
            self.main_frame,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_INPUT,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=BG_INPUT,
            segmented_button_unselected_hover_color=PANEL_HOVER,
            text_color=CANVAS_TEXT[current_mode()],
            corner_radius=10,
        )
        self.mode_tabs.grid(row=0, column=0, sticky="nsew")
        self.mode_tabs.add("Manual")
        self.mode_tabs.add("Lote")

        manual_tab = self.mode_tabs.tab("Manual")
        manual_tab.grid_rowconfigure(1, weight=1)
        manual_tab.grid_columnconfigure(0, weight=1)

        self.info_panel = ctk.CTkFrame(manual_tab, height=40, corner_radius=8, fg_color=INFO_BAR)
        self.info_panel.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.info_panel.pack_propagate(False)

        self.lbl_instruction = ctk.CTkLabel(self.info_panel, text="Carregue um gabarito e uma imagem para comecar.", font=ctk.CTkFont("Courier New", 13, "bold"), text_color="#ffffff")
        self.lbl_instruction.pack(pady=8)

        self.canvas_container = ctk.CTkFrame(manual_tab, corner_radius=10, fg_color=BG_INPUT)
        self.canvas_container.grid(row=1, column=0, sticky="nsew")
        self.canvas_container.grid_rowconfigure(1, weight=1)
        self.canvas_container.grid_columnconfigure(1, weight=1)

        self.corner_block = ctk.CTkFrame(self.canvas_container, fg_color=BG_CARD, corner_radius=0, width=36, height=28)
        self.corner_block.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=(2, 0))

        self.top_ruler = ctk.CTkCanvas(self.canvas_container, bg=palette_color(RULER_BG), highlightthickness=0, height=28)
        self.top_ruler.grid(row=0, column=1, sticky="ew", padx=(0, 2), pady=(2, 0))

        self.left_ruler = ctk.CTkCanvas(self.canvas_container, bg=palette_color(RULER_BG), highlightthickness=0, width=36)
        self.left_ruler.grid(row=1, column=0, sticky="ns", padx=(2, 0), pady=(0, 2))

        self.canvas = ctk.CTkCanvas(self.canvas_container, bg=palette_color(CANVAS_BG), highlightthickness=0)
        self.canvas.grid(row=1, column=1, sticky="nsew", padx=(0, 2), pady=(0, 2))

        self.canvas.bind("<ButtonPress-1>", self.on_guide_press)
        self.canvas.bind("<B1-Motion>", self.on_guide_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_guide_release)
        self.bind("<Configure>", self.on_resize)

        batch_tab = self.mode_tabs.tab("Lote")
        batch_tab.grid_rowconfigure(1, weight=1)
        batch_tab.grid_columnconfigure(0, weight=1)

        self.batch_info = ctk.CTkFrame(batch_tab, height=48, corner_radius=8, fg_color=INFO_BAR)
        self.batch_info.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.batch_info.pack_propagate(False)
        self.batch_info_label = ctk.CTkLabel(
            self.batch_info,
            text="Selecione uma pasta. O lote usa o mesmo gabarito, medidas e DPI configurados na lateral.",
            font=ctk.CTkFont("Courier New", 12, "bold"),
            text_color="#ffffff",
        )
        self.batch_info_label.pack(padx=12, pady=12, anchor="w")

        self.batch_panel = ctk.CTkFrame(batch_tab, fg_color=BG_INPUT, corner_radius=10)
        self.batch_panel.grid(row=1, column=0, sticky="nsew")
        self.batch_panel.grid_rowconfigure(2, weight=1)
        self.batch_panel.grid_columnconfigure(0, weight=1)

        self.batch_folder_label = ctk.CTkLabel(
            self.batch_panel,
            text="Nenhuma pasta selecionada",
            text_color=MUTED,
            font=ctk.CTkFont("Courier New", 11),
            wraplength=720,
            justify="left",
        )
        self.batch_folder_label.grid(row=0, column=0, sticky="w", padx=14, pady=(14, 8))

        batch_actions = ctk.CTkFrame(self.batch_panel, fg_color="transparent")
        batch_actions.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        batch_actions.grid_columnconfigure((0, 1), weight=1)

        self.btn_select_batch_folder = ctk.CTkButton(
            batch_actions,
            text="Selecionar Pasta do Lote",
            command=self.select_batch_folder,
            fg_color=BG_DARK,
            hover_color=PANEL_HOVER,
            border_color=ACCENT,
            border_width=1,
            text_color=ACCENT,
            height=35,
        )
        self.btn_select_batch_folder.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_run_batch = ctk.CTkButton(
            batch_actions,
            text="Processar Lote",
            command=self.process_batch_cuts,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#000000",
            height=35,
        )
        self.btn_run_batch.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.batch_log = ctk.CTkTextbox(
            self.batch_panel,
            fg_color=BG_DARK,
            text_color=CANVAS_TEXT[current_mode()],
            font=ctk.CTkFont("Courier New", 11),
            corner_radius=8,
            wrap="word",
        )
        self.batch_log.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.batch_log.insert("1.0", "O lote vai listar aqui cada arquivo processado.\n")
        self.batch_log.configure(state="disabled")

    def load_template(self):
        file_path = filedialog.askopenfilename(filetypes=[("Imagens", "*.png *.jpg *.jpeg *.tif *.tiff")])
        if file_path:
            self.template_image = Image.open(file_path)
            self.lbl_status_template.configure(text=f"OK {os.path.basename(file_path)[:24]}", text_color=ACCENT)
            self.update_instruction_bar()

    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Imagens", "*.png *.jpg *.jpeg *.tif *.tiff")])
        if not file_path:
            return
        self.image_path = file_path
        self.original_image = Image.open(file_path)
        self.guide_positions = []
        self.lbl_status_img.configure(text=f"OK {os.path.basename(file_path)[:24]}", text_color=ACCENT)
        self.clear_guides()
        self.update_canvas_image()
        self.update_instruction_bar()
        self._update_dpi_info()

    def update_instruction_bar(self):
        if self.original_image and self.template_image:
            self.lbl_instruction.configure(text="Arraste as reguas azuis para definir os limites de corte.")
            self.info_panel.configure(fg_color=ACTION_BAR)
        elif self.original_image:
            width_cm = self._image_width_cm()
            self.lbl_instruction.configure(text=f"Imagem carregada. Largura util: {width_cm:.1f} cm")
            self.info_panel.configure(fg_color=INFO_BAR)

    def update_canvas_image(self):
        if not self.original_image:
            return
        self.canvas.update_idletasks()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            return

        img_width, img_height = self.original_image.size
        self.scale_factor = min(canvas_width / img_width, canvas_height / img_height)
        new_width = int(img_width * self.scale_factor)
        new_height = int(img_height * self.scale_factor)

        resized_img = self.original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        self.display_image = ImageTk.PhotoImage(resized_img)

        self.canvas.delete("image")
        self.x_offset = (canvas_width - new_width) // 2
        self.y_offset = (canvas_height - new_height) // 2
        self.canvas.create_image(self.x_offset, self.y_offset, anchor="nw", image=self.display_image, tags="image")
        self.canvas.tag_lower("image")
        self._redraw_guides()
        self._draw_rulers()

    def on_resize(self, event):
        if event.widget == self:
            self.update_canvas_image()

    def add_guide(self):
        if not self.original_image:
            messagebox.showwarning("Aviso", "Carregue a imagem principal primeiro.")
            return
        start_x = self.original_image.width // 2
        self.guide_positions.append(start_x)
        self.guide_positions = sorted(set(self.guide_positions))
        self._redraw_guides()

    def clear_guides(self):
        self.guide_positions = []
        self.selected_guide = None
        self.canvas.delete("guide")
        self.canvas.delete("guide_label")
        self._update_measure_info()

    def on_guide_press(self, event):
        items = self.canvas.find_closest(event.x, event.y)
        if items:
            item = items[0]
            tags = self.canvas.gettags(item)
            if "guide" in tags:
                for tag in tags:
                    if tag.startswith("guide_"):
                        self.selected_guide = int(tag.split("_", 1)[1])
                        break

    def on_guide_drag(self, event):
        if self.selected_guide is not None and self.display_image:
            max_real = max(1, self.original_image.width - 1)
            new_x_canvas = max(self.x_offset, min(event.x, self.x_offset + self.display_image.width()))
            real_x = int(round((new_x_canvas - self.x_offset) / self.scale_factor))
            real_x = max(1, min(real_x, max_real))
            self.guide_positions[self.selected_guide] = real_x
            self.guide_positions = sorted(self.guide_positions)
            self.selected_guide = min(range(len(self.guide_positions)), key=lambda idx: abs(self.guide_positions[idx] - real_x))
            self._redraw_guides()

    def on_guide_release(self, _event):
        self.selected_guide = None

    def rotate_image(self, angle: int):
        if not self.original_image:
            messagebox.showwarning("Aviso", "Carregue a imagem principal primeiro.")
            return
        self.original_image = self.original_image.rotate(angle, expand=True)
        self.guide_positions = []
        self.selected_guide = None
        self.update_canvas_image()
        self.update_instruction_bar()
        self._update_measure_info()
        self._update_dpi_info()

    def apply_measurements(self):
        if not self.original_image:
            messagebox.showwarning("Aviso", "Carregue a imagem principal primeiro.")
            return

        measures_cm = self._parse_measurements()
        if measures_cm is None:
            return

        image_width_cm = self._image_width_cm()
        total_cm = sum(measures_cm)
        tolerance_cm = 0.2

        if total_cm > image_width_cm + tolerance_cm:
            messagebox.showerror(
                "Erro",
                f"As medidas somam {total_cm:.1f} cm, mas a imagem tem {image_width_cm:.1f} cm de largura.",
            )
            return

        cumulative = 0.0
        positions = []
        for value in measures_cm[:-1]:
            cumulative += value
            positions.append(cm_to_px(cumulative, dpi=self._image_dpi_x()))

        if total_cm < image_width_cm - tolerance_cm:
            remaining_cm = image_width_cm - total_cm
            self.lbl_measure_info.configure(
                text=f"Medidas aplicadas. Sobra final automatica: {remaining_cm:.1f} cm.",
                text_color=ACCENT,
            )
        else:
            self.lbl_measure_info.configure(
                text=f"Medidas aplicadas. Total: {total_cm:.1f} cm.",
                text_color=ACCENT,
            )

        self.guide_positions = sorted({max(1, min(pos, self.original_image.width - 1)) for pos in positions})
        self._redraw_guides()
        self._draw_rulers()

    def _parse_measurements(self) -> list[float] | None:
        raw_text = self.measure_entry.get("1.0", "end").strip()
        values = [chunk for chunk in re.split(r"[\s,;]+", raw_text) if chunk]
        if not values:
            messagebox.showwarning("Aviso", "Digite pelo menos uma medida em cm.")
            return None

        try:
            measures_cm = [float(value.replace(",", ".")) for value in values]
        except ValueError:
            messagebox.showerror("Erro", "As medidas devem ser numeros em cm.")
            return None

        if any(value <= 0 for value in measures_cm):
            messagebox.showerror("Erro", "Todas as medidas devem ser maiores que zero.")
            return None
        return measures_cm

    def _image_dpi_x(self) -> int:
        manual_dpi = self._manual_dpi()
        if manual_dpi is not None:
            return manual_dpi
        if not self.original_image:
            return 72
        dpi = self.original_image.info.get("dpi", (72, 72))[0]
        if not dpi or dpi <= 0:
            return 72
        return int(round(dpi))

    def _manual_dpi(self) -> int | None:
        raw_value = self.dpi_entry.get().strip()
        if not raw_value:
            return None
        try:
            dpi_value = int(float(raw_value.replace(",", ".")))
        except ValueError:
            return None
        return dpi_value if dpi_value > 0 else None

    def _image_width_cm(self) -> float:
        if not self.original_image:
            return 0.0
        return px_to_cm(self.original_image.width, dpi=self._image_dpi_x())

    def _image_height_cm(self) -> float:
        if not self.original_image:
            return 0.0
        return px_to_cm(self.original_image.height, dpi=self._image_dpi_x())

    def _redraw_guides(self):
        self.canvas.delete("guide")
        self.canvas.delete("guide_label")
        if not self.original_image or not self.display_image:
            return

        canvas_height = self.canvas.winfo_height()
        sorted_positions = sorted(pos for pos in self.guide_positions if 0 < pos < self.original_image.width)
        self.guide_positions = sorted_positions

        for idx, real_x in enumerate(sorted_positions):
            canvas_x = self.x_offset + int(round(real_x * self.scale_factor))
            self.canvas.create_line(
                canvas_x,
                self.y_offset,
                canvas_x,
                self.y_offset + self.display_image.height(),
                fill="#00e5ff",
                width=3,
                dash=(8, 4),
                tags=("guide", f"guide_{idx}"),
            )

        boundaries = [0, *sorted_positions, self.original_image.width]
        for idx in range(len(boundaries) - 1):
            start_px = boundaries[idx]
            end_px = boundaries[idx + 1]
            if end_px <= start_px:
                continue
            segment_cm = px_to_cm(end_px - start_px, dpi=self._image_dpi_x())
            middle_px = start_px + ((end_px - start_px) / 2)
            middle_x = self.x_offset + int(round(middle_px * self.scale_factor))
            text_y = max(18, self.y_offset + 18)
            self.canvas.create_text(
                middle_x,
                text_y,
                text=f"{segment_cm:.1f} cm",
                fill=palette_color(CANVAS_TEXT),
                font=("Courier New", 11, "bold"),
                tags=("guide_label",),
            )

        self._update_measure_info()
        self._draw_rulers()

    def _update_measure_info(self):
        if not self.original_image:
            self.lbl_measure_info.configure(
                text="Digite medidas separadas por virgula, espaco ou linha.",
                text_color=MUTED,
            )
            return

        boundaries = [0, *sorted(self.guide_positions), self.original_image.width]
        measures = []
        for idx in range(len(boundaries) - 1):
            width_px = boundaries[idx + 1] - boundaries[idx]
            if width_px > 0:
                measures.append(f"{px_to_cm(width_px, dpi=self._image_dpi_x()):.1f}")

        if measures:
            self.lbl_measure_info.configure(
                text=f"Placas na tela: {' | '.join(measures)} cm",
                text_color=ACCENT,
            )
        else:
            self.lbl_measure_info.configure(
                text=f"Largura total da imagem: {self._image_width_cm():.1f} cm",
                text_color=MUTED,
            )

    def _update_dpi_info(self):
        manual_dpi = self._manual_dpi()
        if manual_dpi is not None:
            self.lbl_dpi_info.configure(text=f"DPI em uso: {manual_dpi} (manual)", text_color=ACCENT)
        elif self.original_image:
            self.lbl_dpi_info.configure(text=f"DPI em uso: {self._image_dpi_x()} (imagem)", text_color=MUTED)
        else:
            self.lbl_dpi_info.configure(text="DPI em uso: automatico", text_color=MUTED)

    def _on_dpi_change(self, _event=None):
        self._update_dpi_info()
        if self.original_image:
            self.update_instruction_bar()
            self._update_measure_info()
            self._draw_rulers()
            if self.guide_positions:
                self._redraw_guides()

    def select_batch_folder(self):
        path = filedialog.askdirectory(title="Selecionar pasta para corte em lote")
        if path:
            self.batch_folder = path
            self.batch_folder_label.configure(text=path, text_color=palette_color(CANVAS_TEXT))
            self._append_batch_log(f"Pasta selecionada: {path}")

    def _append_batch_log(self, text: str):
        self.batch_log.configure(state="normal")
        self.batch_log.insert("end", f"{text}\n")
        self.batch_log.see("end")
        self.batch_log.configure(state="disabled")

    def process_batch_cuts(self):
        if not self.template_image:
            messagebox.showwarning("Aviso", "Carregue o gabarito primeiro.")
            return
        if not self.batch_folder:
            messagebox.showwarning("Aviso", "Selecione uma pasta para o lote.")
            return

        measures_cm = self._parse_measurements()
        if measures_cm is None:
            return

        manual_dpi = self._manual_dpi()
        if self.dpi_entry.get().strip() and manual_dpi is None:
            messagebox.showerror("Erro", "O DPI manual deve ser um numero maior que zero.")
            return

        self._append_batch_log("Iniciando processamento em lote...")
        try:
            results = process_cut_folder(
                folder_path=self.batch_folder,
                template_image=self.template_image,
                measures_cm=measures_cm,
                pad_cm=self.pad_cm,
                dpi_override=manual_dpi,
            )
            self._append_batch_log(f"{len(results)} arquivo(s) processado(s).")
            for result in results:
                self._append_batch_log(f"OK {result['file']} -> {result['parts']} partes")
            messagebox.showinfo("Sucesso", f"Lote concluido com {len(results)} arquivo(s).")
        except Exception as e:
            self._append_batch_log(f"Erro no lote: {e}")
            messagebox.showerror("Erro de Lote", str(e))

    def _draw_rulers(self):
        self.top_ruler.delete("all")
        self.left_ruler.delete("all")
        if not self.original_image or not self.display_image:
            return

        dpi = self._image_dpi_x()
        px_per_cm = dpi / 2.54
        if px_per_cm <= 0:
            return

        major_step_cm = 5
        minor_step_cm = 1

        img_left = self.x_offset
        img_top = self.y_offset
        img_right = self.x_offset + self.display_image.width()
        img_bottom = self.y_offset + self.display_image.height()

        ruler_bg = palette_color(RULER_BG)
        ruler_fg = palette_color(RULER_FG)
        self.top_ruler.create_rectangle(0, 0, self.top_ruler.winfo_width(), 28, fill=ruler_bg, outline="")
        self.left_ruler.create_rectangle(0, 0, 36, self.left_ruler.winfo_height(), fill=ruler_bg, outline="")

        width_cm = self._image_width_cm()
        height_cm = self._image_height_cm()

        cm = 0
        while cm <= width_cm + 0.01:
            real_px = cm_to_px(cm, dpi=dpi)
            canvas_x = img_left + int(round(real_px * self.scale_factor))
            if img_left <= canvas_x <= img_right:
                tick = 18 if cm % major_step_cm == 0 else 10
                self.top_ruler.create_line(canvas_x, 28, canvas_x, 28 - tick, fill=ruler_fg, width=1)
                if cm % major_step_cm == 0:
                    self.top_ruler.create_text(canvas_x + 2, 8, text=str(int(cm)), fill=ruler_fg, anchor="nw", font=("Courier New", 9))
            cm += minor_step_cm

        cm = 0
        while cm <= height_cm + 0.01:
            real_px = cm_to_px(cm, dpi=dpi)
            canvas_y = img_top + int(round(real_px * self.scale_factor))
            if img_top <= canvas_y <= img_bottom:
                tick = 18 if cm % major_step_cm == 0 else 10
                self.left_ruler.create_line(36, canvas_y, 36 - tick, canvas_y, fill=ruler_fg, width=1)
                if cm % major_step_cm == 0:
                    self.left_ruler.create_text(4, canvas_y + 1, text=str(int(cm)), fill=ruler_fg, anchor="nw", font=("Courier New", 9))
            cm += minor_step_cm

    def refresh_theme(self):
        canvas_bg = palette_color(CANVAS_BG)
        ruler_bg = palette_color(RULER_BG)
        self.canvas.configure(bg=canvas_bg)
        self.top_ruler.configure(bg=ruler_bg)
        self.left_ruler.configure(bg=ruler_bg)
        self.batch_folder_label.configure(text_color=palette_color(CANVAS_TEXT) if self.batch_folder else MUTED)
        self.batch_log.configure(text_color=palette_color(CANVAS_TEXT))
        self.measure_entry.configure(text_color=palette_color(CANVAS_TEXT))
        self.dpi_entry.configure(text_color=palette_color(CANVAS_TEXT))
        self._update_dpi_info()
        self.update_instruction_bar()
        self._draw_rulers()
        self._redraw_guides()

    def process_cuts(self):
        if not self.original_image:
            messagebox.showwarning("Aviso", "Carregue a imagem principal primeiro.")
            return
        if not self.template_image:
            messagebox.showwarning("Aviso", "Carregue o gabarito primeiro.")
            return

        self.lbl_instruction.configure(text="Processando cortes, aguarde...", text_color="#ffffff")
        self.info_panel.configure(fg_color=PROCESSING_BAR)
        self.update()

        try:
            manual_dpi = self._manual_dpi()
            if self.dpi_entry.get().strip() and manual_dpi is None:
                messagebox.showerror("Erro", "O DPI manual deve ser um numero maior que zero.")
                return

            if self.guide_positions:
                real_cut_points = [0, *sorted(self.guide_positions), self.original_image.width]
            else:
                measures_cm = self._parse_measurements()
                if measures_cm is None:
                    return
                real_cut_points = build_cut_points_from_measures(
                    self.original_image,
                    measures_cm,
                    dpi_override=manual_dpi,
                )

            output_dir, total_parts = process_cut_images(
                original_image=self.original_image,
                template_image=self.template_image,
                image_path=self.image_path,
                real_cut_points=real_cut_points,
                pad_cm=self.pad_cm,
                dpi_override=manual_dpi,
            )
            self.update_instruction_bar()
            messagebox.showinfo("Sucesso", f"Processo concluido.\n\nAs {total_parts} partes foram salvas em:\n{output_dir}")
        except Exception as e:
            messagebox.showerror("Erro de Processamento", f"Ocorreu um erro durante o corte:\n{e}")

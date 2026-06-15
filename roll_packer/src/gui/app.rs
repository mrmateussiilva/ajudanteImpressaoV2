use eframe::egui;
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use rfd::FileDialog;

use crate::engine::packing::{pack_images_gallery, pack_images_fast, pack_images_tight};
use crate::engine::packing_masked::pack_images_masked;
use crate::engine::canvas::build_canvas;
use crate::engine::output::split_and_save;
use crate::engine::loader::{process_images, ImageItem};
use crate::engine::classifier::Classifier;
use crate::engine::image_ops::add_label_to_image;
use image::{DynamicImage, GenericImageView};

fn cm_to_px(cm: f32, dpi: f32) -> u32 {
    ((cm * dpi) / 2.54).round() as u32
}

fn px_to_cm(px: u32, dpi: f32) -> f32 {
    (px as f32 * 2.54) / dpi
}

#[derive(PartialEq, Clone, Copy)]
pub enum Algorithm {
    Gallery,
    Fast,
    Tight,
    Masked,
}

enum LogLevel {
    Info,
    Warn,
    Error,
    Ok,
    Muted,
}

enum LoadMsg {
    Log(String, LogLevel),
    Progress(usize, usize),
    Done(Vec<ImageItem>),
    Error(String),
}

pub struct PackResult {
    pub paths: Vec<PathBuf>,
    pub canvas_w: u32,
    pub canvas_h: u32,
    pub preview_w: u32,
    pub preview_h: u32,
    pub preview_rgba: Vec<u8>,
}

enum PackMsg {
    Log(String, LogLevel),
    Status(String),
    Done(PackResult),
    Error(String),
}

pub struct RollPackerApp {
    folder: Option<PathBuf>,
    max_width_cm: f32,
    spacing_cm: f32,
    margin_cm: f32,
    step_mm: f32,
    dpi: f32,
    allow_rotate: bool,
    algorithm: Algorithm,
    performance_mode: String,
    label_position: String,
    label_date_enabled: bool,
    label_date: String,
    label_color: [f32; 4],
    output_name: String,
    threshold: u8,

    is_loading: bool,
    is_packing: bool,
    loaded_items: Vec<ImageItem>,
    log_lines: Vec<(String, LogLevel)>,
    
    preview_texture: Option<egui::TextureHandle>,
    preview_dims: (u32, u32),

    load_tx: mpsc::Sender<LoadMsg>,
    load_rx: mpsc::Receiver<LoadMsg>,
    pack_tx: mpsc::Sender<PackMsg>,
    pack_rx: mpsc::Receiver<PackMsg>,

    prod_classifier: Arc<Mutex<Classifier>>,
    quality_classifier: Arc<Mutex<Classifier>>,
    status_text: String,
    progress: f32,
}

impl Default for RollPackerApp {
    fn default() -> Self {
        let (load_tx, load_rx) = mpsc::channel();
        let (pack_tx, pack_rx) = mpsc::channel();
        
        Self {
            folder: None,
            max_width_cm: 60.0,
            spacing_cm: 0.3,
            margin_cm: 0.5,
            step_mm: 2.0,
            dpi: 100.0,
            allow_rotate: false,
            algorithm: Algorithm::Fast,
            performance_mode: "balanced".to_string(),
            label_position: "external_bottom_right".to_string(),
            label_date_enabled: false,
            label_date: "".to_string(),
            label_color: [0.0, 0.0, 0.0, 1.0],
            output_name: "rolo.jpg".to_string(),
            threshold: 245,

            is_loading: false,
            is_packing: false,
            loaded_items: Vec::new(),
            log_lines: Vec::new(),
            preview_texture: None,
            preview_dims: (0, 0),

            load_tx,
            load_rx,
            pack_tx,
            pack_rx,

            prod_classifier: Arc::new(Mutex::new(Classifier::new(r"Z:\IMPRESSÃO DE TOTENS\treinamentos", "Producao"))),
            quality_classifier: Arc::new(Mutex::new(Classifier::new(r"Z:\IMPRESSÃO DE TOTENS\qualidade", "Qualidade"))),
            status_text: "Aguardando...".to_string(),
            progress: 0.0,
        }
    }
}

impl eframe::App for RollPackerApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        if let Ok(msg) = self.load_rx.try_recv() {
            match msg {
                LoadMsg::Log(s, l) => self.log_lines.push((s, l)),
                LoadMsg::Progress(c, t) => {
                    self.progress = c as f32 / t as f32;
                    self.status_text = format!("Carregando {}/{}...", c, t);
                }
                LoadMsg::Done(items) => {
                    self.loaded_items = items;
                    self.is_loading = false;
                    self.status_text = format!("Carregado {} imagens.", self.loaded_items.len());
                    self.log_lines.push(("Imagens carregadas com sucesso.".to_string(), LogLevel::Ok));
                }
                LoadMsg::Error(e) => {
                    self.is_loading = false;
                    self.status_text = "Erro no carregamento.".to_string();
                    self.log_lines.push((e, LogLevel::Error));
                }
            }
        }

        if let Ok(msg) = self.pack_rx.try_recv() {
            match msg {
                PackMsg::Log(s, l) => self.log_lines.push((s, l)),
                PackMsg::Status(s) => self.status_text = s,
                PackMsg::Done(res) => {
                    self.is_packing = false;
                    self.status_text = "Empacotamento concluido!".to_string();
                    let ci = egui::ColorImage::from_rgba_unmultiplied([res.preview_w as usize, res.preview_h as usize], &res.preview_rgba);
                    self.preview_texture = Some(ctx.load_texture("preview", ci, Default::default()));
                    self.preview_dims = (res.canvas_w, res.canvas_h);
                }
                PackMsg::Error(e) => {
                    self.is_packing = false;
                    self.status_text = "Erro no packing.".to_string();
                    self.log_lines.push((e, LogLevel::Error));
                }
            }
        }

        egui::SidePanel::left("sidebar").min_width(320.0).show(ctx, |ui| {
            ui.heading("Roll Packer Rust");
            ui.separator();
            
            if ui.button("📁 Selecionar Pasta").clicked() {
                if let Some(folder) = FileDialog::new().pick_folder() {
                    self.folder = Some(folder.clone());
                    self.log_lines.push((format!("Pasta selecionada: {:?}", folder), LogLevel::Info));
                }
            }
            if let Some(f) = &self.folder {
                ui.label(f.to_string_lossy());
            }

            ui.add_enabled_ui(self.folder.is_some() && !self.is_loading && !self.is_packing, |ui| {
                if ui.button("Carregar Imagens").clicked() {
                    self.start_loading(ctx.clone());
                }
            });

            ui.separator();
            ui.heading("Configurações");
            egui::Grid::new("config_grid").show(ui, |ui| {
                ui.label("Largura max (cm):");
                ui.add(egui::DragValue::new(&mut self.max_width_cm).range(10.0..=500.0).speed(0.5));
                ui.end_row();

                ui.label("Margem (cm):");
                ui.add(egui::DragValue::new(&mut self.margin_cm).range(0.0..=10.0).speed(0.1));
                ui.end_row();

                ui.label("Espaçamento (cm):");
                ui.add(egui::DragValue::new(&mut self.spacing_cm).range(0.0..=10.0).speed(0.1));
                ui.end_row();

                ui.label("Step (mm):");
                ui.add(egui::DragValue::new(&mut self.step_mm).range(1.0..=50.0).speed(0.1));
                ui.end_row();

                ui.label("Threshold Branco:");
                ui.add(egui::DragValue::new(&mut self.threshold).range(200..=255));
                ui.end_row();

                ui.label("Saída:");
                ui.text_edit_singleline(&mut self.output_name);
                ui.end_row();
            });

            ui.separator();
            ui.horizontal(|ui| {
                ui.label("Algoritmo:");
                ui.radio_value(&mut self.algorithm, Algorithm::Gallery, "Gallery");
                ui.radio_value(&mut self.algorithm, Algorithm::Fast, "Fast");
                ui.radio_value(&mut self.algorithm, Algorithm::Tight, "Tight");
                ui.radio_value(&mut self.algorithm, Algorithm::Masked, "Masked");
            });

            ui.checkbox(&mut self.allow_rotate, "Permitir rotação livre");

            ui.separator();
            ui.heading("Rótulo");
            ui.checkbox(&mut self.label_date_enabled, "Incluir Data");
            if self.label_date_enabled {
                ui.text_edit_singleline(&mut self.label_date);
            }
            ui.color_edit_button_rgba_unmultiplied(&mut self.label_color);
            egui::ComboBox::from_label("Posição")
                .selected_text(&self.label_position)
                .show_ui(ui, |ui| {
                    for pos in ["external_bottom_right", "external_bottom_left", "external_bottom_center", "overlay_bottom_right"] {
                        ui.selectable_value(&mut self.label_position, pos.to_string(), pos);
                    }
                });

            ui.separator();
            
            if self.is_loading || self.is_packing {
                ui.spinner();
                ui.label(&self.status_text);
            } else {
                let can_pack = !self.loaded_items.is_empty();
                ui.add_enabled_ui(can_pack, |ui| {
                    if ui.button("▶ GERAR ROLO").clicked() {
                        self.start_packing(ctx.clone());
                    }
                });
                ui.label(&self.status_text);
            }
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            egui::TopBottomPanel::bottom("log_panel").resizable(true).min_height(100.0).show_inside(ui, |ui| {
                egui::ScrollArea::vertical().stick_to_bottom(true).show(ui, |ui| {
                    for (msg, level) in &self.log_lines {
                        let color = match level {
                            LogLevel::Info => egui::Color32::WHITE,
                            LogLevel::Warn => egui::Color32::YELLOW,
                            LogLevel::Error => egui::Color32::RED,
                            LogLevel::Ok => egui::Color32::GREEN,
                            LogLevel::Muted => egui::Color32::GRAY,
                        };
                        ui.colored_label(color, msg);
                    }
                });
            });

            egui::CentralPanel::default().show_inside(ui, |ui| {
                egui::ScrollArea::both().show(ui, |ui| {
                    if let Some(tex) = &self.preview_texture {
                        ui.image(tex);
                        ui.label(format!("Dimensões: {} x {}", self.preview_dims.0, self.preview_dims.1));
                    } else {
                        ui.centered_and_justified(|ui| {
                            ui.label("Nenhum preview.");
                        });
                    }
                });
            });
        });

        if self.is_loading || self.is_packing {
            ctx.request_repaint();
        }
    }
}

impl RollPackerApp {
    fn start_loading(&mut self, ctx: egui::Context) {
        self.is_loading = true;
        self.progress = 0.0;
        self.loaded_items.clear();
        let folder = self.folder.clone().unwrap();
        let th = self.threshold;
        let prod_c = self.prod_classifier.clone();
        let qual_c = self.quality_classifier.clone();
        let tx = self.load_tx.clone();

        thread::spawn(move || {
            let cb = {
                let tx = tx.clone();
                let ctx = ctx.clone();
                move |curr, total| {
                    let _ = tx.send(LoadMsg::Progress(curr, total));
                    ctx.request_repaint();
                }
            };
            let _ = tx.send(LoadMsg::Log("Iniciando carregamento...".to_string(), LogLevel::Info));
            let items = process_images(&folder, 0, th, prod_c, qual_c, cb);
            let _ = tx.send(LoadMsg::Done(items));
            ctx.request_repaint();
        });
    }

    fn start_packing(&mut self, ctx: egui::Context) {
        self.is_packing = true;
        let items = self.loaded_items.clone();
        let tx = self.pack_tx.clone();
        let max_w = cm_to_px(self.max_width_cm, self.dpi);
        let spacing = cm_to_px(self.spacing_cm, self.dpi);
        let margin = cm_to_px(self.margin_cm, self.dpi);
        let step = cm_to_px(self.step_mm / 10.0, self.dpi).max(1);
        let alg = self.algorithm;
        let allow_rotate = self.allow_rotate;
        let perf = self.performance_mode.clone();
        
        let label_pos = self.label_position.clone();
        let label_date = if self.label_date_enabled { self.label_date.clone() } else { "".to_string() };
        let mut color_u8 = [0u8; 4];
        for i in 0..4 { color_u8[i] = (self.label_color[i] * 255.0) as u8; }

        let out_dir = self.folder.clone().unwrap();
        let out_name = self.output_name.clone();

        thread::spawn(move || {
            let _ = tx.send(PackMsg::Log("Preparando rótulos...".to_string(), LogLevel::Info));
            
            // Add labels
            let mut final_images = Vec::new();
            for item in items {
                let text = format!("{}\n{}\n{}", item.name, item.category, item.quality);
                let dyn_img = DynamicImage::ImageRgba8(item.image);
                let labeled = add_label_to_image(dyn_img, &text, &label_pos, &label_date, color_u8);
                final_images.push(labeled);
            }

            let _ = tx.send(PackMsg::Log("Executando empacotamento...".to_string(), LogLevel::Info));

            let (placed, cw, ch) = match alg {
                Algorithm::Gallery => pack_images_gallery(final_images, max_w, spacing, margin, allow_rotate),
                Algorithm::Fast => pack_images_fast(final_images, max_w, spacing, margin, allow_rotate),
                Algorithm::Tight => pack_images_tight(final_images, max_w, spacing, margin, step, allow_rotate),
                Algorithm::Masked => pack_images_masked(final_images, max_w, spacing, margin, step, allow_rotate, &perf),
            };

            let _ = tx.send(PackMsg::Log(format!("Rolo gerado com {} imagens. Renderizando canvas...", placed.len()), LogLevel::Info));

            let canvas = build_canvas(&placed, cw, ch);

            let _ = tx.send(PackMsg::Log("Salvando JPEG...".to_string(), LogLevel::Info));

            let out_path = out_dir.join(out_name);
            let paths = match split_and_save(&canvas, &out_path, 65000, 90) {
                Ok(p) => {
                    let _ = tx.send(PackMsg::Log("JPEG salvo com sucesso.".to_string(), LogLevel::Ok));
                    p
                },
                Err(e) => {
                    let _ = tx.send(PackMsg::Error(format!("Falha ao salvar: {}", e)));
                    Vec::new()
                }
            };

            // Prepare preview downscaled
            let scale = if cw > 1200 { 1200.0 / cw as f32 } else { 1.0 };
            let pw = (cw as f32 * scale) as u32;
            let ph = (ch as f32 * scale) as u32;
            let preview = image::imageops::resize(&canvas, pw, ph, image::imageops::FilterType::Lanczos3);
            
            let mut rgba_data = Vec::new();
            rgba_data.extend_from_slice(preview.as_raw());

            let _ = tx.send(PackMsg::Done(PackResult {
                paths,
                canvas_w: cw,
                canvas_h: ch,
                preview_w: pw,
                preview_h: ph,
                preview_rgba: rgba_data,
            }));

            ctx.request_repaint();
        });
    }
}

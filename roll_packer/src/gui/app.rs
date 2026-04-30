use eframe::egui;
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread;
use rfd::FileDialog;

use crate::engine::packing::{pack_images_gallery, pack_images_fast, pack_images_tight};
use crate::engine::packing_masked::pack_images_masked;

// Converte centímetros para pixels dado o DPI
fn cm_to_px(cm: f32, dpi: f32) -> u32 {
    ((cm * dpi) / 2.54).round() as u32
}

// Converte pixels para centímetros dado o DPI
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

// Resultado serializável para passar entre threads
pub struct PackResult {
    pub canvas_data: Vec<u8>, // imagem final RGBA renderizada
    pub canvas_w: u32,
    pub canvas_h: u32,
    pub canvas_h_cm: f32,
    pub dpi: f32,
}

pub struct RollPackerApp {
    image_paths: Vec<PathBuf>,
    // Parâmetros em CM
    max_width_cm: f32,
    spacing_cm: f32,
    margin_cm: f32,
    step_mm: f32, // step em mm para mais precisão
    dpi: f32,
    allow_rotate: bool,
    algorithm: Algorithm,
    performance_mode: String,

    is_packing: bool,
    tx: Sender<PackResult>,
    rx: Receiver<PackResult>,

    pack_result: Option<PackResult>,
    preview_texture: Option<egui::TextureHandle>,
    status_text: String,
}

impl Default for RollPackerApp {
    fn default() -> Self {
        let (tx, rx) = mpsc::channel();
        Self {
            image_paths: Vec::new(),
            max_width_cm: 60.0,  // 60 cm (rolo padrão)
            spacing_cm: 0.3,     // 3mm de espaço
            margin_cm: 0.5,      // 5mm de margem
            step_mm: 2.0,        // 2mm de step
            dpi: 100.0,          // 100 DPI padrão
            allow_rotate: false,
            algorithm: Algorithm::Fast,
            performance_mode: "balanced".to_string(),
            is_packing: false,
            tx,
            rx,
            pack_result: None,
            preview_texture: None,
            status_text: "Carregue imagens e clique em PACK!".to_string(),
        }
    }
}

impl eframe::App for RollPackerApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Verifica se chegou resultado da thread
        if let Ok(result) = self.rx.try_recv() {
            self.status_text = format!(
                "✅ Pronto! Canvas: {:.1} cm × {:.1} cm  ({} × {} px)",
                self.max_width_cm,
                result.canvas_h_cm,
                result.canvas_w,
                result.canvas_h
            );

            // Gera preview downscalado a partir do canvas real
            let scale = if result.canvas_w > 860 {
                860.0 / result.canvas_w as f32
            } else {
                1.0
            };
            let pw = ((result.canvas_w as f32 * scale) as usize).max(1);
            let ph = ((result.canvas_h as f32 * scale) as usize).max(1);
            let mut preview = vec![255u8; pw * ph * 4];

            let cw = result.canvas_w as usize;
            for sy in 0..ph {
                let src_y = (sy as f32 / scale) as usize;
                for sx in 0..pw {
                    let src_x = (sx as f32 / scale) as usize;
                    let src_idx = (src_y * cw + src_x) * 4;
                    let dst_idx = (sy * pw + sx) * 4;
                    if src_idx + 3 < result.canvas_data.len() {
                        preview[dst_idx]   = result.canvas_data[src_idx];
                        preview[dst_idx+1] = result.canvas_data[src_idx+1];
                        preview[dst_idx+2] = result.canvas_data[src_idx+2];
                        preview[dst_idx+3] = result.canvas_data[src_idx+3];
                    }
                }
            }

            let color_image = egui::ColorImage::from_rgba_unmultiplied([pw, ph], &preview);
            self.preview_texture = Some(ctx.load_texture("preview", color_image, Default::default()));
            self.pack_result = Some(result);
            self.is_packing = false;
        }

        egui::SidePanel::left("controls_panel").min_width(240.0).show(ctx, |ui| {
            ui.add_space(8.0);
            ui.heading("🎞 Roll Packer");
            ui.separator();

            // --- Carregar imagens ---
            if ui.button("📁 Carregar Pasta").clicked() {
                if let Some(folder) = FileDialog::new().pick_folder() {
                    let mut paths = Vec::new();
                    if let Ok(entries) = std::fs::read_dir(&folder) {
                        for entry in entries.flatten() {
                            let path = entry.path();
                            if path.is_file() {
                                if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                                    if ["png", "jpg", "jpeg", "webp"].contains(&ext.to_lowercase().as_str()) {
                                        paths.push(path);
                                    }
                                }
                            }
                        }
                    }
                    paths.sort();
                    self.status_text = format!("{} imagens carregadas", paths.len());
                    self.image_paths = paths;
                    self.pack_result = None;
                    self.preview_texture = None;
                }
            }
            ui.label(format!("📷 {} imagens", self.image_paths.len()));
            ui.separator();

            // --- Parâmetros em CM ---
            egui::Grid::new("params_grid")
                .num_columns(2)
                .spacing([8.0, 8.0])
                .show(ui, |ui| {
                    ui.label("🖨 DPI:");
                    ui.add(
                        egui::DragValue::new(&mut self.dpi)
                            .range(72.0..=1200.0)
                            .speed(1.0)
                            .suffix(" dpi"),
                    );
                    ui.end_row();

                    ui.label("📐 Largura max (cm):");
                    ui.add(
                        egui::DragValue::new(&mut self.max_width_cm)
                            .range(1.0..=500.0)
                            .speed(0.5)
                            .suffix(" cm"),
                    );
                    ui.end_row();

                    ui.label("🔲 Margem (cm):");
                    ui.add(
                        egui::DragValue::new(&mut self.margin_cm)
                            .range(0.0..=10.0)
                            .speed(0.05)
                            .suffix(" cm"),
                    );
                    ui.end_row();

                    ui.label("↔ Espaçamento (cm):");
                    ui.add(
                        egui::DragValue::new(&mut self.spacing_cm)
                            .range(0.0..=10.0)
                            .speed(0.05)
                            .suffix(" cm"),
                    );
                    ui.end_row();

                    ui.label("🔍 Step (mm):");
                    ui.add(
                        egui::DragValue::new(&mut self.step_mm)
                            .range(0.1..=50.0)
                            .speed(0.1)
                            .suffix(" mm"),
                    );
                    ui.end_row();
                });

            // Mostra equivalência em px para referência
            let w_px = cm_to_px(self.max_width_cm, self.dpi);
            let m_px = cm_to_px(self.margin_cm, self.dpi);
            let s_px = cm_to_px(self.spacing_cm, self.dpi);
            let step_px = cm_to_px(self.step_mm / 10.0, self.dpi).max(1);
            ui.add_space(2.0);
            egui::CollapsingHeader::new("ℹ Equivalência em pixels").show(ui, |ui| {
                ui.small(format!("Largura: {} px", w_px));
                ui.small(format!("Margem:  {} px", m_px));
                ui.small(format!("Espaço:  {} px", s_px));
                ui.small(format!("Step:    {} px", step_px));
            });
            ui.separator();

            ui.checkbox(&mut self.allow_rotate, "🔄 Permitir Rotação");
            ui.separator();

            // --- Algoritmo ---
            ui.label("Algoritmo:");
            ui.radio_value(&mut self.algorithm, Algorithm::Gallery, "Gallery (linhas)");
            ui.radio_value(&mut self.algorithm, Algorithm::Fast,    "Fast (prateleiras)");
            ui.radio_value(&mut self.algorithm, Algorithm::Tight,   "Tight (perfil)");
            ui.radio_value(&mut self.algorithm, Algorithm::Masked,  "Masked (alpha)");

            if self.algorithm == Algorithm::Masked {
                ui.separator();
                ui.label("Performance:");
                egui::ComboBox::from_id_source("perf_combo")
                    .selected_text(&self.performance_mode)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut self.performance_mode, "fast".to_string(),     "Fast");
                        ui.selectable_value(&mut self.performance_mode, "balanced".to_string(), "Balanced");
                        ui.selectable_value(&mut self.performance_mode, "quality".to_string(),  "Quality");
                    });
            }

            ui.separator();

            // --- Ação ---
            if self.is_packing {
                ui.horizontal(|ui| {
                    ui.spinner();
                    ui.label("Empacotando...");
                });
            } else {
                let can_pack = !self.image_paths.is_empty();
                ui.add_enabled_ui(can_pack, |ui| {
                    if ui.button("▶ PACK!").clicked() {
                        self.start_packing(ctx.clone());
                    }
                });
            }

            ui.separator();

            if self.pack_result.is_some() {
                if ui.button("💾 Exportar PNG").clicked() {
                    self.export();
                }
            }

            ui.separator();
            ui.label(&self.status_text);
        });

        // --- Painel central com preview ---
        egui::CentralPanel::default().show(ctx, |ui| {
            egui::ScrollArea::both().show(ui, |ui| {
                if let Some(tex) = &self.preview_texture {
                    ui.image(tex);
                } else if self.is_packing {
                    ui.centered_and_justified(|ui| {
                        ui.label("⏳ Processando...");
                    });
                } else {
                    ui.centered_and_justified(|ui| {
                        ui.label("Carregue imagens e clique em PACK!");
                    });
                }
            });
        });

        if self.is_packing {
            ctx.request_repaint();
        }
    }
}

impl RollPackerApp {
    fn start_packing(&mut self, ctx: egui::Context) {
        self.is_packing = true;
        self.pack_result = None;
        self.preview_texture = None;
        self.status_text = "⏳ Empacotando...".to_string();

        let paths = self.image_paths.clone();
        let alg = self.algorithm;
        let dpi = self.dpi;

        // Converte cm → px para o engine
        let max_width = cm_to_px(self.max_width_cm, dpi);
        let spacing   = cm_to_px(self.spacing_cm, dpi);
        let margin    = cm_to_px(self.margin_cm, dpi);
        let step      = cm_to_px(self.step_mm / 10.0, dpi).max(1);

        let allow_rotate = self.allow_rotate;
        let perf_mode = self.performance_mode.clone();
        let tx = self.tx.clone();

        thread::spawn(move || {
            let mut images = Vec::new();
            for p in &paths {
                match image::open(p) {
                    Ok(img) => images.push(img),
                    Err(e) => eprintln!("Erro ao abrir {:?}: {}", p, e),
                }
            }

            if images.is_empty() {
                eprintln!("Nenhuma imagem válida carregada!");
                return;
            }

            eprintln!(
                "Empacotando {} imagens | {}x? px | DPI={}",
                images.len(), max_width, dpi
            );

            let (placed_imgs, canvas_w, canvas_h) = match alg {
                Algorithm::Gallery => pack_images_gallery(images, max_width, spacing, margin, allow_rotate),
                Algorithm::Fast    => pack_images_fast(images, max_width, spacing, margin, allow_rotate),
                Algorithm::Tight   => pack_images_tight(images, max_width, spacing, margin, step, allow_rotate),
                Algorithm::Masked  => pack_images_masked(images, max_width, spacing, margin, step, allow_rotate, &perf_mode),
            };

            let canvas_h_cm = px_to_cm(canvas_h, dpi);
            eprintln!(
                "Concluído: {} imgs → canvas {} × {} px  ({:.1} cm)",
                placed_imgs.len(), canvas_w, canvas_h, canvas_h_cm
            );

            // Renderiza canvas final em RGBA com alpha blending correto
            let cw = canvas_w.max(1) as usize;
            let ch = canvas_h.max(1) as usize;
            let mut canvas_data = vec![255u8; cw * ch * 4]; // fundo branco opaco

            for pi in &placed_imgs {
                let rgba = pi.img.to_rgba8();
                let iw = rgba.width() as usize;
                let ih = rgba.height() as usize;
                let ox = pi.x as usize;
                let oy = pi.y as usize;

                for py in 0..ih {
                    let dy = oy + py;
                    if dy >= ch { break; }
                    for px in 0..iw {
                        let dx = ox + px;
                        if dx >= cw { break; }
                        let src = rgba.get_pixel(px as u32, py as u32);
                        if src[3] == 0 { continue; }
                        let idx = (dy * cw + dx) * 4;
                        let a = src[3] as f32 / 255.0;
                        let inv_a = 1.0 - a;
                        canvas_data[idx]   = (src[0] as f32 * a + canvas_data[idx]   as f32 * inv_a) as u8;
                        canvas_data[idx+1] = (src[1] as f32 * a + canvas_data[idx+1] as f32 * inv_a) as u8;
                        canvas_data[idx+2] = (src[2] as f32 * a + canvas_data[idx+2] as f32 * inv_a) as u8;
                        canvas_data[idx+3] = 255;
                    }
                }
            }

            let _ = tx.send(PackResult {
                canvas_data,
                canvas_w: cw as u32,
                canvas_h: ch as u32,
                canvas_h_cm,
                dpi,
            });

            ctx.request_repaint();
        });
    }

    fn export(&self) {
        if let Some(result) = &self.pack_result {
            let default_name = format!(
                "rolo_{:.0}x{:.1}cm.png",
                px_to_cm(result.canvas_w, result.dpi),
                result.canvas_h_cm
            );
            if let Some(path) = FileDialog::new()
                .add_filter("PNG", &["png"])
                .set_file_name(&default_name)
                .save_file()
            {
                let img = image::RgbaImage::from_raw(
                    result.canvas_w,
                    result.canvas_h,
                    result.canvas_data.clone(),
                );
                if let Some(img) = img {
                    match img.save(&path) {
                        Ok(_) => eprintln!("✅ Salvo em {:?}", path),
                        Err(e) => eprintln!("❌ Erro ao salvar: {}", e),
                    }
                }
            }
        }
    }
}

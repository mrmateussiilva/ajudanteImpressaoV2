use eframe::egui;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread;
use image::GenericImageView;
use rfd::FileDialog;

use crate::engine::packing::{pack_images_gallery, pack_images_fast, pack_images_tight, PlacedImage};
use crate::engine::packing_masked::pack_images_masked;

#[derive(PartialEq, Clone, Copy)]
pub enum Algorithm {
    Gallery,
    Fast,
    Tight,
    Masked,
}

pub struct RollPackerApp {
    image_paths: Vec<PathBuf>,
    max_width: u32,
    spacing: u32,
    margin: u32,
    step: u32,
    allow_rotate: bool,
    algorithm: Algorithm,
    performance_mode: String,
    
    is_packing: Arc<Mutex<bool>>,
    result: Arc<Mutex<Option<(Vec<PlacedImage>, u32, u32)>>>,
    
    preview_texture: Option<egui::TextureHandle>,
}

impl Default for RollPackerApp {
    fn default() -> Self {
        Self {
            image_paths: Vec::new(),
            max_width: 600, // standard roll size 60cm ~ 600mm? Let's use pixels for now
            spacing: 10,
            margin: 10,
            step: 8,
            allow_rotate: false,
            algorithm: Algorithm::Fast,
            performance_mode: "balanced".to_string(),
            is_packing: Arc::new(Mutex::new(false)),
            result: Arc::new(Mutex::new(None)),
            preview_texture: None,
        }
    }
}

impl eframe::App for RollPackerApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::SidePanel::left("controls_panel").show(ctx, |ui| {
            ui.heading("Roll Packer");
            ui.separator();
            
            if ui.button("Load Folder").clicked() {
                if let Some(folder) = FileDialog::new().pick_folder() {
                    let mut paths = Vec::new();
                    if let Ok(entries) = std::fs::read_dir(folder) {
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
                    self.image_paths = paths;
                }
            }
            ui.label(format!("Loaded {} images", self.image_paths.len()));
            ui.separator();
            
            ui.add(egui::Slider::new(&mut self.max_width, 100..=5000).text("Max Width"));
            ui.add(egui::Slider::new(&mut self.margin, 0..=100).text("Margin"));
            ui.add(egui::Slider::new(&mut self.spacing, 0..=100).text("Spacing"));
            ui.add(egui::Slider::new(&mut self.step, 1..=32).text("Step"));
            ui.checkbox(&mut self.allow_rotate, "Allow Rotate");
            
            ui.separator();
            ui.label("Algorithm");
            ui.radio_value(&mut self.algorithm, Algorithm::Gallery, "Gallery");
            ui.radio_value(&mut self.algorithm, Algorithm::Fast, "Fast");
            ui.radio_value(&mut self.algorithm, Algorithm::Tight, "Tight");
            ui.radio_value(&mut self.algorithm, Algorithm::Masked, "Masked");
            
            if self.algorithm == Algorithm::Masked {
                egui::ComboBox::from_label("Performance")
                    .selected_text(&self.performance_mode)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut self.performance_mode, "fast".to_string(), "Fast");
                        ui.selectable_value(&mut self.performance_mode, "balanced".to_string(), "Balanced");
                        ui.selectable_value(&mut self.performance_mode, "quality".to_string(), "Quality");
                    });
            }
            
            ui.separator();
            
            let is_packing = *self.is_packing.lock().unwrap();
            
            if is_packing {
                ui.spinner();
                ui.label("Packing...");
            } else {
                if ui.button("PACK!").clicked() && !self.image_paths.is_empty() {
                    *self.is_packing.lock().unwrap() = true;
                    *self.result.lock().unwrap() = None;
                    self.preview_texture = None;
                    
                    let paths = self.image_paths.clone();
                    let alg = self.algorithm;
                    let max_width = self.max_width;
                    let spacing = self.spacing;
                    let margin = self.margin;
                    let step = self.step;
                    let allow_rotate = self.allow_rotate;
                    let perf_mode = self.performance_mode.clone();
                    
                    let is_packing_clone = Arc::clone(&self.is_packing);
                    let result_clone = Arc::clone(&self.result);
                    let ctx_clone = ctx.clone();
                    
                    thread::spawn(move || {
                        let mut images = Vec::new();
                        for p in paths {
                            if let Ok(img) = image::open(&p) {
                                images.push(img);
                            }
                        }
                        
                        let result = match alg {
                            Algorithm::Gallery => pack_images_gallery(images, max_width, spacing, margin, allow_rotate),
                            Algorithm::Fast => pack_images_fast(images, max_width, spacing, margin, allow_rotate),
                            Algorithm::Tight => pack_images_tight(images, max_width, spacing, margin, step, allow_rotate),
                            Algorithm::Masked => pack_images_masked(images, max_width, spacing, margin, step, allow_rotate, &perf_mode),
                        };
                        
                        *result_clone.lock().unwrap() = Some(result);
                        *is_packing_clone.lock().unwrap() = false;
                        ctx_clone.request_repaint(); // Wake up UI
                    });
                }
            }
            
            ui.separator();
            if ui.button("Export").clicked() {
                if let Some(result) = &*self.result.lock().unwrap() {
                    let (_, w, h) = result;
                    if let Some(path) = FileDialog::new().add_filter("PNG", &["png"]).save_file() {
                        let mut canvas = image::RgbaImage::from_pixel(*w, *h, image::Rgba([255, 255, 255, 255]));
                        let (placed, _, _) = result;
                        for p in placed {
                            image::imageops::overlay(&mut canvas, &p.img, p.x as i64, p.y as i64);
                        }
                        let _ = canvas.save(path);
                    }
                }
            }
        });
        
        egui::CentralPanel::default().show(ctx, |ui| {
            egui::ScrollArea::both().show(ui, |ui| {
                if let Some(res) = &*self.result.lock().unwrap() {
                    let (_, _, h) = res;
                    ui.label(format!("Height: {}", h));
                    
                    // Generate texture if not exists
                    if self.preview_texture.is_none() {
                        let (_, w, h) = res;
                        let scale = if *w > 1000 { 1000.0 / *w as f32 } else { 1.0 };
                        let scaled_w = (*w as f32 * scale) as u32;
                        let scaled_h = (*h as f32 * scale) as u32;
                        
                        let mut canvas = image::RgbaImage::from_pixel(scaled_w, scaled_h, image::Rgba([240, 240, 240, 255]));
                        let (placed, _, _) = res;
                        for p in placed {
                            for cx in 0..p.img.width() {
                                for cy in 0..p.img.height() {
                                    if cx == 0 || cy == 0 || cx == p.img.width()-1 || cy == p.img.height()-1 {
                                        let sx = ((p.x + cx) as f32 * scale) as u32;
                                        let sy = ((p.y + cy) as f32 * scale) as u32;
                                        if sx < scaled_w && sy < scaled_h {
                                            canvas.put_pixel(sx, sy, image::Rgba([0, 0, 0, 255]));
                                        }
                                    } else {
                                        let pixel = p.img.get_pixel(cx, cy);
                                        if pixel[3] > 0 { // alpha > 0
                                            let sx = ((p.x + cx) as f32 * scale) as u32;
                                            let sy = ((p.y + cy) as f32 * scale) as u32;
                                            if sx < scaled_w && sy < scaled_h {
                                                canvas.put_pixel(sx, sy, image::Rgba([100, 150, 250, 255]));
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        
                        let size = [canvas.width() as _, canvas.height() as _];
                        let pixels = canvas.into_raw();
                        let color_image = egui::ColorImage::from_rgba_unmultiplied(size, &pixels);
                        self.preview_texture = Some(ctx.load_texture("preview", color_image, Default::default()));
                    }
                    
                    if let Some(tex) = &self.preview_texture {
                        ui.image(tex);
                    }
                } else {
                    ui.label("Load images and click PACK!");
                }
            });
        });
    }
}

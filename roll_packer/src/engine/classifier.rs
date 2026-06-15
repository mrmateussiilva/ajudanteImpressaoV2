use std::collections::HashMap;
use std::path::PathBuf;
use image::{GenericImageView, DynamicImage};
use rayon::prelude::*;

#[derive(Clone)]
struct ImageFeatures {
    aspect_ratio: f32,
    sharpness: f32,
    hist: Vec<f32>,
}

pub struct Classifier {
    training_dir: PathBuf,
    name: String,
    features: HashMap<String, Vec<ImageFeatures>>,
    pub category_names: Vec<String>,
    trained: bool,
}

impl Classifier {
    pub fn new(training_dir: &str, name: &str) -> Self {
        Self {
            training_dir: PathBuf::from(training_dir),
            name: name.to_string(),
            features: HashMap::new(),
            category_names: Vec::new(),
            trained: false,
        }
    }

    fn extract_features(img: &DynamicImage) -> Option<ImageFeatures> {
        let (w, h) = img.dimensions();
        if h == 0 || w == 0 { return None; }
        
        let aspect_ratio = w as f32 / h as f32;
        
        let gray = img.to_luma8();
        let w = w as usize;
        let h = h as usize;
        let raw_gray = gray.as_raw();
        
        // Sharpness: Laplacian variance
        let mut sum = 0.0;
        let mut sum_sq = 0.0;
        let mut count = 0.0;
        
        for y in 1..(h - 1) {
            let row_idx = y * w;
            let row_prev_idx = (y - 1) * w;
            let row_next_idx = (y + 1) * w;
            for x in 1..(w - 1) {
                let center = raw_gray[row_idx + x] as f32;
                let left = raw_gray[row_idx + x - 1] as f32;
                let right = raw_gray[row_idx + x + 1] as f32;
                let up = raw_gray[row_prev_idx + x] as f32;
                let down = raw_gray[row_next_idx + x] as f32;
                let v = center * 4.0 - left - right - up - down;
                sum += v;
                sum_sq += v * v;
                count += 1.0;
            }
        }
        let sharpness = if count > 0.0 {
            let mean = sum / count;
            (sum_sq / count) - (mean * mean)
        } else {
            0.0
        };

        // Color histogram (8x8x8 bins)
        let mut hist = vec![0.0; 512];
        let rgb = img.to_rgb8();
        let raw_rgb = rgb.as_raw();
        for chunk in raw_rgb.chunks_exact(3) {
            let r = (chunk[0] / 32) as usize;
            let g = (chunk[1] / 32) as usize;
            let b = (chunk[2] / 32) as usize;
            let idx = (r * 64) + (g * 8) + b;
            hist[idx] += 1.0;
        }
        
        // Normalize
        let mut sum_hist: f32 = 0.0;
        for &v in &hist { sum_hist += v * v; }
        let norm = sum_hist.sqrt();
        if norm > 0.0 {
            for v in &mut hist { *v /= norm; }
        }

        Some(ImageFeatures {
            aspect_ratio,
            sharpness,
            hist,
        })
    }

    pub fn train(&mut self) -> bool {
        if !self.training_dir.exists() || !self.training_dir.is_dir() {
            return false;
        }

        self.category_names.clear();
        self.features.clear();

        if let Ok(entries) = std::fs::read_dir(&self.training_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
                    if !name.starts_with('.') {
                        self.category_names.push(name);
                    }
                }
            }
        }

        // Primeiro, listamos todos os caminhos de imagens por categoria
        let mut category_images = HashMap::new();
        for cat in &self.category_names {
            let mut paths = Vec::new();
            let cat_path = self.training_dir.join(cat);
            if let Ok(entries) = std::fs::read_dir(cat_path) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                        let ext_l = ext.to_lowercase();
                        if ext_l == "jpg" || ext_l == "jpeg" || ext_l == "png" {
                            paths.push(path);
                        }
                    }
                }
            }
            category_images.insert(cat.clone(), paths);
        }

        // Paraleliza o carregamento e extração de características usando Rayon
        let features: HashMap<String, Vec<ImageFeatures>> = self.category_names
            .par_iter()
            .map(|cat| {
                let paths = &category_images[cat];
                let feats: Vec<ImageFeatures> = paths
                    .par_iter()
                    .filter_map(|path| {
                        if let Ok(img) = image::open(path) {
                            Self::extract_features(&img)
                        } else {
                            None
                        }
                    })
                    .collect();
                (cat.clone(), feats)
            })
            .collect();

        self.features = features;
        self.trained = true;
        true
    }

    pub fn classify(&mut self, img: &DynamicImage, filename: Option<&str>) -> String {
        if !self.trained && !self.train() {
            return "N/A".to_string();
        }

        let new_feat = match Self::extract_features(img) {
            Some(f) => f,
            None => return "Erro".to_string(),
        };

        let is_quality = self.training_dir.to_string_lossy().to_lowercase().contains("qualidade");
        let file_lower = filename.unwrap_or("").to_lowercase();

        let mut distances = Vec::new();

        for (category, cat_feats) in &self.features {
            let cat_lower = category.to_lowercase();
            let name_boost = if !file_lower.is_empty() && file_lower.contains(&cat_lower) {
                0.05
            } else {
                1.0
            };

            for feat in cat_feats {
                let ar_dist = (new_feat.aspect_ratio - feat.aspect_ratio).abs();
                
                // Chi-Square distance
                let mut hist_dist = 0.0;
                for i in 0..512 {
                    let diff = new_feat.hist[i] - feat.hist[i];
                    let sum = new_feat.hist[i] + feat.hist[i];
                    if sum > 0.0 {
                        hist_dist += (diff * diff) / sum;
                    }
                }

                let s1 = (new_feat.sharpness + 1.0).ln();
                let s2 = (feat.sharpness + 1.0).ln();
                let sharp_dist = (s1 - s2).abs();

                let total_dist = if is_quality {
                    (ar_dist * 5.0) + (hist_dist / 1000.0) + (sharp_dist * 20.0)
                } else {
                    (ar_dist * 15.0) + (hist_dist / 800.0) + (sharp_dist * 5.0)
                };

                let final_dist = total_dist * name_boost;
                distances.push((final_dist, category.clone()));
            }
        }

        if distances.is_empty() {
            return "Sem dados".to_string();
        }

        distances.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));

        let mut votes = HashMap::new();
        let k = distances.len().min(3);
        for i in 0..k {
            let cat = &distances[i].1;
            *votes.entry(cat.clone()).or_insert(0) += 1;
        }

        let mut winner = String::new();
        let mut max_votes = 0;
        for (cat, count) in votes {
            if count > max_votes {
                max_votes = count;
                winner = cat;
            }
        }

        if winner.is_empty() { "N/A".to_string() } else { winner }
    }
}

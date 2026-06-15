use std::path::{Path, PathBuf};
use image::{DynamicImage, GenericImageView, RgbaImage};
use rayon::prelude::*;
use std::sync::{Arc, Mutex};
use super::classifier::Classifier;
use super::image_ops::{remove_white, normalize_to_100dpi, trim_empty_borders};

#[derive(Clone)]
pub struct ImageItem {
    pub name: String,
    pub category: String,
    pub quality: String,
    pub image: RgbaImage,
    pub width_px: u32,
    pub height_px: u32,
}

#[derive(serde::Serialize, serde::Deserialize)]
struct CacheMeta {
    name: String,
    category: String,
    quality: String,
    width_px: u32,
    height_px: u32,
}

fn compute_hash(path: &Path, size: u64, mtime: u64, threshold: u8) -> String {
    let s = format!("v2|{}|{}|{}|{}", path.to_string_lossy(), size, mtime, threshold);
    format!("{:x}", md5::compute(s.as_bytes()))
}

pub fn process_images<F>(
    folder: &Path,
    _max_width_px: u32,
    threshold: u8,
    prod_classifier: Arc<Mutex<Classifier>>,
    quality_classifier: Arc<Mutex<Classifier>>,
    progress_cb: F,
) -> Vec<ImageItem>
where
    F: Fn(usize, usize) + Send + Sync,
{
    let mut files = Vec::new();
    if let Ok(entries) = std::fs::read_dir(folder) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                    let ext_l = ext.to_lowercase();
                    if ext_l == "jpg" || ext_l == "jpeg" || ext_l == "png" || ext_l == "webp" {
                        files.push(path);
                    }
                }
            }
        }
    }
    
    files.sort();
    
    let cache_dir = folder.join(".ajudante_cache");
    let _ = std::fs::create_dir_all(&cache_dir);

    let total = files.len();
    let processed_count = std::sync::atomic::AtomicUsize::new(0);

    let items: Vec<Option<ImageItem>> = files.par_iter().map(|path| {
        let meta = std::fs::metadata(path).ok()?;
        let size = meta.len();
        let mtime = meta.modified().ok()?.duration_since(std::time::UNIX_EPOCH).ok()?.as_secs();
        
        let hash = compute_hash(path, size, mtime, threshold);
        let cache_img = cache_dir.join(format!("{}.png", hash));
        let cache_json = cache_dir.join(format!("{}.json", hash));

        let filename = path.file_name()?.to_string_lossy().to_string();

        let mut item = None;

        if cache_img.exists() && cache_json.exists() {
            if let Ok(json_str) = std::fs::read_to_string(&cache_json) {
                if let Ok(meta_data) = serde_json::from_str::<CacheMeta>(&json_str) {
                    if let Ok(img) = image::open(&cache_img) {
                        item = Some(ImageItem {
                            name: meta_data.name,
                            category: meta_data.category,
                            quality: meta_data.quality,
                            image: img.into_rgba8(),
                            width_px: meta_data.width_px,
                            height_px: meta_data.height_px,
                        });
                    }
                }
            }
        }

        if item.is_none() {
            if let Ok(mut img) = image::open(path) {
                img = normalize_to_100dpi(img);
                img = remove_white(&img, threshold, 18);
                
                // Convert back to dynamic for trim_empty_borders
                img = DynamicImage::ImageRgba8(img.into_rgba8());
                img = trim_empty_borders(&img);

                let cat = {
                    let mut clf = prod_classifier.lock().unwrap();
                    clf.classify(&img, Some(&filename))
                };
                let qual = {
                    let mut clf = quality_classifier.lock().unwrap();
                    clf.classify(&img, Some(&filename))
                };

                let rgba = img.into_rgba8();
                let w = rgba.width();
                let h = rgba.height();

                let new_item = ImageItem {
                    name: filename.clone(),
                    category: cat.clone(),
                    quality: qual.clone(),
                    image: rgba.clone(),
                    width_px: w,
                    height_px: h,
                };

                let _ = rgba.save(&cache_img);
                let meta_data = CacheMeta {
                    name: filename,
                    category: cat,
                    quality: qual,
                    width_px: w,
                    height_px: h,
                };
                if let Ok(json_str) = serde_json::to_string(&meta_data) {
                    let _ = std::fs::write(&cache_json, json_str);
                }

                item = Some(new_item);
            }
        }

        let current = processed_count.fetch_add(1, std::sync::atomic::Ordering::SeqCst) + 1;
        progress_cb(current, total);

        item
    }).collect();

    items.into_iter().flatten().collect()
}

use std::path::{Path, PathBuf};
use image::{RgbImage, RgbaImage};
use jpeg_encoder::{Encoder, ColorType};

pub fn save_jpeg(img: &RgbImage, path: &Path, quality: u8) -> Result<(), Box<dyn std::error::Error>> {
    let encoder = Encoder::new_file(path, quality)?;
    encoder.encode(img.as_raw(), img.width() as u16, img.height() as u16, ColorType::Rgb)?;
    Ok(())
}

pub fn flatten_to_rgb(img: &RgbaImage) -> RgbImage {
    let (w, h) = img.dimensions();
    let mut rgb = RgbImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            let px = img.get_pixel(x, y);
            rgb.put_pixel(x, y, image::Rgb([px[0], px[1], px[2]]));
        }
    }
    rgb
}

pub const MAX_JPEG_DIM: u32 = 65000;

pub fn split_and_save(img: &RgbaImage, base_path: &Path, max_dim: u32, quality: u8) -> Result<Vec<PathBuf>, Box<dyn std::error::Error>> {
    let rgb = flatten_to_rgb(img);
    let (w, h) = rgb.dimensions();
    let mut paths = Vec::new();

    if h <= max_dim {
        save_jpeg(&rgb, base_path, quality)?;
        paths.push(base_path.to_path_buf());
    } else {
        let num_parts = (h + max_dim - 1) / max_dim;
        for i in 0..num_parts {
            let y0 = i * max_dim;
            let y1 = ((i + 1) * max_dim).min(h);
            
            let part = image::imageops::crop_imm(&rgb, 0, y0, w, y1 - y0).to_image();
            
            let mut name = base_path.file_stem().unwrap().to_string_lossy().to_string();
            name.push_str(&format!("_parte{}.jpg", i + 1));
            let part_path = base_path.with_file_name(name);
            
            save_jpeg(&part, &part_path, quality)?;
            paths.push(part_path);
        }
    }
    
    Ok(paths)
}

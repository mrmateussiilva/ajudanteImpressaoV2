use image::DynamicImage;

#[derive(Clone, Copy, serde::Serialize, serde::Deserialize)]
pub struct Span {
    pub start: u16,
    pub end: u16, // exclusive
}

pub fn trim_empty_borders(img: &DynamicImage) -> DynamicImage {
    let rgba = img.to_rgba8();
    let (width, height) = rgba.dimensions();

    let mut min_x = width;
    let mut min_y = height;
    let mut max_x = 0;
    let mut max_y = 0;

    let mut found = false;
    let raw = rgba.as_raw();

    for y in 0..height {
        let row_idx = y as usize * width as usize * 4;
        for x in 0..width {
            let idx = row_idx + x as usize * 4;
            let alpha = raw[idx + 3];
            if alpha > 0 {
                if x < min_x { min_x = x; }
                if y < min_y { min_y = y; }
                if x > max_x { max_x = x; }
                if y > max_y { max_y = y; }
                found = true;
            }
        }
    }

    if !found {
        return img.clone();
    }

    let crop_width = max_x - min_x + 1;
    let crop_height = max_y - min_y + 1;

    let cropped = image::imageops::crop_imm(img, min_x, min_y, crop_width, crop_height).to_image();
    DynamicImage::ImageRgba8(cropped)
}

#[derive(Clone)]
pub struct Mask {
    pub spans: Vec<Vec<Span>>,
    pub width: usize,
    pub height: usize,
    pub area: usize,
}

impl Mask {
    pub fn new(img: &DynamicImage) -> Self {
        let rgba = img.to_rgba8();
        let (w, h) = rgba.dimensions();
        let width = w as usize;
        let height = h as usize;
        let mut spans = Vec::with_capacity(height);
        let mut area = 0;
        let raw = rgba.as_raw();
        
        for y in 0..height {
            let mut row_spans = Vec::new();
            let mut in_span = false;
            let mut start = 0;
            let row_idx = y * width * 4;
            
            for x in 0..width {
                let active = raw[row_idx + x * 4 + 3] > 0;
                if active {
                    area += 1;
                    if !in_span {
                        start = x as u16;
                        in_span = true;
                    }
                } else {
                    if in_span {
                        row_spans.push(Span { start, end: x as u16 });
                        in_span = false;
                    }
                }
            }
            if in_span {
                row_spans.push(Span { start, end: width as u16 });
            }
            spans.push(row_spans);
        }
        
        Self { spans, width, height, area }
    }
}

pub fn remove_white(img: &DynamicImage, threshold: u8, softness: u8) -> DynamicImage {
    let mut rgba = img.to_rgba8();
    let fade_start = threshold.saturating_sub(softness);
    let softness_f = softness.max(1) as f32;
    
    let raw = rgba.as_mut();
    for pixel in raw.chunks_exact_mut(4) {
        let min_val = pixel[0].min(pixel[1]).min(pixel[2]);
        
        if min_val >= threshold {
            pixel[3] = 0;
        } else if min_val >= fade_start {
            let factor = (threshold as f32 - min_val as f32) / softness_f;
            pixel[3] = (pixel[3] as f32 * factor) as u8;
        }
    }
    
    DynamicImage::ImageRgba8(rgba)
}

pub fn normalize_to_100dpi(img: DynamicImage) -> DynamicImage {
    // In Rust `image` crate, DPI metadata is not easily accessible via DynamicImage
    // We will assume 100 dpi for now since the Python code relies on Image.info which might not be preserved.
    // If we want true DPI reading we'd need to parse the image bytes ourselves.
    // Let's return the image directly for now, or if we had DPI we would resize.
    img
}

pub fn add_label_to_image(
    img: DynamicImage, 
    text: &str, 
    position: &str, 
    date_str: &str, 
    color: [u8; 4]
) -> DynamicImage {
    use image::{RgbaImage, Rgba};
    use imageproc::drawing::{draw_text_mut, draw_filled_rect_mut};
    use imageproc::rect::Rect;
    use ab_glyph::{FontRef, PxScale};
    
    let mut rgba = img.to_rgba8();
    
    // We try to load Arial, if not, we fail gracefully and return the image
    let font_bytes = match std::fs::read("C:\\Windows\\Fonts\\arial.ttf") {
        Ok(b) => b,
        Err(_) => return DynamicImage::ImageRgba8(rgba)
    };
    
    let font = match FontRef::try_from_slice(&font_bytes) {
        Ok(f) => f,
        Err(_) => return DynamicImage::ImageRgba8(rgba)
    };
    
    let mut full_text = text.to_string();
    if !date_str.trim().is_empty() {
        full_text.push_str("\nEnvio: ");
        full_text.push_str(date_str.trim());
    }
    
    let is_external = position.starts_with("external_");
    let font_pt = 30; // default
    let font_size = if is_external {
        font_pt as f32
    } else {
        let size = (rgba.height() as f32 * 0.03).max(font_pt as f32);
        size
    };
    
    let scale = PxScale::from(font_size);
    
    // Calculate bounds manually (very rough approximation for now)
    let lines: Vec<&str> = full_text.split('\n').collect();
    let th = (font_size * lines.len() as f32) as i32;
    let mut max_w = 0.0;
    for line in &lines {
        let w = line.chars().count() as f32 * (font_size * 0.6); // rough width estimate
        if w > max_w { max_w = w; }
    }
    let tw = max_w as i32;
    
    let mut new_img = if is_external {
        let mut padding_h = 40; // 1cm roughly at 100 dpi
        if !date_str.trim().is_empty() {
            padding_h = padding_h.max(th + 20);
        }
        let mut canvas = RgbaImage::new(rgba.width(), rgba.height() + padding_h as u32);
        image::imageops::overlay(&mut canvas, &rgba, 0, 0);
        canvas
    } else {
        rgba
    };
    
    let (mut x, mut y) = (0, 0);
    
    if is_external {
        let padding_h = (new_img.height() - img.height()) as i32;
        y = img.height() as i32 + (padding_h - th) / 2;
        
        if position == "external_bottom_right" {
            x = new_img.width() as i32 - tw - 15;
        } else if position == "external_bottom_left" {
            x = 15;
        } else {
            x = (new_img.width() as i32 - tw) / 2;
        }
    } else {
        let margin_offset = 12;
        if position == "overlay_bottom_right" {
            x = new_img.width() as i32 - tw - margin_offset;
            y = new_img.height() as i32 - th - margin_offset;
        } else if position == "overlay_bottom_left" {
            x = margin_offset;
            y = new_img.height() as i32 - th - margin_offset;
        } else if position == "overlay_top_right" {
            x = new_img.width() as i32 - tw - margin_offset;
            y = margin_offset;
        } else if position == "overlay_top_left" {
            x = margin_offset;
            y = margin_offset;
        } else {
            x = new_img.width() as i32 - tw - margin_offset;
            y = new_img.height() as i32 - th - margin_offset;
        }
    }
    
    // Draw white background
    draw_filled_rect_mut(&mut new_img, Rect::at(x - 8, y - 5).of_size((tw + 16) as u32, (th + 10) as u32), Rgba([255, 255, 255, 255]));
    
    // Draw text
    let text_color = Rgba(color);
    let mut cy = y;
    for line in lines {
        draw_text_mut(&mut new_img, text_color, x, cy, scale, &font, line);
        cy += font_size as i32;
    }
    
    DynamicImage::ImageRgba8(new_img)
}


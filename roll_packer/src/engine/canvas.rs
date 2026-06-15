use image::{RgbaImage, Rgba};
use super::packing::PlacedImage;

pub fn build_canvas(placed: &[PlacedImage], width: u32, height: u32) -> RgbaImage {
    let mut canvas = RgbaImage::from_pixel(width, height, Rgba([255, 255, 255, 255]));
    let canvas_raw = canvas.as_mut();
    let canvas_w = width as usize;

    for pi in placed {
        let img = pi.img.to_rgba8();
        let ox = pi.x as usize;
        let oy = pi.y as usize;
        
        let img_w = img.width() as usize;
        let img_h = img.height() as usize;

        let y1 = (oy + img_h).min(height as usize);
        let x1 = (ox + img_w).min(width as usize);
        
        if y1 <= oy || x1 <= ox { continue; }

        let h_fit = y1 - oy;
        let w_fit = x1 - ox;

        let raw_src = img.as_raw();

        for y in 0..h_fit {
            let src_row_idx = y * img_w * 4;
            let dst_row_idx = (oy + y) * canvas_w * 4 + ox * 4;
            
            for x in 0..w_fit {
                let sx = src_row_idx + x * 4;
                let dx = dst_row_idx + x * 4;
                
                let a = raw_src[sx + 3] as u16;
                if a == 0 { continue; }
                
                if a == 255 {
                    canvas_raw[dx] = raw_src[sx];
                    canvas_raw[dx + 1] = raw_src[sx + 1];
                    canvas_raw[dx + 2] = raw_src[sx + 2];
                    canvas_raw[dx + 3] = raw_src[sx + 3];
                } else {
                    let ia = 255 - a;
                    canvas_raw[dx] = ((raw_src[sx] as u16 * a + canvas_raw[dx] as u16 * ia + 127) / 255) as u8;
                    canvas_raw[dx + 1] = ((raw_src[sx + 1] as u16 * a + canvas_raw[dx + 1] as u16 * ia + 127) / 255) as u8;
                    canvas_raw[dx + 2] = ((raw_src[sx + 2] as u16 * a + canvas_raw[dx + 2] as u16 * ia + 127) / 255) as u8;
                    canvas_raw[dx + 3] = canvas_raw[dx + 3].max(raw_src[sx + 3]);
                }
            }
        }
    }

    canvas
}

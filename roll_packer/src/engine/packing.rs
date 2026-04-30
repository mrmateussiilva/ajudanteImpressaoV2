use image::DynamicImage;
use std::cmp::{max, min};
use super::image_ops::trim_empty_borders;

pub struct PlacedImage {
    pub img: DynamicImage,
    pub x: u32,
    pub y: u32,
}

pub fn pack_images_gallery(
    images: Vec<DynamicImage>,
    max_width: u32,
    spacing: u32,
    margin: u32,
    allow_rotate: bool,
) -> (Vec<PlacedImage>, u32, u32) {
    let usable_width = max_width.saturating_sub(2 * margin);
    let mut prepared = Vec::new();

    for img in images {
        let mut trimmed = trim_empty_borders(&img);
        if allow_rotate {
            let (w, h) = (trimmed.width(), trimmed.height());
            if w > usable_width && h <= usable_width {
                trimmed = trimmed.rotate90();
            } else if h > w + (w / 2) && h <= usable_width {
                trimmed = trimmed.rotate90();
            }
        }
        prepared.push(trimmed);
    }

    prepared.sort_by_key(|im| std::cmp::Reverse(im.width() * im.height()));

    let mut rows: Vec<Vec<DynamicImage>> = Vec::new();
    let mut current_row: Vec<DynamicImage> = Vec::new();
    let mut current_width = 0;

    for img in prepared {
        let w = img.width();
        let extra = if current_row.is_empty() { w } else { w + spacing };
        if !current_row.is_empty() && current_width + extra > usable_width {
            rows.push(current_row);
            current_row = vec![img];
            current_width = w;
        } else {
            current_row.push(img);
            current_width += extra;
        }
    }
    if !current_row.is_empty() {
        rows.push(current_row);
    }

    let mut placed = Vec::new();
    let mut y = margin;

    for row_imgs in rows {
        let mut row_h = 0;
        let mut row_w = 0;
        for im in &row_imgs {
            row_h = max(row_h, im.height());
            row_w += im.width();
        }
        
        let gaps = spacing * (row_imgs.len().saturating_sub(1) as u32);
        let row_total = row_w + gaps;
        
        let mut x = margin;
        if row_total < usable_width {
            x += (usable_width - row_total) / 2;
        }

        for im in row_imgs {
            let w = im.width();
            placed.push(PlacedImage { img: im, x, y });
            x += w + spacing;
        }
        y += row_h + spacing;
    }

    let final_height = if !placed.is_empty() {
        y.saturating_sub(spacing) + margin
    } else {
        margin * 2
    };

    (placed, max_width, final_height)
}

struct FastRow {
    x: u32,
    y: u32,
    h: u32,
}

pub fn pack_images_fast(
    images: Vec<DynamicImage>,
    max_width: u32,
    spacing: u32,
    margin: u32,
    allow_rotate: bool,
) -> (Vec<PlacedImage>, u32, u32) {
    let usable_width = max_width.saturating_sub(2 * margin);
    let mut prepared = Vec::new();

    for img in images {
        let mut trimmed = trim_empty_borders(&img);
        if allow_rotate {
            let (w, h) = (trimmed.width(), trimmed.height());
            if w > usable_width && h <= usable_width {
                trimmed = trimmed.rotate90();
            } else if h > w && h <= usable_width {
                let rot = trimmed.rotate90();
                if rot.width() <= usable_width {
                    trimmed = rot;
                }
            }
        }
        prepared.push(trimmed);
    }

    prepared.sort_by_key(|im| std::cmp::Reverse((im.height(), im.width())));

    let mut rows: Vec<FastRow> = Vec::new();
    let mut placed = Vec::new();

    for img in prepared {
        let w = img.width();
        let h = img.height();
        
        let mut best_row_index = None;
        let mut best_waste = None;

        for (i, row) in rows.iter().enumerate() {
            let available = max_width.saturating_sub(margin).saturating_sub(row.x);
            if w <= available {
                let waste = available - w;
                if best_waste.is_none() || waste < best_waste.unwrap() {
                    best_waste = Some(waste);
                    best_row_index = Some(i);
                }
            }
        }

        if let Some(idx) = best_row_index {
            let row = &mut rows[idx];
            placed.push(PlacedImage { img: img.clone(), x: row.x, y: row.y });
            row.x += w + spacing;
            row.h = max(row.h, h);
        } else {
            let new_y = if let Some(last) = rows.last() {
                last.y + last.h + spacing
            } else {
                margin
            };
            rows.push(FastRow {
                x: margin + w + spacing,
                y: new_y,
                h,
            });
            placed.push(PlacedImage { img, x: margin, y: new_y });
        }
    }

    let mut final_height = margin;
    for row in &rows {
        final_height = max(final_height, row.y + row.h);
    }
    final_height += margin;

    (placed, max_width, final_height)
}

pub fn pack_images_tight(
    images: Vec<DynamicImage>,
    max_width: u32,
    spacing: u32,
    margin: u32,
    step: u32,
    allow_rotate: bool,
) -> (Vec<PlacedImage>, u32, u32) {
    let usable_width = max_width.saturating_sub(2 * margin);
    let mut prepared = Vec::new();

    for img in images {
        let trimmed = trim_empty_borders(&img);
        let mut variants = vec![trimmed.clone()];
        if allow_rotate {
            let rot = trimmed.rotate90();
            if rot.width() <= usable_width {
                variants.push(rot);
            }
        }
        
        let best_variant = variants.into_iter()
            .max_by_key(|im| (im.width() * im.height(), im.width(), im.height()))
            .unwrap();
            
        prepared.push(best_variant);
    }

    prepared.sort_by_key(|im| std::cmp::Reverse((im.width() * im.height(), im.height(), im.width())));

    let mut profile = vec![margin; max_width as usize];
    let mut placed = Vec::new();
    let mut max_y_used = margin;
    let step = max(1, step);

    for img in prepared {
        let w = img.width();
        let h = img.height();
        let x_start = margin;
        let mut x_end = max_width.saturating_sub(margin).saturating_sub(w);
        
        if x_end < x_start {
            x_end = x_start;
        }

        let mut best_x = margin;
        let mut best_y = None;
        let mut best_bottom = None;

        let mut x = x_start;
        while x <= x_end {
            let mut y = profile[x as usize];
            for i in 0..w {
                if (x + i) < max_width {
                    y = max(y, profile[(x + i) as usize]);
                }
            }
            let bottom = y + h;
            
            if best_bottom.is_none() || bottom < best_bottom.unwrap() || (bottom == best_bottom.unwrap() && y < best_y.unwrap()) {
                best_x = x;
                best_y = Some(y);
                best_bottom = Some(bottom);
            }
            x += step;
        }

        let y = best_y.unwrap_or(max_y_used + spacing);
        let bottom = y + h;
        best_x = if best_y.is_none() { margin } else { best_x };

        placed.push(PlacedImage { img: img.clone(), x: best_x, y });
        max_y_used = max(max_y_used, bottom);

        let reserve_start = max(margin, best_x.saturating_sub(spacing));
        let reserve_end = min(max_width - margin, best_x + w + spacing);
        
        for i in reserve_start..reserve_end {
            if (i as usize) < profile.len() {
                profile[i as usize] = max(profile[i as usize], bottom + spacing);
            }
        }
    }

    let final_height = max_y_used + margin;
    (placed, max_width, final_height)
}

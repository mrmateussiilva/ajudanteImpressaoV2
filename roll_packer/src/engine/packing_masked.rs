use image::DynamicImage;
use std::cmp::max;
use super::image_ops::{trim_empty_borders, Mask};
use super::packing::PlacedImage;

struct MaskVariant {
    img: DynamicImage,
    mask: Mask,
}

pub fn pack_images_masked(
    images: Vec<DynamicImage>,
    max_width: u32,
    spacing: u32,
    margin: u32,
    step: u32,
    allow_rotate: bool,
    performance_mode: &str, // "fast", "balanced", "quality"
) -> (Vec<PlacedImage>, u32, u32) {
    let usable_width = max_width.saturating_sub(2 * margin);
    let mut prepared = Vec::new();

    let angle_candidates = if allow_rotate {
        match performance_mode {
            "quality" => vec![0, 90, 180, 270, 45, 135, 225, 315],
            "balanced" => vec![0, 90, 180, 270],
            _ => vec![0, 90], // fast
        }
    } else {
        vec![0]
    };

    for img in images {
        let trimmed = trim_empty_borders(&img);
        let mut variants = Vec::new();
        for &angle in &angle_candidates {
            let variant_img = if angle == 0 {
                trimmed.clone()
            } else if angle == 90 {
                trimmed.rotate90()
            } else if angle == 180 {
                trimmed.rotate180()
            } else if angle == 270 {
                trimmed.rotate270()
            } else {
                trimmed.clone() // Need imageproc for arbitrary angles, fallback to 0 for now
            };
            
            let variant_img = trim_empty_borders(&variant_img);
            if variant_img.width() <= usable_width {
                let mask = Mask::new(&variant_img);
                if mask.area > 0 {
                    variants.push(MaskVariant { img: variant_img, mask });
                }
            }
        }
        
        if !variants.is_empty() {
            variants.sort_by_key(|v| std::cmp::Reverse(v.mask.area));
            prepared.push(variants);
        }
    }

    prepared.sort_by_key(|variants| {
        let primary = &variants[0];
        std::cmp::Reverse((primary.mask.area, primary.img.height(), primary.img.width()))
    });

    let mut placed = Vec::new();
    let step = max(1, step) as usize;
    let margin_u = margin as usize;
    let max_width_u = max_width as usize;
    
    // Occupancy grid (1D vec representing 2D grid)
    let mut occupancy = vec![false; max_width_u * 1024]; 
    let mut occ_height = 1024;
    let mut max_y_used = margin_u;

    for variants in prepared {
        let mut best_choice: Option<((usize, usize), (usize, std::cmp::Reverse<usize>, usize, usize, usize, isize), &MaskVariant)> = None;
        let spacing_u = spacing as usize;

        for variant in &variants {
            let mask = &variant.mask;
            let w = mask.width;
            let h = mask.height;

            // Ensure occupancy height
            let required_height = max_y_used + spacing_u + h + step + 64;
            if required_height > occ_height {
                let new_h = required_height + 1024;
                let mut new_occ = vec![false; max_width_u * new_h];
                new_occ[..max_width_u * occ_height]
                    .copy_from_slice(&occupancy[..max_width_u * occ_height]);
                occupancy = new_occ;
                occ_height = new_h;
            }

            let y_limit = max_y_used + spacing_u;
            let mut variant_best: Option<((usize, usize), (usize, std::cmp::Reverse<usize>, usize, usize, usize, isize), &MaskVariant)> = None;

            for fy in (margin_u..=y_limit).step_by(step) {
                let mut found_at_fy = false;
                for fx in (margin_u..=(max_width_u - margin_u).saturating_sub(w)).step_by(step) {
                    
                    let mut collides = false;
                    'outer: for my in 0..h {
                        let oy = fy + my;
                        let occ_row_idx = oy * max_width_u;
                        for span in &mask.spans[my] {
                            let start = occ_row_idx + fx + span.start as usize;
                            let end = occ_row_idx + fx + span.end as usize;
                            if occupancy[start..end].iter().any(|&b| b) {
                                collides = true;
                                break 'outer;
                            }
                        }
                    }

                    if !collides {
                        let bottom = fy + h;
                        let center_dist = ((fx + w / 2) as isize - (max_width_u / 2) as isize).abs();
                        let increases_height = if bottom > max_y_used { 1 } else { 0 };
                        let height_increase = bottom.saturating_sub(max_y_used);
                        let score = (
                            increases_height,
                            std::cmp::Reverse(mask.area),
                            height_increase,
                            fy,
                            bottom,
                            center_dist,
                        );
                        
                        if variant_best.is_none() || score < variant_best.unwrap().1 {
                            variant_best = Some(((fx, fy), score, variant));
                            found_at_fy = true;
                        }
                    }
                }
                if found_at_fy && variant_best.as_ref().unwrap().1.0 == 0 {
                    break;
                }
            }

            if let Some((pos, score, var)) = variant_best {
                if best_choice.is_none() || score < best_choice.as_ref().unwrap().1 {
                    best_choice = Some((pos, score, var));
                }
            }
        }

        let (final_pos, _, var) = best_choice.unwrap_or_else(|| {
            // Fallback
            let var = &variants[0];
            ((margin_u, max_y_used + spacing_u), (0, std::cmp::Reverse(0), 0, 0, 0, 0), var)
        });

        // Nudge gravity — limitado para não ser O(h × w × distancia)
        let mut x = final_pos.0;
        let mut y = final_pos.1;
        let h = var.mask.height;
        
        // Nudge UP: max step * 4 iterações para evitar loop longo
        let nudge_limit = step * 4;
        for _ in 0..nudge_limit {
            if y <= margin_u { break; }
            let ty = y - 1;
            let mut col = false;
            'nu: for my in 0..h {
                let occ_row_idx = (ty + my) * max_width_u;
                for span in &var.mask.spans[my] {
                    let start = occ_row_idx + x + span.start as usize;
                    let end = occ_row_idx + x + span.end as usize;
                    if occupancy[start..end].iter().any(|&b| b) {
                        col = true;
                        break 'nu;
                    }
                }
            }
            if col { break; }
            y -= 1;
        }
        // Nudge LEFT: max step * 4
        for _ in 0..nudge_limit {
            if x <= margin_u { break; }
            let tx = x - 1;
            let mut col = false;
            'nl: for my in 0..h {
                let occ_row_idx = (y + my) * max_width_u;
                for span in &var.mask.spans[my] {
                    let start = occ_row_idx + tx + span.start as usize;
                    let end = occ_row_idx + tx + span.end as usize;
                    if occupancy[start..end].iter().any(|&b| b) {
                        col = true;
                        break 'nl;
                    }
                }
            }
            if col { break; }
            x -= 1;
        }

        // Stamp: dilatação circular baseada em máscara
        if spacing_u > 0 {
            let mut dx_limits = Vec::with_capacity(spacing_u + 1);
            for dy in 0..=spacing_u {
                let limit = ((spacing_u * spacing_u - dy * dy) as f64).sqrt() as usize;
                dx_limits.push(limit);
            }
            
            for my in 0..h {
                for span in &var.mask.spans[my] {
                    for dy_offset in -(spacing_u as isize)..=(spacing_u as isize) {
                        let oy = (y as isize + my as isize + dy_offset) as usize;
                        if oy < margin_u || oy >= occ_height {
                            continue;
                        }
                        let dy_abs = dy_offset.abs() as usize;
                        let dx_limit = dx_limits[dy_abs];
                        
                        let start_x = (x as isize + span.start as isize - dx_limit as isize).max(margin_u as isize) as usize;
                        let end_x = (x as isize + span.end as isize + dx_limit as isize).min((max_width_u - margin_u) as isize) as usize;
                        
                        if start_x < end_x {
                            let row_idx = oy * max_width_u;
                            occupancy[row_idx + start_x..row_idx + end_x].fill(true);
                        }
                    }
                }
            }
        } else {
            for my in 0..h {
                let row_idx = (y + my) * max_width_u;
                for span in &var.mask.spans[my] {
                    let start_x = (x + span.start as usize).max(margin_u);
                    let end_x = (x + span.end as usize).min(max_width_u - margin_u);
                    if start_x < end_x {
                        occupancy[row_idx + start_x..row_idx + end_x].fill(true);
                    }
                }
            }
        }

        max_y_used = max(max_y_used, y + h);
        placed.push(PlacedImage {
            img: var.img.clone(),
            x: x as u32,
            y: y as u32,
        });
    }

    let final_height = max_y_used as u32 + margin;
    (placed, max_width, final_height)
}

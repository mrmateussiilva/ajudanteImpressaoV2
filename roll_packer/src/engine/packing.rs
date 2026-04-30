use image::DynamicImage;
use std::cmp::max;
use super::image_ops::trim_empty_borders;

pub struct PlacedImage {
    pub img: DynamicImage,
    pub x: u32,
    pub y: u32,
}

// ── Contorno real de uma imagem (spans por linha) ─────────────────────────────
struct Contour {
    img: DynamicImage,
    // Para cada linha, coluna esquerda e direita (inclusive, exclusive) com alpha > 0
    row_spans: Vec<(u32, u32)>,
    width: u32,
    height: u32,
    area: u32,
}

impl Contour {
    fn from_image(img: DynamicImage) -> Self {
        let trimmed = trim_empty_borders(&img);
        let (w, h) = (trimmed.width(), trimmed.height());
        let rgba = trimmed.to_rgba8();
        let mut row_spans = vec![(0u32, 0u32); h as usize];
        let mut area = 0u32;

        for y in 0..h {
            let mut left = w;
            let mut right = 0u32;
            for x in 0..w {
                if rgba.get_pixel(x, y)[3] > 10 {
                    if x < left { left = x; }
                    if x + 1 > right { right = x + 1; }
                    area += 1;
                }
            }
            if left < right {
                row_spans[y as usize] = (left, right);
            }
        }
        Self { img: trimmed, row_spans, width: w, height: h, area }
    }

    // Verifica colisão da imagem em (px, py) com a grid 2D
    fn collides(&self, px: u32, py: u32, grid: &[bool], grid_w: u32) -> bool {
        for r in 0..self.height {
            let (sl, sr) = self.row_spans[r as usize];
            if sl >= sr { continue; }
            let row_idx = ((py + r) * grid_w) as usize;
            let start = row_idx + (px + sl) as usize;
            let end = row_idx + (px + sr) as usize;
            // Se algum pixel na grid estiver ocupado, colide.
            // Slice .iter().any(|&b| b) é muito bem otimizado pelo compilador.
            if grid[start..end].iter().any(|&b| b) {
                return true;
            }
        }
        false
    }

    // Marca a imagem na grid, com dilatação pelo `spacing`
    fn stamp(&self, px: u32, py: u32, grid: &mut [bool], grid_w: u32, grid_h: u32, spacing: u32, margin: u32) {
        let right_limit = grid_w.saturating_sub(margin);
        for r in 0..self.height {
            let (sl, sr) = self.row_spans[r as usize];
            if sl >= sr { continue; }
            let y_start = (py + r).saturating_sub(spacing).max(margin);
            let y_end = (py + r + 1 + spacing).min(grid_h);
            let x_start = (px + sl).saturating_sub(spacing).max(margin);
            let x_end = (px + sr + spacing).min(right_limit);

            for y in y_start..y_end {
                let row_idx = (y * grid_w) as usize;
                let start = row_idx + x_start as usize;
                let end = row_idx + x_end as usize;
                grid[start..end].fill(true);
            }
        }
    }
}

// ── GALLERY ───────────────────────────────────────────────────────────────────
pub fn pack_images_gallery(
    images: Vec<DynamicImage>, max_width: u32, spacing: u32, margin: u32, allow_rotate: bool,
) -> (Vec<PlacedImage>, u32, u32) {
    let uw = max_width.saturating_sub(2 * margin);
    let mut prep: Vec<DynamicImage> = images.iter().map(|im| {
        let t = trim_empty_borders(im);
        if allow_rotate { let r = t.rotate90(); if r.width() <= uw { return r; } }
        t
    }).collect();
    prep.sort_by_key(|i| std::cmp::Reverse(i.width() * i.height()));

    let mut rows: Vec<Vec<DynamicImage>> = Vec::new();
    let mut cur: Vec<DynamicImage> = Vec::new();
    let mut cw = 0u32;
    for img in prep {
        let w = img.width();
        let extra = if cur.is_empty() { w } else { w + spacing };
        if !cur.is_empty() && cw + extra > uw { rows.push(cur); cur = vec![img]; cw = w; }
        else { cw += extra; cur.push(img); }
    }
    if !cur.is_empty() { rows.push(cur); }

    let mut placed = Vec::new();
    let mut y = margin;
    for row in rows {
        let rh = row.iter().map(|i| i.height()).max().unwrap_or(0);
        let rw: u32 = row.iter().map(|i| i.width()).sum::<u32>()
            + spacing * row.len().saturating_sub(1) as u32;
        let mut x = margin + uw.saturating_sub(rw) / 2;
        for im in row { let w = im.width(); placed.push(PlacedImage { img: im, x, y }); x += w + spacing; }
        y += rh + spacing;
    }
    (placed, max_width, (y.saturating_sub(spacing) + margin).max(margin * 2))
}

// ── FAST (Best-Fit Decreasing Height) ────────────────────────────────────────
pub fn pack_images_fast(
    images: Vec<DynamicImage>, max_width: u32, spacing: u32, margin: u32, allow_rotate: bool,
) -> (Vec<PlacedImage>, u32, u32) {
    let uw = max_width.saturating_sub(2 * margin);
    let mut prep: Vec<DynamicImage> = images.iter().map(|im| {
        let t = trim_empty_borders(im);
        if allow_rotate { let r = t.rotate90(); if r.width() <= uw && r.width() <= t.width() { return r; } }
        t
    }).collect();
    prep.sort_by_key(|i| std::cmp::Reverse(i.height()));

    struct Shelf { x: u32, y: u32, h: u32 }
    let mut shelves: Vec<Shelf> = Vec::new();
    let mut placed = Vec::new();
    let right = max_width - margin;

    for img in prep {
        let (w, h) = (img.width(), img.height());
        let mut best = None;
        let mut best_score = u64::MAX;
        for (i, s) in shelves.iter().enumerate() {
            let avail = right.saturating_sub(s.x);
            if w <= avail {
                let waste = avail - w;
                let hpen = if h > s.h { (h - s.h) as u64 * uw as u64 } else { 0 };
                let score = waste as u64 + hpen / 10;
                if score < best_score { best_score = score; best = Some(i); }
            }
        }
        if let Some(i) = best {
            let s = &mut shelves[i];
            placed.push(PlacedImage { img, x: s.x, y: s.y });
            s.x += w + spacing; s.h = max(s.h, h);
        } else {
            let ny = shelves.last().map_or(margin, |s| s.y + s.h + spacing);
            placed.push(PlacedImage { img, x: margin, y: ny });
            shelves.push(Shelf { x: margin + w + spacing, y: ny, h });
        }
    }
    let fh = shelves.iter().map(|s| s.y + s.h).max().unwrap_or(margin) + margin;
    (placed, max_width, fh)
}

// ── TIGHT / CONTORNO (True 2D Nesting - Bottom-Left) ──────────────────────────
//
// Fluxo correto:
//  1. Remove fundo (trim alpha)
//  2. Extrai contorno real (row_spans: span de pixels opacos por linha)
//  3. Ordena por área (maior primeiro)
//  4. Para as outras, varre de baixo para cima (Y) e da esquerda para direita (X)
//  5. Primeiro lugar onde não colidir, faz nudge para cima e esquerda para precisão.
//  6. Estampa no grid 2D com spacing expandido.
//
pub fn pack_images_tight(
    images: Vec<DynamicImage>, max_width: u32, spacing: u32, margin: u32, step: u32, allow_rotate: bool,
) -> (Vec<PlacedImage>, u32, u32) {
    let uw = max_width.saturating_sub(2 * margin);
    let step = max(1, step);

    // Constrói variantes (normal + rotação) e filtra as que cabem
    let mut all_variants: Vec<Vec<Contour>> = images.into_iter().map(|img| {
        let t = trim_empty_borders(&img);
        let mut vars = vec![Contour::from_image(t.clone())];
        if allow_rotate {
            let r = t.rotate90();
            if r.width() <= uw { vars.push(Contour::from_image(r)); }
        }
        vars.retain(|c| c.width <= uw && c.area > 0);
        vars.sort_by_key(|c| std::cmp::Reverse(c.area));
        vars
    }).filter(|v| !v.is_empty()).collect();

    // Ordena grupos: maior área primeiro
    all_variants.sort_by_key(|v| std::cmp::Reverse(v[0].area));

    let mut placed = Vec::new();
    let mut max_y_used = margin;
    
    // Grid 2D inicial com altura razoável
    let mut grid_h = 2000u32;
    let mut grid = vec![false; (max_width * grid_h) as usize];

    for variants in all_variants {
        let mut best_px = margin;
        let mut best_py = max_y_used + spacing;
        let mut best_vi = 0usize;
        let mut found = false;

        // Tenta cada variante, da maior área para menor
        for (vi, contour) in variants.iter().enumerate() {
            let w = contour.width;
            let h = contour.height;
            
            // Garante que o grid tem altura suficiente para testar
            let required_h = max_y_used + spacing + h + step + 500;
            if required_h > grid_h {
                let old_size = grid.len();
                grid.resize((max_width * required_h) as usize, false);
                grid_h = required_h;
            }

            let x_max = max_width.saturating_sub(margin + w);
            let y_max = max_y_used + spacing;

            let mut cand_py = margin;
            let mut cand_px = margin;
            let mut var_found = false;

            'search: for py in (margin..=y_max).step_by(step as usize) {
                for px in (margin..=x_max).step_by(step as usize) {
                    if !contour.collides(px, py, &grid, max_width) {
                        cand_px = px;
                        cand_py = py;
                        var_found = true;
                        break 'search;
                    }
                }
            }

            if var_found {
                // Encontrou! Agora faz nudge para refinar o encaixe do 'step'
                // Nudge UP (cima)
                while cand_py > margin {
                    if !contour.collides(cand_px, cand_py - 1, &grid, max_width) {
                        cand_py -= 1;
                    } else {
                        break;
                    }
                }
                // Nudge LEFT (esquerda)
                while cand_px > margin {
                    if !contour.collides(cand_px - 1, cand_py, &grid, max_width) {
                        cand_px -= 1;
                    } else {
                        break;
                    }
                }

                // Salva se for o melhor (menor y possível)
                // Como iteramos y de baixo pra cima, a primeira que acha já é a de menor y!
                if !found || cand_py < best_py || (cand_py == best_py && cand_px < best_px) {
                    best_py = cand_py;
                    best_px = cand_px;
                    best_vi = vi;
                    found = true;
                }
            }
        }

        // Se não achou (impossível em teoria já que y_max cresce, mas fallback de segurança)
        let contour = &variants[best_vi];
        if !found {
            best_px = margin;
            best_py = max_y_used + spacing;
        }

        // Estampa a peça escolhida
        // Garante grid height de novo (caso fallback)
        let required_h = best_py + contour.height + spacing + 500;
        if required_h > grid_h {
            grid.resize((max_width * required_h) as usize, false);
            grid_h = required_h;
        }

        contour.stamp(best_px, best_py, &mut grid, max_width, grid_h, spacing, margin);
        max_y_used = max(max_y_used, best_py + contour.height);
        placed.push(PlacedImage { img: contour.img.clone(), x: best_px, y: best_py });
    }

    (placed, max_width, max_y_used + margin)
}

// Alias para compatibilidade com packing_masked
pub use pack_images_tight as pack_images_masked_contour;

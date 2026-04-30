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

    // Menor y onde esta peça pode ser colocada em px dado o perfil atual
    fn min_y(&self, profile: &[u32], px: u32, margin: u32) -> u32 {
        let mut py = margin;
        for r in 0..self.height {
            let (sl, sr) = self.row_spans[r as usize];
            if sl >= sr { continue; }
            let x0 = (px + sl) as usize;
            let x1 = (px + sr) as usize;
            for x in x0..x1 {
                // Para que a linha r fique em py+r ≥ profile[x], precisa py ≥ profile[x] - r
                let needed = profile[x].saturating_sub(r);
                if needed > py { py = needed; }
            }
        }
        py
    }

    // Atualiza o perfil após colocar a peça em (px, py)
    fn stamp(&self, profile: &mut [u32], px: u32, py: u32, spacing: u32, margin: u32, max_w: u32) {
        let right_limit = max_w.saturating_sub(margin) as usize;
        for r in 0..self.height {
            let (sl, sr) = self.row_spans[r as usize];
            if sl >= sr { continue; }
            let x0 = (px + sl).saturating_sub(spacing).max(margin) as usize;
            let x1 = ((px + sr + spacing) as usize).min(right_limit);
            let bottom = py + r + 1 + spacing;
            for x in x0..x1 {
                if bottom > profile[x] { profile[x] = bottom; }
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

// ── TIGHT / CONTORNO (Skyline com row-spans reais) ────────────────────────────
//
// Fluxo correto:
//  1. Remove fundo (trim alpha)
//  2. Extrai contorno real (row_spans: span de pixels opacos por linha)
//  3. Ordena por área (maior primeiro) → coloca o maior em (margin, margin)
//  4. Para cada imagem seguinte, varre posições x candidatas e calcula
//     o menor y possível usando o contorno real (não bounding box)
//  5. Atualiza o perfil linha a linha com o contorno da peça recém colocada
//
pub fn pack_images_tight(
    images: Vec<DynamicImage>, max_width: u32, spacing: u32, margin: u32, step: u32, allow_rotate: bool,
) -> (Vec<PlacedImage>, u32, u32) {
    let uw = max_width.saturating_sub(2 * margin);
    let step = max(1, step);

    // Constrói variantes (normal + rotação) e filtra as que cabem
    let mut all_variants: Vec<Vec<Contour>> = images.iter().map(|img| {
        let t = trim_empty_borders(img);
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

    let mut profile = vec![margin; max_width as usize];
    let mut placed = Vec::new();
    let mut max_y_used = margin;

    for (group_idx, variants) in all_variants.iter().enumerate() {
        let mut best_px = margin;
        let mut best_py = max_y_used;
        let mut best_vi = 0usize;
        let mut best_score = (u32::MAX, u32::MAX, u32::MAX);

        // Primeiro item: coloca direto em (margin, margin)
        if group_idx == 0 {
            let c = &variants[0];
            c.stamp(&mut profile, margin, margin, spacing, margin, max_width);
            max_y_used = max(max_y_used, margin + c.height);
            placed.push(PlacedImage { img: c.img.clone(), x: margin, y: margin });
            continue;
        }

        for (vi, contour) in variants.iter().enumerate() {
            let w = contour.width;
            let x_max = max_width.saturating_sub(margin + w);

            // Candidatos: transições do perfil + varredura com step
            let mut cands: Vec<u32> = Vec::new();
            let mut prev = profile[margin as usize];
            for xi in margin..=x_max {
                let cur = profile[xi as usize];
                if cur != prev { cands.push(xi); prev = cur; }
            }
            let mut xi = margin;
            while xi <= x_max { cands.push(xi); xi += step; }
            cands.push(x_max);
            cands.sort_unstable(); cands.dedup();

            for px in cands {
                if px > x_max { break; }
                let py = contour.min_y(&profile, px, margin);
                let bottom = py + contour.height;
                let score = (max(bottom, max_y_used), bottom, px);
                if score < best_score {
                    best_score = score;
                    best_px = px;
                    best_py = py;
                    best_vi = vi;
                }
            }
        }

        let contour = &variants[best_vi];
        contour.stamp(&mut profile, best_px, best_py, spacing, margin, max_width);
        max_y_used = max(max_y_used, best_py + contour.height);
        placed.push(PlacedImage { img: contour.img.clone(), x: best_px, y: best_py });
    }

    (placed, max_width, max_y_used + margin)
}

// Alias para compatibilidade com packing_masked
pub use pack_images_tight as pack_images_masked_contour;

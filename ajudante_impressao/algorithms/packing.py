from __future__ import annotations

from typing import List

import cv2
import numpy as np
from PIL import Image

try:
    import numba
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

from .image_ops import fit_width, resize_to_height, trim_empty_borders


def pack_images_gallery(images: List[Image.Image], max_width: int, spacing: int, margin: int, row_height: int, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared: List[Image.Image] = []

    for img in images:
        img = trim_empty_borders(img)
        if allow_rotate:
            # Se for mais largo que o rolo mas couber em pé, rotaciona
            if img.width > usable_width and img.height <= usable_width:
                img = img.rotate(90, expand=True)
            # Se for muito alto e couber deitado, rotaciona para economizar altura
            elif img.height > img.width * 1.5 and img.height <= usable_width:
                img = img.rotate(90, expand=True)
        prepared.append(img)

    prepared.sort(key=lambda im: (im.width * im.height), reverse=True)
    rows: List[List[Image.Image]] = []
    current_row: List[Image.Image] = []
    current_width = 0

    for img in prepared:
        w = img.width
        extra = w if not current_row else w + spacing
        if current_row and current_width + extra > usable_width:
            rows.append(current_row)
            current_row = [img]
            current_width = img.width
        else:
            current_row.append(img)
            current_width += extra

    if current_row:
        rows.append(current_row)

    placed = []
    y = margin
    for row_imgs in rows:
        total_w = sum(im.width for im in row_imgs)
        gaps = spacing * (len(row_imgs) - 1)
        row_total = total_w + gaps
        scaled_row = row_imgs # Sem redimensionamento automático

        row_h = max(im.height for im in scaled_row)
        total_w = sum(im.width for im in scaled_row)
        gaps = spacing * (len(scaled_row) - 1)
        row_total = total_w + gaps
        x = margin
        if row_total < usable_width:
            x += (usable_width - row_total) // 2

        for im in scaled_row:
            placed.append((im, x, y))
            x += im.width + spacing
        y += row_h + spacing

    final_height = y - spacing + margin if placed else margin * 2
    return placed, max_width, final_height


def pack_images_fast(images: List[Image.Image], max_width: int, spacing: int, margin: int, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared = []

    for img in images:
        img = trim_empty_borders(img)
        if allow_rotate:
            # Prioridade 1: Rotacionar se for mais largo que o rolo
            if img.width > usable_width and img.height <= usable_width:
                img = img.rotate(90, expand=True)
            # Prioridade 2: Rotacionar se for muito alto para economizar altura
            elif img.height > img.width and img.height <= usable_width:
                rotated = img.rotate(90, expand=True)
                if rotated.width <= usable_width:
                    img = rotated
        prepared.append(img)

    prepared.sort(key=lambda im: (im.height, im.width), reverse=True)
    rows = []
    placed = []

    for img in prepared:
        w, h = img.size
        best_row_index = None
        best_waste = None

        for i, row in enumerate(rows):
            available = max_width - margin - row["x"]
            if w <= available:
                waste = available - w
                if best_waste is None or waste < best_waste:
                    best_waste = waste
                    best_row_index = i

        if best_row_index is not None:
            row = rows[best_row_index]
            x = row["x"]
            y = row["y"]
            placed.append((img, x, y))
            row["x"] += w + spacing
            row["h"] = max(row["h"], h)
        else:
            new_y = rows[-1]["y"] + rows[-1]["h"] + spacing if rows else margin
            rows.append({"x": margin + w + spacing, "y": new_y, "h": h})
            placed.append((img, margin, new_y))

    final_height = margin
    for row in rows:
        final_height = max(final_height, row["y"] + row["h"])
    final_height += margin
    return placed, max_width, final_height


def pack_images_tight(images: List[Image.Image], max_width: int, spacing: int, margin: int, step: int = 8, allow_rotate: bool = False):
    usable_width = max_width - 2 * margin
    prepared = []

    for img in images:
        variants = [img]
        if allow_rotate:
            rot = img.rotate(90, expand=True)
            if rot.width <= usable_width:
                variants.append(rot)

        normalized_variants = []
        for variant in variants:
            normalized_variants.append(variant)

        best_variant = max(normalized_variants, key=lambda im: (im.width * im.height, im.width, im.height))
        prepared.append(best_variant)

    prepared.sort(key=lambda im: (im.width * im.height, im.height, im.width), reverse=True)
    profile = np.full(max_width, margin, dtype=np.int32)
    placed = []
    max_y_used = margin
    step = max(1, step)

    for img in prepared:
        w, h = img.size
        x_start = margin
        x_end = max_width - margin - w

        if x_end < x_start:
            x_end = x_start  # Manter no início se for maior que o rolo

        best_x = margin
        best_y = None
        best_bottom = None

        for x in range(x_start, x_end + 1, step):
            y = int(profile[x:x + w].max())
            bottom = y + h
            if best_bottom is None or bottom < best_bottom or (bottom == best_bottom and y < best_y):
                best_x = x
                best_y = y
                best_bottom = bottom

        if best_y is None:
            best_x = margin
            best_y = max_y_used + spacing
            best_bottom = best_y + h

        placed.append((img, best_x, best_y))
        max_y_used = max(max_y_used, best_bottom)

        reserve_start = max(margin, best_x - spacing)
        reserve_end = min(max_width - margin, best_x + w + spacing)
        profile[reserve_start:reserve_end] = max(profile[reserve_start:reserve_end].max(), best_bottom + spacing)

    final_height = max_y_used + margin
    return placed, max_width, final_height


def _alpha_mask(img: Image.Image) -> np.ndarray:
    mask = np.array(img.getchannel("A"), dtype=np.uint8)
    return (mask > 0).astype(np.uint8)


def _quantize(value: int, step: int, minimum: int) -> int:
    if value <= minimum:
        return minimum
    return minimum + ((value - minimum + step - 1) // step) * step


def _prepare_mask_variants(img: Image.Image, usable_width: int, allow_rotate: bool, performance_mode: str = "balanced") -> list[dict]:
    img = trim_empty_borders(img)
    angle_candidates = [0]
    if allow_rotate:
        if performance_mode == "quality":
            # Busca mais agressiva de ângulos: 0, 90, 180, 270 e variações de 15 e 45 graus
            angle_candidates.extend([90, 180, 270, 15, -15, 30, -30, 45, 135, 225, 315, 60, -60])
        elif performance_mode == "balanced":
            angle_candidates.extend([90, 180, 270, 45, 135, 225, 315])
        else: # fast
            angle_candidates.extend([90, 180, 270])

    variants: list[dict] = []
    seen: set[tuple[int, int, int]] = set()

    for angle in angle_candidates:
        variant = img if angle == 0 else trim_empty_borders(img.rotate(angle, expand=True))
        # Removido redimensionamento automático para preservar dimensões originais
        if variant.width > usable_width:
            pass
        if variant.width > usable_width or variant.width <= 0 or variant.height <= 0:
            continue

        mask = _alpha_mask(variant)
        alpha_area = int(mask.sum())
        signature = (variant.width, variant.height, alpha_area)
        if alpha_area <= 0 or signature in seen:
            continue
        seen.add(signature)
        variants.append({"image": variant, "mask": mask, "area": alpha_area})

    variants.sort(key=lambda item: (item["area"], item["image"].height, item["image"].width), reverse=True)
    return variants


def _ensure_height(occupancy: np.ndarray, min_height: int) -> np.ndarray:
    if min_height <= occupancy.shape[0]:
        return occupancy
    # Crescimento controlado: apenas o necessário + margem de segurança
    growth = min_height + 512 
    expanded = np.zeros((growth, occupancy.shape[1]), dtype=np.uint8)
    expanded[: occupancy.shape[0], :] = occupancy
    return expanded


if HAS_NUMBA:
    @numba.njit(nogil=True)
    def _collides_jit(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, max_y_used: int) -> bool:
        if y >= max_y_used:
            return False
        h, w = mask.shape
        # Short-circuit loop: para no primeiro pixel que colidir
        for i in range(h):
            if y + i >= max_y_used:
                break
            for j in range(w):
                if mask[i, j] > 0 and occupancy[y + i, x + j] > 0:
                    return True
        return False

    @numba.njit(nogil=True)
    def _nudge_gravity_jit(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, margin: int, max_occ_y: int) -> tuple[int, int]:
        cx, cy = x, y
        for _ in range(2):
            while cy - 1 >= margin and not _collides_jit(occupancy, mask, cx, cy - 1, max_occ_y):
                cy -= 1
            while cx - 1 >= margin and not _collides_jit(occupancy, mask, cx - 1, cy, max_occ_y):
                cx -= 1
        return cx, cy

    @numba.njit(nogil=True)
    def _evaluate_batch_jit(occupancy: np.ndarray, mask: np.ndarray, candidates: np.ndarray, max_y_used: int, max_occ_y: int, max_width: int):
        # Avalia um lote de candidatos em paralelo (aproveita todos os cores)
        num = len(candidates)
        scores = np.full((num, 4), 99999999, dtype=np.int32)
        h_mask = mask.shape[0]
        w_mask = mask.shape[1]
        
        for i in range(num):
            fx, fy = candidates[i]
            if not _collides_jit(occupancy, mask, fx, fy, max_occ_y):
                bottom = fy + h_mask
                center_dist = abs(fx + w_mask // 2 - max_width // 2)
                scores[i, 0] = max(bottom, max_y_used)
                scores[i, 1] = bottom
                scores[i, 2] = fy
                scores[i, 3] = -center_dist
        
        best_idx = -1
        best_val = (99999999, 99999999, 99999999, 99999999)
        for i in range(num):
            s = (scores[i, 0], scores[i, 1], scores[i, 2], scores[i, 3])
            if s < best_val:
                best_val = s
                best_idx = i
        return best_idx, best_val

else:
    _collides_jit = None
    _nudge_gravity_jit = None
    _evaluate_batch_jit = None


def _collides(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, max_occ_y: int) -> bool:
    if y >= max_occ_y:
        return False
    h, w = mask.shape
    if y < 0 or x < 0 or y + h > occupancy.shape[0] or x + w > occupancy.shape[1]:
        return True
    
    if HAS_NUMBA and _collides_jit is not None:
        return _collides_jit(occupancy, mask, x, y, max_occ_y)
        
    check_h = min(h, max_occ_y - y)
    if check_h <= 0:
        return False
    return bool(np.any(occupancy[y:y + check_h, x:x + w] & mask[:check_h, :]))


def _stamp_reserved(occupancy: np.ndarray, mask: np.ndarray, x: int, y: int, spacing: int, margin: int, max_width: int) -> None:
    if spacing > 0:
        y_idx, x_idx = np.ogrid[-spacing:spacing+1, -spacing:spacing+1]
        # Kernel circular para um encaixe mais natural em cantos
        kernel = (x_idx**2 + y_idx**2 <= spacing**2).astype(np.uint8)
        padded = cv2.copyMakeBorder(mask, spacing, spacing, spacing, spacing, cv2.BORDER_CONSTANT, value=0)
        dilated = cv2.dilate(padded, kernel)
    else:
        dilated = mask
        spacing = 0

    h, w = dilated.shape
    ox = x - spacing
    oy = y - spacing
    occ_h, occ_w = occupancy.shape
    
    src_x0 = 0
    src_y0 = 0
    src_x1 = w
    src_y1 = h

    dst_x0 = ox
    dst_y0 = oy
    dst_x1 = ox + w
    dst_y1 = oy + h

    left_bound = margin
    right_bound = max_width - margin
    
    if dst_x0 < left_bound:
        src_x0 += (left_bound - dst_x0)
        dst_x0 = left_bound
    if dst_x1 > right_bound:
        src_x1 -= (dst_x1 - right_bound)
        dst_x1 = right_bound
        
    if dst_y0 < margin:
        src_y0 += (margin - dst_y0)
        dst_y0 = margin
    if dst_y1 > occ_h:
        src_y1 -= (dst_y1 - occ_h)
        dst_y1 = occ_h

    if src_x0 < src_x1 and src_y0 < src_y1:
        occupancy[dst_y0:dst_y1, dst_x0:dst_x1] |= dilated[src_y0:src_y1, src_x0:src_x1]


def _score_candidate(mask: np.ndarray, x: int, y: int, max_width: int, margin: int, max_y_used: int) -> tuple[int, int, int, int]:
    bottom = y + mask.shape[0]
    # Prioridade 1: Minimizar o aumento do rolo
    # Prioridade 2: Minimizar a base da peça (quanto mais alto melhor)
    # Prioridade 3: Minimizar o topo da peça (quanto mais alto melhor)
    # Prioridade 4: Favorecer encostar nas bordas (x pequeno ou x grande)
    center_dist = abs(x + mask.shape[1] // 2 - max_width // 2)
    return (max(bottom, max_y_used), bottom, y, -center_dist)


def pack_images_masked(images: List[Image.Image], max_width: int, spacing: int, margin: int, step: int = 8, allow_rotate: bool = False, progress_cb=None, performance_mode: str = "balanced"):
    usable_width = max_width - 2 * margin
    prepared = []
    for img in images:
        variants = _prepare_mask_variants(img, usable_width, allow_rotate, performance_mode)
        if not variants:
            continue
        primary = variants[0]
        prepared.append(
            {
                "variants": variants,
                "sort_key": (
                    primary["area"],
                    max(item["image"].height for item in variants),
                    max(item["image"].width for item in variants),
                ),
            }
        )

    prepared.sort(key=lambda item: item["sort_key"], reverse=True)
    occupancy = np.zeros((max(64, margin * 2 + 1), max_width), dtype=np.uint8)
    placed = []
    step = max(1, step)
    max_y_used = margin
    
    total_count = len(prepared)

    for i, piece in enumerate(prepared):
        if progress_cb:
            progress_cb(i, total_count)
        best_choice = None
        max_occ_y = max_y_used + spacing

        for variant in piece["variants"]:
            img = variant["image"]
            mask = variant["mask"]
            w, h = img.size
            variant_best = None
            
            # Garantir que a área de busca seja suficiente
            search_h = max_y_used + spacing + h + step
            occupancy = _ensure_height(occupancy, search_h)
            
            # --- BUSCA MULTI-ESCALA (COARSE-TO-FINE) ---
            if performance_mode == "quality":
                if w < max_width * 0.15 or h < 150:
                    factor = 1
                else:
                    factor = 2
            elif performance_mode == "balanced":
                if w < max_width * 0.15 or h < 150:
                    factor = 2
                else:
                    factor = 4
            else: # fast
                factor = 4
            
            try:
                if factor > 1:
                    mask_c = cv2.resize(mask, (0, 0), fx=1/factor, fy=1/factor, interpolation=cv2.INTER_AREA)
                    occ_slice = occupancy[:search_h, :]
                    occ_c = cv2.resize(occ_slice, (0, 0), fx=1/factor, fy=1/factor, interpolation=cv2.INTER_AREA)
                    res_c = cv2.matchTemplate(occ_c, mask_c, cv2.TM_CCORR)
                    
                    # BUSCA EXAUSTIVA: Agora olhamos o rolo inteiro sem limite de linhas
                    for cy in range(margin // factor, res_c.shape[0]):
                        base_y = cy * factor
                        min_y = base_y - factor
                        min_bottom = min_y + h
                        
                        if variant_best is not None:
                            best_s0 = variant_best["score"][0]
                            best_s1 = variant_best["score"][1]
                            if max(min_bottom, max_y_used) > best_s0:
                                break
                            if max(min_bottom, max_y_used) == best_s0 and min_bottom > best_s1:
                                break

                        row_c = res_c[cy, (margin // factor) : (max_width - w) // factor + 1]
                        promising_cx_indices = np.where(row_c < 1.0)[0] 
                        
                        if promising_cx_indices.size > 0:
                            found_any_in_coarse = True
                            
                            # Coletar candidatos para avaliação em lote (paralelo)
                            batch = []
                            # Reduzimos o step para um encaixe muito mais fino
                            fine_step = max(2, step // 2)
                            
                            for pcx in promising_cx_indices:
                                base_x = (margin // factor + pcx) * factor
                                base_y = cy * factor
                                for fy in range(max(margin, base_y - factor), base_y + factor + 1, fine_step):
                                    for fx in range(max(margin, base_x - factor), min(max_width - margin - w, base_x + factor + 1), fine_step):
                                        batch.append((fx, fy))
                            
                            if batch and HAS_NUMBA and _evaluate_batch_jit is not None:
                                idx, score = _evaluate_batch_jit(occupancy, mask, np.array(batch, dtype=np.int32), max_y_used, max_occ_y, max_width)
                                if idx != -1:
                                    if variant_best is None or score < variant_best["score"]:
                                        bx, by = batch[idx]
                                        variant_best = {"image": img, "mask": mask, "x": bx, "y": by, "score": score}
                            else:
                                # Fallback se batch for pequeno ou sem Numba
                                for fx, fy in batch:
                                    if not _collides(occupancy, mask, fx, fy, max_occ_y):
                                        score = _score_candidate(mask, fx, fy, max_width, margin, max_y_used)
                                        if variant_best is None or score < variant_best["score"]:
                                            variant_best = {"image": img, "mask": mask, "x": fx, "y": fy, "score": score}
                    
                    if not found_any_in_coarse:
                        raise Exception("No coarse match")
                else:
                    # Busca direta para peças pequenas (factor=1)
                    y_limit = max_y_used + spacing
                    for fy in range(margin, y_limit + 1, step):
                        found_at_fy = False
                        for fx in range(margin, max_width - margin - w + 1, step):
                            if not _collides(occupancy, mask, fx, fy, max_occ_y):
                                score = _score_candidate(mask, fx, fy, max_width, margin, max_y_used)
                                if variant_best is None or score < variant_best["score"]:
                                    variant_best = {"image": img, "mask": mask, "x": fx, "y": fy, "score": score}
                                    found_at_fy = True
                        if found_at_fy and variant_best["score"][1] < max_y_used:
                            break # Encontramos uma vaga num "buraco" acima do final do rolo

            except Exception:
                # Fallback para busca manual total se a miniatura falhar
                y = margin
                while y <= max_y_used + spacing:
                    x = margin
                    found_at_y = False
                    while x + w <= max_width - margin:
                        if not _collides(occupancy, mask, x, y, max_occ_y):
                            score = _score_candidate(mask, x, y, max_width, margin, max_y_used)
                            variant_best = {"image": img, "mask": mask, "x": x, "y": y, "score": score}
                            found_at_y = True
                            break
                        x += step
                    if found_at_y:
                        break
                    y += step
                
            if variant_best is not None:
                if best_choice is None or variant_best["score"] < best_choice["score"]:
                    best_choice = variant_best

        if best_choice is None:
            fallback = piece["variants"][0]
            img = fallback["image"]
            mask = fallback["mask"]
            x = margin
            y = max_y_used + spacing
            occupancy = _ensure_height(occupancy, y + img.height + spacing + margin + step)
            while x + img.width <= max_width - margin:
                if not _collides(occupancy, mask, x, y, max_occ_y):
                    break
                x += step
            best_choice = {"image": img, "mask": mask, "x": x, "y": y, "score": _score_candidate(mask, x, y, max_width, margin, max_y_used)}

        img = best_choice["image"]
        mask = best_choice["mask"]
        x = best_choice["x"]
        y = best_choice["y"]

        # --- REFINAMENTO DE GRAVIDADE (NUDGE) ---
        if HAS_NUMBA and _nudge_gravity_jit is not None:
            x, y = _nudge_gravity_jit(occupancy, mask, x, y, margin, max_occ_y)
        else:
            for _ in range(2):
                while y - 1 >= margin and not _collides(occupancy, mask, x, y - 1, max_occ_y):
                    y -= 1
                while x - 1 >= margin and not _collides(occupancy, mask, x - 1, y, max_occ_y):
                    x -= 1

        placed.append((img, x, y))
        _stamp_reserved(occupancy, mask, x, y, spacing, margin, max_width)
        max_y_used = max(max_y_used, y + img.height)

    final_height = max_y_used + margin
    return placed, max_width, final_height


if HAS_NUMBA:
    @numba.njit(nogil=True)
    def _blend_canvas_jit(canvas: np.ndarray, img: np.ndarray, x: int, y: int):
        h, w = img.shape[:2]
        ch, cw = canvas.shape[:2]
        y1, x1 = min(y + h, ch), min(x + w, cw)
        ih, iw = y1 - y, x1 - x
        if ih <= 0 or iw <= 0:
            return

        for i in range(ih):
            for j in range(iw):
                alpha = img[i, j, 3]
                if alpha == 255:
                    canvas[y + i, x + j] = img[i, j]
                elif alpha > 0:
                    a = alpha / 255.0
                    inv_a = 1.0 - a
                    for c in range(3):
                        new_val = img[i, j, c] * a + canvas[y + i, x + j, c] * inv_a
                        canvas[y + i, x + j, c] = np.uint8(new_val)
                    # Preservar o maior alpha ou marcar como opaco se o fundo for 255
                    canvas[y + i, x + j, 3] = max(alpha, canvas[y + i, x + j, 3])


def build_canvas(packed, width, height):
    # Composição ultra rápida usando Numba Parallel
    canvas_arr = np.zeros((height, width, 4), dtype=np.uint8)
    canvas_arr[:, :, :3] = 255  # Fundo branco
    canvas_arr[:, :, 3] = 255   # Alpha opaco para o fundo
    
    for img, x, y in packed:
        img_arr = np.array(img.convert("RGBA"))
        if HAS_NUMBA:
            _blend_canvas_jit(canvas_arr, img_arr, x, y)
        else:
            # Fallback NumPy (lento)
            h_img, w_img = img_arr.shape[:2]
            y1, x1 = min(y + h_img, height), min(x + w_img, width)
            h_fit, w_fit = y1 - y, x1 - x
            if h_fit <= 0 or w_fit <= 0: continue
            
            target = canvas_arr[y:y1, x:x1].astype(np.float32)
            source = img_arr[:h_fit, :w_fit].astype(np.float32)
            alpha = source[:, :, 3:4] / 255.0
            target[:, :, :3] = (source[:, :, :3] * alpha + target[:, :, :3] * (1 - alpha))
            canvas_arr[y:y1, x:x1] = target.astype(np.uint8)
        
    return Image.fromarray(canvas_arr, "RGBA")

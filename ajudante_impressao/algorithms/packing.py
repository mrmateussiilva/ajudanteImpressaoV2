from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .image_ops import trim_empty_borders


# ── Máscara alfa binária ──────────────────────────────────────────────────────
def _alpha_mask(img: Image.Image) -> np.ndarray:
    mask = np.array(img.getchannel("A"), dtype=np.uint8)
    return (mask > 0).astype(np.uint8)


def _quantize(value: int, step: int, minimum: int) -> int:
    if value <= minimum:
        return minimum
    return minimum + ((value - minimum + step - 1) // step) * step


@dataclass(slots=True)
class MaskVariant:
    image: Image.Image
    mask: np.ndarray
    area: int
    angle: int


@dataclass(slots=True)
class PackedPiece:
    image: Image.Image
    mask: np.ndarray
    x: int
    y: int
    w: int
    h: int
    area: int


# ── Rotação via cv2 (3-5x mais rápido que PIL para 90/180/270) ────────────────
_CV2_ROT_MAP = {
    90:  cv2.ROTATE_90_COUNTERCLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_CLOCKWISE,
}

def _rotate_image(img: Image.Image, angle: int) -> Image.Image:
    if angle in _CV2_ROT_MAP:
        arr = np.array(img)
        rotated_arr = cv2.rotate(arr, _CV2_ROT_MAP[angle])
        return Image.fromarray(rotated_arr)
    return img.rotate(angle, expand=True)


def _prepare_mask_variants(
    img: Image.Image,
    usable_width: int,
    allow_rotate: bool,
    performance_mode: str = "balanced",
) -> list[MaskVariant]:
    original_id = img.info.get("_original_id", None)
    img = trim_empty_borders(img)
    angle_candidates = [0]
    # Só rotaciona se a imagem original for paisagem (largura > altura).
    # Imagens retrato já são ideais para o rolo vertical. Rotacioná-las
    # aumentaria a largura consumida, bloqueando o rolo e gerando espaços vazios.
    if allow_rotate and img.width > img.height:
        if performance_mode == "fast":
            angle_candidates.extend([90])
        else:
            angle_candidates.extend([90, 270])

    variants: list[MaskVariant] = []
    seen: set[tuple[int, int, int]] = set()

    for angle in angle_candidates:
        variant = img if angle == 0 else trim_empty_borders(_rotate_image(img, angle))
        if variant.width > usable_width or variant.width <= 0 or variant.height <= 0:
            continue
        mask = _alpha_mask(variant)
        alpha_area = int(mask.sum())
        signature = (variant.width, variant.height, alpha_area)
        if alpha_area <= 0 or signature in seen:
            continue
        seen.add(signature)
        variant.info["_original_id"] = original_id
        variant.info["_original_angle"] = angle
        variants.append(MaskVariant(image=variant, mask=mask, area=alpha_area, angle=angle))

    variants.sort(key=lambda v: (v.area, v.image.height, v.image.width), reverse=True)
    return variants


def _ensure_height(occupancy: np.ndarray, min_height: int) -> np.ndarray:
    if min_height <= occupancy.shape[0]:
        return occupancy
    growth = max(min_height + 2048, occupancy.shape[0] * 2)
    expanded = np.zeros((growth, occupancy.shape[1]), dtype=np.uint8)
    expanded[: occupancy.shape[0], :] = occupancy
    return expanded


def _build_stamp_kernel(spacing: int) -> np.ndarray:
    y_idx, x_idx = np.ogrid[-spacing:spacing + 1, -spacing:spacing + 1]
    return (x_idx ** 2 + y_idx ** 2 <= spacing ** 2).astype(np.uint8)


def _collides(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    max_occ_y: int,
) -> bool:
    if y >= max_occ_y:
        return False
    h, w = mask.shape
    if y < 0 or x < 0 or y + h > occupancy.shape[0] or x + w > occupancy.shape[1]:
        return True
    check_h = min(h, max_occ_y - y)
    if check_h <= 0:
        return False
    occ_slice = occupancy[y:y + check_h, x:x + w]
    # Fast-path: se não há nada ocupado nessa região, não há colisão
    if not occ_slice.any():
        return False
    # Checa sobreposição real com a máscara
    return bool((occ_slice & mask[:check_h, :]).any())


def _stamp_reserved(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    spacing: int,
    margin: int,
    max_width: int,
    stamp_kernel: np.ndarray | None = None,
) -> None:
    if spacing > 0:
        if stamp_kernel is None:
            stamp_kernel = _build_stamp_kernel(spacing)
        padded = cv2.copyMakeBorder(mask, spacing, spacing, spacing, spacing, cv2.BORDER_CONSTANT, value=0)
        dilated = cv2.dilate(padded, stamp_kernel)
    else:
        dilated = mask
        spacing = 0

    h, w = dilated.shape
    ox, oy = x - spacing, y - spacing
    occ_h, occ_w = occupancy.shape

    src_x0, src_y0, src_x1, src_y1 = 0, 0, w, h
    dst_x0, dst_y0, dst_x1, dst_y1 = ox, oy, ox + w, oy + h

    left_bound, right_bound = margin, max_width - margin

    if dst_x0 < left_bound:
        src_x0 += left_bound - dst_x0
        dst_x0 = left_bound
    if dst_x1 > right_bound:
        src_x1 -= dst_x1 - right_bound
        dst_x1 = right_bound
    if dst_y0 < margin:
        src_y0 += margin - dst_y0
        dst_y0 = margin
    if dst_y1 > occ_h:
        src_y1 -= dst_y1 - occ_h
        dst_y1 = occ_h

    if src_x0 < src_x1 and src_y0 < src_y1:
        occupancy[dst_y0:dst_y1, dst_x0:dst_x1] |= dilated[src_y0:src_y1, src_x0:src_x1]


def _score_contact(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    spacing: int,
) -> int:
    h, w = mask.shape
    y0 = max(0, y - spacing - 2)
    y1 = min(y + h + spacing + 2, occupancy.shape[0])
    x0 = max(0, x - spacing - 2)
    x1 = min(x + w + spacing + 2, occupancy.shape[1])
    return int(occupancy[y0:y1, x0:x1].sum())


def _score_candidate(
    mask: np.ndarray,
    x: int, y: int,
    max_width: int,
    margin: int,
    max_y_used: int,
    area: int,
) -> tuple:
    bottom = y + mask.shape[0]
    increases_height = 1 if bottom > max_y_used else 0
    height_increase = max(0, bottom - max_y_used)
    center_dist = abs(x + mask.shape[1] // 2 - max_width // 2)
    space_right = max_width - margin - (x + mask.shape[1])
    fragmentation_penalty = 1 if 0 < space_right < 50 else 0
    return (increases_height, height_increase, fragmentation_penalty, -area, y, bottom, -center_dist)


def _dedupe_candidates(candidates: list[tuple[int, int]], limit: int) -> list[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    deduped: list[tuple[int, int]] = []
    for x, y in candidates:
        key = (int(x), int(y))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
        if len(deduped) >= limit:
            break
    return deduped


def _collect_frontier_candidates(
    occupancy: np.ndarray,
    placed: list[PackedPiece],
    margin: int,
    max_width: int,
    search_h: int,
    piece_w: int,
    piece_h: int,
    step: int,
    spacing: int,
    limit: int = 256,
) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = [(margin, margin)]

    max_y_used = max((piece.y + piece.h for piece in placed), default=margin)
    band_top = max(margin, max_y_used - max(piece_h * 2, step * 6))
    band_bottom = min(search_h, max_y_used + max(piece_h, step * 2))
    row_stride = max(2, step // 2)
    x_limit = max(margin, max_width - margin - piece_w)

    for piece in placed:
        right_x = piece.x + piece.w + spacing
        below_y = piece.y + piece.h + spacing
        candidates.append((right_x, piece.y))
        candidates.append((piece.x, below_y))
        candidates.append((right_x, below_y))
        candidates.append((piece.x + piece.w // 2 - piece_w // 2, piece.y))
        candidates.append((piece.x, piece.y + piece.h // 2 - piece_h // 2))

    if band_bottom > band_top:
        for y in range(band_top, band_bottom, row_stride):
            row = occupancy[y, margin:max_width - margin]
            if not row.any():
                continue
            padded = np.pad(row.astype(np.int8), (1, 1), mode="constant", constant_values=0)
            transitions = np.diff(padded)
            starts = np.where(transitions == 1)[0] + margin
            ends = np.where(transitions == -1)[0] + margin
            for start, end in zip(starts.tolist(), ends.tolist()):
                candidates.append((end + spacing, y))
                candidates.append((end, y))
                candidates.append((max(margin, start - piece_w), y))
                candidates.append((max(margin, start - piece_w // 2), y))
                candidates.append((min(x_limit, end + spacing // 2), y))

    filtered: list[tuple[int, int]] = []
    for x, y in candidates:
        if x < margin or y < margin:
            continue
        if x > x_limit:
            continue
        if y > search_h:
            continue
        filtered.append((x, y))

    filtered.sort(key=lambda p: (p[1], p[0]))
    return _dedupe_candidates(filtered, limit)


def _refine_candidate(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int,
    y: int,
    min_x: int,
    min_y: int,
    max_occ_y: int,
    max_width: int,
    max_iters: int = 6,
) -> tuple[int, int]:
    step = 4
    for _ in range(max_iters):
        moved = False
        for dx, dy in ((0, -1), (-1, 0), (-1, -1), (1, -1)):
            nx = x + dx * step
            ny = y + dy * step
            if nx < min_x or ny < min_y:
                continue
            if nx + mask.shape[1] > max_width:
                continue
            if not _collides(occupancy, mask, nx, ny, max_occ_y):
                x, y = nx, ny
                moved = True
                break
        if not moved:
            if step == 1:
                break
            step = max(1, step // 2)
    return x, y


def _find_valid_positions_nfp(
    occupancy: np.ndarray,
    mask: np.ndarray,
    max_width: int,
    margin: int,
    search_h: int,
    step: int = 8,
    spacing: int = 0,
    scale: int = 8,
    top_k: int = 128,
    raster_search: bool = True,
) -> list[tuple[int, int]]:
    """Busca candidatos por fronteira e, quando habilitado, por NFP raster.

    A fronteira é barata e captura os encaixes óbvios. O NFP raster coarse-to-fine
    volta a varrer a área livre do canvas para encontrar vãos internos que a
    fronteira sozinha não enxerga.
    """
    h_m, w_m = mask.shape
    if h_m <= 0 or w_m <= 0:
        return [(margin, margin)]

    if not occupancy[:search_h, :].any():
        return [(margin, margin)]

    results: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    placed: list[PackedPiece] = getattr(_find_valid_positions_nfp, "_placed_cache", [])  # type: ignore[attr-defined]
    frontier_limit = top_k if not raster_search else max(32, min(96, top_k // 3))
    frontier_candidates = _collect_frontier_candidates(
        occupancy=occupancy,
        placed=placed,
        margin=margin,
        max_width=max_width,
        search_h=search_h,
        piece_w=w_m,
        piece_h=h_m,
        step=step,
        spacing=spacing,
        limit=frontier_limit,
    )

    for fx, fy in frontier_candidates:
        if (fx, fy) in seen:
            continue
        seen.add((fx, fy))
        if fx + w_m > max_width - margin or fy + h_m > search_h:
            continue
        if not _collides(occupancy, mask, fx, fy, search_h):
            results.append((fx, fy))

    if not raster_search:
        return results[:top_k] if results else [(margin, search_h - h_m)]

    h_c = max(2, search_h // scale)
    w_c = max(2, max_width // scale)

    occ_slice_f = occupancy[:search_h, :].astype(np.float32)
    occ_small = cv2.resize(occ_slice_f, (w_c, h_c), interpolation=cv2.INTER_AREA)
    free_c = 1.0 - occ_small.clip(0.0, 1.0)

    mask_w_c = max(1, w_m // scale)
    mask_h_c = max(1, h_m // scale)
    mask_small = cv2.resize(mask.astype(np.float32), (mask_w_c, mask_h_c), interpolation=cv2.INTER_AREA)

    if mask_small.shape[0] >= free_c.shape[0] or mask_small.shape[1] >= free_c.shape[1]:
        return results[:top_k] if results else [(margin, search_h - h_m)]

    mask_sum = float(mask_small.sum())
    if mask_sum < 1.0:
        return results[:top_k] if results else [(margin, margin)]

    res = cv2.matchTemplate(free_c, mask_small, cv2.TM_CCORR)
    res_norm = res / mask_sum

    ys_c = xs_c = np.array([], dtype=np.int64)
    for thresh in (0.995, 0.97, 0.90, 0.75, 0.50, 0.20):
        ys_c, xs_c = np.where(res_norm >= thresh)
        if len(ys_c) > 0:
            break

    if len(ys_c) == 0:
        return results[:top_k] if results else [(margin, search_h - h_m)]

    margin_c = max(0, margin // scale)
    x_limit_c = max(1, (max_width - margin - w_m) // scale)
    valid = (ys_c >= margin_c) & (xs_c >= margin_c) & (xs_c <= x_limit_c)
    ys_c, xs_c = ys_c[valid], xs_c[valid]

    if len(ys_c) == 0:
        return results[:top_k] if results else [(margin, search_h - h_m)]

    order = np.lexsort((xs_c, ys_c))
    candidates_coarse: list[tuple[int, int]] = []
    seen_cells: set[tuple[int, int]] = set()
    for cx, cy in zip(xs_c[order].tolist(), ys_c[order].tolist()):
        cell = (cx // 4, cy // 4)
        if cell in seen_cells:
            continue
        seen_cells.add(cell)
        candidates_coarse.append((cx, cy))
        if len(candidates_coarse) >= 2048:
            break

    fine_step = max(1, scale // 2)
    coarse_evaluated = 0
    for cx_c, cy_c in candidates_coarse:
        coarse_evaluated += 1
        base_y = cy_c * scale
        base_x = cx_c * scale

        for dy in range(-scale, scale + 1, fine_step):
            for dx in range(-scale, scale + 1, fine_step):
                fy = base_y + dy
                fx = base_x + dx
                if fy < margin or fx < margin or fx + w_m > max_width - margin or fy + h_m > search_h:
                    continue
                if (fx, fy) in seen:
                    continue
                seen.add((fx, fy))
                if not _collides(occupancy, mask, fx, fy, search_h):
                    results.append((fx, fy))
                    if len(results) >= top_k:
                        return results

        if coarse_evaluated >= 1024:
            break

    return results if results else [(margin, search_h - h_m)]


def _nudge_gravity_full(
    occupancy: np.ndarray,
    mask: np.ndarray,
    x: int, y: int,
    min_x: int,
    min_y: int,
    max_occ_y: int,
    max_iters: int = 10,
) -> tuple[int, int]:
    """Desloca a peça em direção ao canto superior-esquerdo com passo decrescente."""
    DIRS = [(0, -1), (-1, 0), (-1, -1), (1, -1)]
    step = 4
    for _ in range(max_iters):
        moved = False
        for dx, dy in DIRS:
            nx, ny = x + dx * step, y + dy * step
            if ny < min_y or nx < min_x:
                continue
            if not _collides(occupancy, mask, nx, ny, max_occ_y):
                x, y = nx, ny
                moved = True
                break
        if not moved:
            if step == 1:
                break
            step = max(1, step // 2)
    return x, y


def pack_images_masked(
    images: list[Image.Image],
    max_width: int,
    spacing: int,
    margin: int,
    step: int = 8,
    allow_rotate: bool = False,
    progress_cb=None,
    performance_mode: str = "balanced",
):
    for idx, img in enumerate(images):
        img.info["_original_id"] = idx

    usable_width = max_width - 2 * margin

    from concurrent.futures import ThreadPoolExecutor
    from functools import partial

    _prep_fn = partial(
        _prepare_mask_variants,
        usable_width=usable_width,
        allow_rotate=allow_rotate,
        performance_mode=performance_mode,
    )

    with ThreadPoolExecutor(max_workers=min(len(images), 8)) as ex:
        all_variants = list(ex.map(_prep_fn, images))

    prepared = []
    for variants in all_variants:
        if not variants:
            continue
        primary = variants[0]
        prepared.append({
            "variants": variants,
            "sort_key": (
                primary.area,
                max(v.image.height for v in variants),
                max(v.image.width for v in variants),
            ),
        })

    prepared.sort(key=lambda item: item["sort_key"], reverse=True)

    total_alpha_area = sum(p["variants"][0].area for p in prepared)
    estimated_height = int(total_alpha_area / max(1, usable_width) * 1.6) + margin * 4
    initial_height = max(64, margin * 2 + 1, estimated_height)
    occupancy = np.zeros((initial_height, max_width), dtype=np.uint8)

    placed: list[PackedPiece] = []
    max_y_used = margin
    stamp_kernel = _build_stamp_kernel(spacing) if spacing > 0 else None
    total_count = len(prepared)
    scale_factor = 16 if performance_mode == "fast" else 8
    candidate_limit = 64 if performance_mode == "fast" else 192
    raster_search = performance_mode != "fast"

    for processed_count, piece in enumerate(prepared):
        if progress_cb:
            progress_cb(processed_count, total_count)

        best_choice = None
        max_occ_y = max_y_used + spacing

        # Compartilha o estado já colocado com a busca de fronteira, evitando varrer
        # o canvas inteiro para cada nova peça.
        setattr(_find_valid_positions_nfp, "_placed_cache", placed)

        for variant in piece["variants"]:
            img = variant.image
            mask = variant.mask
            w, h = img.size
            # search_h cobre todo o canvas já usado + uma peça abaixo.
            # Isso permite que o NFP ache espaços livres em TODAS as linhas
            # existentes, não apenas imediatamente abaixo de max_y_used.
            search_h = max_y_used + spacing + h + step
            occupancy = _ensure_height(occupancy, search_h)

            valid_positions = _find_valid_positions_nfp(
                occupancy,
                mask,
                max_width,
                margin,
                search_h,
                step=step,
                spacing=spacing,
                scale=scale_factor,
                top_k=candidate_limit,
                raster_search=raster_search,
            )

            for fx, fy in valid_positions:
                score = _score_candidate(mask, fx, fy, max_width, margin, max_y_used, variant.area)
                contact = _score_contact(occupancy, mask, fx, fy, spacing)
                angle_penalty = 0 if variant.angle in (0, 90, 270) else 1
                # Minimiza altura, maximiza contato entre peças
                final_score = (score[0], score[1], angle_penalty, -contact, score[2], score[3], score[4], score[5])

                if best_choice is None or final_score < best_choice["score"]:
                    best_choice = {
                        "image": img, "mask": mask,
                        "x": fx, "y": fy,
                        "score": final_score,
                    }

            # Refinamento local a partir do melhor candidato desta variante.
            if best_choice is not None and best_choice["image"] is img:
                rx, ry = _refine_candidate(
                    occupancy=occupancy,
                    mask=mask,
                    x=best_choice["x"],
                    y=best_choice["y"],
                    min_x=margin,
                    min_y=margin,
                    max_occ_y=max_occ_y + img.height + step,
                    max_width=max_width,
                )
                if (rx, ry) != (best_choice["x"], best_choice["y"]):
                    score = _score_candidate(mask, rx, ry, max_width, margin, max_y_used, variant.area)
                    contact = _score_contact(occupancy, mask, rx, ry, spacing)
                    angle_penalty = 0 if variant.angle in (0, 90, 270) else 1
                    refined_score = (score[0], score[1], angle_penalty, -contact, score[2], score[3], score[4], score[5])
                    if refined_score < best_choice["score"]:
                        best_choice = {
                            "image": img,
                            "mask": mask,
                            "x": rx,
                            "y": ry,
                            "score": refined_score,
                        }

        # Fallback: coloca abaixo de tudo se nenhuma posição foi encontrada
        if best_choice is None:
            fallback = piece["variants"][0]
            img = fallback.image
            mask = fallback.mask
            best_choice = {
                "image": img, "mask": mask,
                "x": margin, "y": max_y_used + spacing,
                "score": (1, img.height, 0, 0, -fallback.area, margin, max_y_used + spacing),
            }

        img = best_choice["image"]
        mask = best_choice["mask"]
        x = best_choice["x"]
        y = best_choice["y"]
        nudge_occ_y = min(max_y_used + spacing + img.height + step, occupancy.shape[0])
        # y_floor: impede que o nudge mova a peça ACIMA da linha onde ela foi
        # posicionada pelo NFP. Sem isso, uma peça alocada em y=1532 (linha 2)
        # subiria para y=20 (linha 1) onde não há espaço horizontal suficiente.
        y_floor = y if y > margin else margin
        x, y = _nudge_gravity_full(
            occupancy=occupancy,
            mask=mask,
            x=x, y=y,
            min_x=margin,
            min_y=max(margin, y_floor - 32),
            max_occ_y=nudge_occ_y,
        )

        placed.append(PackedPiece(
            image=img,
            mask=mask,
            x=x,
            y=y,
            w=img.width,
            h=img.height,
            area=int(mask.sum()),
        ))
        _stamp_reserved(occupancy, mask, x, y, spacing, margin, max_width, stamp_kernel)
        max_y_used = max(max_y_used, y + img.height)

    final_height = max_y_used + margin
    return [(piece.image, piece.x, piece.y) for piece in placed], max_width, final_height


def build_canvas(packed, width, height):
    canvas_arr = np.zeros((height, width, 4), dtype=np.uint8)
    canvas_arr[:, :, :3] = 255
    canvas_arr[:, :, 3] = 255

    for img, x, y in packed:
        img_arr = np.array(img) if img.mode == "RGBA" else np.array(img.convert("RGBA"))
        h_img, w_img = img_arr.shape[:2]
        y1 = min(y + h_img, height)
        x1 = min(x + w_img, width)
        h_fit = y1 - y
        w_fit = x1 - x
        if h_fit <= 0 or w_fit <= 0:
            continue

        src = img_arr[:h_fit, :w_fit]
        dst = canvas_arr[y:y1, x:x1]
        a = src[:, :, 3:4].astype(np.uint16)
        ia = np.uint16(255) - a
        blended = (src[:, :, :3].astype(np.uint16) * a + dst[:, :, :3].astype(np.uint16) * ia + 127) >> 8
        canvas_arr[y:y1, x:x1, :3] = blended.astype(np.uint8)
        canvas_arr[y:y1, x:x1, 3] = np.maximum(dst[:, :, 3], src[:, :, 3])

    return Image.fromarray(canvas_arr, "RGBA")

import time
import random
import numpy as np
import cv2
import numba
from PIL import Image, ImageDraw
from concurrent.futures import ThreadPoolExecutor
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ajudante_impressao.algorithms.packing import (
    _alpha_mask,
    _rotate_image,
    _build_stamp_kernel,
    _stamp_reserved,
    _collides_fast,
    _ensure_height,
    _find_row_transitions_fast,
    MaskVariant,
    PackedPiece,
    _prepare_mask_variants,
    _dedupe_candidates,
    _score_candidate,
    _mutate_order,
    _crossover_order,
)
from ajudante_impressao.scratch.test_optimized_packing import (
    _fast_score_contact,
    _collect_frontier_candidates_fast,
    _find_valid_positions_optimized,
    _refine_candidate_fast,
    _run_single_pass_fast,
)

def run_genetic_fast(
    prepared_base: list[list[MaskVariant]],
    max_width: int,
    spacing: int,
    margin: int,
    step: int,
    performance_mode: str,
):
    seed1 = sorted(
        prepared_base,
        key=lambda v_list: (v_list[0].area, max(v.image.height for v in v_list), max(v.image.width for v in v_list)),
        reverse=True,
    )
    seed2 = sorted(
        prepared_base,
        key=lambda v_list: (max(v.image.height for v in v_list), v_list[0].area, max(v.image.width for v in v_list)),
        reverse=True,
    )
    seed3 = sorted(
        prepared_base,
        key=lambda v_list: (v_list[0].image.width * v_list[0].image.height, v_list[0].area),
        reverse=True,
    )

    pop_size = 6 if performance_mode == "quality" else 4
    num_generations = 2 if performance_mode == "quality" else 1

    population = [seed1, seed2, seed3]
    while len(population) < pop_size:
        base_seed = random.choice([seed1, seed2, seed3])
        population.append(_mutate_order(base_seed))

    best_result = None

    def eval_individual(indiv):
        prepared_items = [{"variants": v_list} for v_list in indiv]
        return _run_single_pass_fast(
            prepared_items=prepared_items,
            max_width=max_width,
            spacing=spacing,
            margin=margin,
            step=step,
            performance_mode=performance_mode,
        )

    for gen in range(num_generations):
        with ThreadPoolExecutor(max_workers=min(len(population), 4)) as ex:
            results = list(ex.map(eval_individual, population))

        eval_pairs = list(zip(population, results))
        eval_pairs.sort(key=lambda pair: pair[1][2])

        if best_result is None or eval_pairs[0][1][2] < best_result[2]:
            best_result = eval_pairs[0][1]

        elite_count = max(2, len(population) // 2)
        elites = [pair[0] for pair in eval_pairs[:elite_count]]

        new_population = list(elites)
        while len(new_population) < pop_size:
            p1, p2 = random.sample(elites, 2)
            child = _crossover_order(p1, p2)
            if random.random() < 0.4:
                child = _mutate_order(child)
            new_population.append(child)

        population = new_population

    return best_result

def test_full():
    images = []
    for i in range(4):
        img = Image.new("RGBA", (2000, 2800), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pts = [(100, 100), (1900, 200), (1800, 2700), (200, 2600), (1000, 1400)]
        draw.polygon(pts, fill=((i*60)%255, 100, 200, 255))
        images.append(img)

    max_width = 4921
    spacing = 12
    margin = 20
    step = 8

    print("\n--- Testando Genetic Packing Completo no Modo BALANCED ---")
    variants_list = [_prepare_mask_variants(img, max_width - 2*margin, allow_rotate=True, performance_mode="balanced") for img in images]
    t0 = time.time()
    res = run_genetic_fast(
        prepared_base=variants_list,
        max_width=max_width,
        spacing=spacing,
        margin=margin,
        step=step,
        performance_mode="balanced",
    )
    t1 = time.time()
    print(f"Balanced Concluído! Altura: {res[2]}px em {t1-t0:.2f}s!")

    print("\n--- Testando Genetic Packing Completo no Modo QUALITY (com ângulos finos) ---")
    variants_q = [_prepare_mask_variants(img, max_width - 2*margin, allow_rotate=True, performance_mode="quality") for img in images]
    t0 = time.time()
    res_q = run_genetic_fast(
        prepared_base=variants_q,
        max_width=max_width,
        spacing=spacing,
        margin=margin,
        step=step,
        performance_mode="quality",
    )
    t1 = time.time()
    print(f"Quality Concluído! Altura: {res_q[2]}px em {t1-t0:.2f}s!")

if __name__ == "__main__":
    test_full()

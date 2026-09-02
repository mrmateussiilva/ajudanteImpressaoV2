import time
import numpy as np
import cv2
from PIL import Image, ImageDraw
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ajudante_impressao.algorithms.packing import (
    _prepare_mask_variants,
    _create_interlocking_pair,
    _find_valid_positions_nfp,
    _collides,
    _score_contact,
    _score_candidate,
    pack_images_masked,
    HAS_NUMBA,
)

print(f"HAS_NUMBA: {HAS_NUMBA}")

# Criar 4 imagens grandes como no mundo real (ex: 2000x2800 cada)
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

print("\n1. Testando _prepare_mask_variants para 4 imagens (balanced)...")
t0 = time.time()
variants_list = [_prepare_mask_variants(img, max_width - 2*margin, allow_rotate=True, performance_mode="balanced") for img in images]
print(f"   Tempo: {time.time() - t0:.3f}s, total variantes por imagem: {[len(v) for v in variants_list]}")

print("\n2. Testando _create_interlocking_pair...")
t0 = time.time()
_create_interlocking_pair(images[0], images[1], spacing, max_width - 2*margin)
print(f"   Tempo: {time.time() - t0:.3f}s")

print("\n3. Testando 1 busca de posições _find_valid_positions_nfp...")
m0 = variants_list[0][0].mask
occ = np.zeros((6000, max_width), dtype=np.uint8)
occ[0:m0.shape[0], 0:m0.shape[1]] = m0
m1 = variants_list[1][0].mask
t0 = time.time()
positions = _find_valid_positions_nfp(
    occupancy=occ,
    mask=m1,
    max_width=max_width,
    margin=margin,
    search_h=5800,
    step=step,
    spacing=spacing,
    scale=8,
    top_k=192,
    raster_search=True
)
print(f"   Tempo: {time.time() - t0:.3f}s, posições encontradas: {len(positions)}")

print("\n4. Testando _score_contact para posições...")
t0 = time.time()
for x, y in positions:
    _score_contact(occ, m1, x, y, spacing, margin, max_width)
print(f"   Tempo: {time.time() - t0:.3f}s")

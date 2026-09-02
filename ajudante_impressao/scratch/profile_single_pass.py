import time
import cProfile
import pstats
import io
from PIL import Image, ImageDraw
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ajudante_impressao.algorithms.packing import _prepare_mask_variants, _run_single_pass

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

print("Preparando variantes...")
variants_list = [_prepare_mask_variants(img, max_width - 2*margin, allow_rotate=True, performance_mode="balanced") for img in images]
prepared_items = [{"variants": v_list} for v_list in variants_list]

print("Executando 1 single pass com cProfile...")
pr = cProfile.Profile()
pr.enable()
t0 = time.time()
result = _run_single_pass(
    prepared_items=prepared_items,
    max_width=max_width,
    spacing=spacing,
    margin=margin,
    step=step,
    performance_mode="balanced",
)
t1 = time.time()
pr.disable()

print(f"Passo concluído em {t1-t0:.3f}s! Altura: {result[2]}")
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumtime')
ps.print_stats(25)
print(s.getvalue())

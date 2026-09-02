import os
import sys
import time
from PIL import Image, ImageDraw

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ajudante_impressao.algorithms.packing import pack_images_masked

def generate_asymmetric_pairs():
    images = []
    # 4 copies of an L-shaped / staircase figure
    for i in range(4):
        w, h = 300, 400
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = (255, (i * 60) % 256, 100, 255)
        # L-shape: full left side, bottom half right side
        draw.rectangle((0, 0, 150, 400), fill=color)
        draw.rectangle((150, 200, 300, 400), fill=color)
        images.append(img)
    return images

def test_interlocking():
    images = generate_asymmetric_pairs()
    max_width = 1200
    spacing = 10
    margin = 10
    step = 8

    print("\n--- Testando Pareamento Invertido (Interlocking 180°) ---")
    t0 = time.time()
    packed, w, h, useful = pack_images_masked(
        images, max_width, spacing, margin, step, allow_rotate=True, performance_mode="balanced"
    )
    t1 = time.time()
    yield_pct = (useful / (w * h)) * 100.0
    print(f"Resultado: Altura={h}px, Aproveitamento={yield_pct:.1f}%, Tempo={t1-t0:.3f}s")
    for idx, (img, x, y) in enumerate(packed):
        print(f"Bloco {idx}: size={img.size}, pos=({x}, {y})")

if __name__ == "__main__":
    test_interlocking()

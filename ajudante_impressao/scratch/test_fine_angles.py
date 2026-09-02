import os
import sys
import time
from PIL import Image, ImageDraw

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ajudante_impressao.algorithms.packing import pack_images_masked

def generate_diagonal_mock_images():
    images = []
    # Create triangle / diagonal shapes
    for i in range(6):
        w, h = 400, 400
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        color = ((i * 50) % 256, (i * 100) % 256, 200, 255)
        # Draw a diagonal triangle
        draw.polygon([(10, 10), (w - 10, h // 2), (10, h - 10)], fill=color)
        images.append(img)
    return images

def test_fine_angles():
    images = generate_diagonal_mock_images()
    max_width = 1200
    spacing = 10
    margin = 10
    step = 8

    print("\n--- Testando Modo Balanced (0, 90, 270) ---")
    t0 = time.time()
    packed, w, h, useful = pack_images_masked(
        images, max_width, spacing, margin, step, allow_rotate=True, performance_mode="balanced"
    )
    t1 = time.time()
    print(f"Balanced: Altura={h}px, Tempo={t1-t0:.3f}s")

    print("\n--- Testando Modo Quality (Ângulos Finos) ---")
    t2 = time.time()
    packed_q, w_q, h_q, useful_q = pack_images_masked(
        images, max_width, spacing, margin, step, allow_rotate=True, performance_mode="quality"
    )
    t3 = time.time()
    print(f"Quality:  Altura={h_q}px, Tempo={t3-t2:.3f}s")

if __name__ == "__main__":
    test_fine_angles()

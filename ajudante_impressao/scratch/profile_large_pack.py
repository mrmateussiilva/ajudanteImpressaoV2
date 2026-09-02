import time
from PIL import Image, ImageDraw
import cProfile
import pstats
import io
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ajudante_impressao.algorithms.packing import pack_images_masked

def profile_test():
    # 4 imagens realistas: rolo de 125cm (4921 px), 4 imagens de ~2000x3000px
    print("Gerando 4 imagens de teste grandes (2000x3000px)...")
    images = []
    for i in range(4):
        img = Image.new("RGBA", (2000, 2800), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Forma complexa (polígono irregular)
        pts = [(100, 100), (1900, 200), (1800, 2700), (200, 2600), (1000, 1400)]
        draw.polygon(pts, fill=((i*60)%255, 100, 200, 255))
        images.append(img)

    max_width = 4921 # 125 cm @ 100 DPI
    spacing = 12     # 0.3 cm
    margin = 20      # 0.5 cm
    step = 8

    print("Iniciando perfilamento do pack_images_masked (balanced)...")
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.time()
    packed, w, h, useful = pack_images_masked(
        images, max_width, spacing, margin, step, allow_rotate=True, performance_mode="balanced"
    )
    t1 = time.time()
    pr.disable()

    print(f"Finalizado em {t1-t0:.2f}s! Altura: {h}px")
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumtime')
    ps.print_stats(30)
    print(s.getvalue())

if __name__ == "__main__":
    profile_test()

import os
import sys
from PIL import Image

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ajudante_impressao.algorithms.packing import pack_images_masked

def test_portrait_rotation():
    img_wide = Image.new("RGBA", (800, 400), (255, 0, 0, 255))
    img_tall = Image.new("RGBA", (200, 600), (0, 0, 255, 255))
    
    max_width = 900
    spacing = 10
    margin = 10
    step = 8
    
    packed, w, h, useful_area = pack_images_masked(
        [img_wide, img_tall],
        max_width=max_width,
        spacing=spacing,
        margin=margin,
        step=step,
        allow_rotate=True,
        performance_mode="balanced"
    )
    
    print(f"Final height: {h}px")
    for idx, (img, x, y) in enumerate(packed):
        print(f"Piece {idx}: size={img.size}, pos=({x}, {y})")

if __name__ == "__main__":
    test_portrait_rotation()

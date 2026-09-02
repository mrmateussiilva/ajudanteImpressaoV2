import os
import time
import numpy as np
from PIL import Image, ImageDraw

# Adicionar o diretório raiz ao path para poder importar o pacote ajudante_impressao
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ajudante_impressao.algorithms.packing import pack_images_masked, build_canvas

def generate_mock_images():
    print("Gerando imagens de teste...")
    images = []
    
    sizes = [
        (300, 300, "circle"),
        (250, 400, "ellipse"),
        (450, 150, "rect"),
        (200, 200, "circle"),
        (150, 350, "ellipse"),
        (500, 250, "rect"),
        (100, 100, "circle"),
        (80, 80, "circle"),
        (120, 200, "ellipse"),
        (350, 350, "circle"),
        (200, 400, "rect"),
        (150, 150, "circle")
    ]
    
    for i, (w, h, shape) in enumerate(sizes):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        color = ((i * 45) % 256, (i * 90) % 256, (i * 135) % 256, 255)
        if shape == "circle":
            r = min(w, h) // 2 - 5
            draw.ellipse((w//2 - r, h//2 - r, w//2 + r, h//2 + r), fill=color)
        elif shape == "ellipse":
            draw.ellipse((5, 5, w - 5, h - 5), fill=color)
        else: # rect
            draw.rectangle((5, 5, w - 5, h - 5), fill=color)
            
        images.append(img)
        
    return images

def test_algorithm(images, name, perf_mode):
    print(f"\n--- Testando algoritmo: {name} ({perf_mode}) ---")
    start_time = time.time()
    
    max_width = 1200
    spacing = 10
    margin = 20
    step = 8
    
    packed, w, h, useful_area = pack_images_masked(images, max_width, spacing, margin, step, allow_rotate=True, performance_mode=perf_mode)
    yield_pct = (useful_area / (w * h)) * 100.0
        
    elapsed = time.time() - start_time
    print(f"Resultado {name}:")
    print(f"  Imagens posicionadas: {len(packed)} de {len(images)}")
    print(f"  Largura final: {w}px")
    print(f"  Altura final: {h}px")
    print(f"  Tempo decorrido: {elapsed:.3f}s")
    
    if packed:
        canvas = build_canvas(packed, w, h)
        output_name = f"test_result_{perf_mode}.png"
        output_path = os.path.join(os.path.dirname(__file__), output_name)
        canvas.save(output_path)
        print(f"  Imagem de resultado salva em: {output_name}")
        
    return h, elapsed

def main():
    images = generate_mock_images()
    
    h_fast, t_fast = test_algorithm(images, "Masked Fast", "fast")
    h_balanced, t_balanced = test_algorithm(images, "Masked Balanced", "balanced")
    
    print("\n" + "="*40)
    print("Resumo do Benchmark Atual:")
    print(f"  Fast     - Altura: {h_fast}px, Tempo: {t_fast:.3f}s")
    print(f"  Balanced - Altura: {h_balanced}px, Tempo: {t_balanced:.3f}s")
    print("="*40)

if __name__ == "__main__":
    main()

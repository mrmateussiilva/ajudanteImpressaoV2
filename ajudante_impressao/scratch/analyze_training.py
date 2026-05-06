import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

TRAIN_DIR = Path(r"Z:\IMPRESSÃO DE TOTENS\treinamentos")

def analyze_folder(folder_path):
    print(f"Analyzing {folder_path.name}...")
    results = []
    for file in folder_path.iterdir():
        if file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
            try:
                # Load image
                with Image.open(file) as pil_img:
                    img_np = np.array(pil_img.convert('RGB'))
                    # Convert RGB to BGR for opencv compatibility if needed
                    img = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                
                h, w = img.shape[:2]
                aspect_ratio = w / h
                
                # Color histogram
                hist = cv2.calcHist([img], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                hist = cv2.normalize(hist, hist).flatten()
                
                # Simple stats
                mean_color = cv2.mean(img)[:3]
                
                results.append({
                    "name": file.name,
                    "aspect_ratio": aspect_ratio,
                    "mean_color": mean_color,
                    "hist": hist
                })
            except Exception as e:
                print(f"Error analyzing {file.name}: {e}")
    return results

if __name__ == "__main__":
    if not TRAIN_DIR.exists():
        print(f"Directory {TRAIN_DIR} not found.")
    else:
        for subfolder in TRAIN_DIR.iterdir():
            if subfolder.is_dir():
                data = analyze_folder(subfolder)
                print(f"Found {len(data)} images in {subfolder.name}")
                if data:
                    avg_ar = sum(d['aspect_ratio'] for d in data) / len(data)
                    print(f"  Average Aspect Ratio: {avg_ar:.2f}")
                    avg_color = np.mean([d['mean_color'] for d in data], axis=0)
                    print(f"  Average Mean Color (BGR): {avg_color}")

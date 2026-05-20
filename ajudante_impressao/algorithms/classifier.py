import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from typing import Optional, Dict, List

class ImageClassifier:
    def __init__(self, training_dir: str, name: str = "Classifier"):
        self.training_dir = Path(training_dir)
        self.name = name
        self.features = {} # Dict[category, List[Dict]]
        self.category_names = []
        self.trained = False
        
    def _extract_features(self, image_path_or_pil: Path | Image.Image) -> Optional[Dict]:
        """Extracts features (Aspect Ratio, Color Histogram, Sharpness) from an image."""
        try:
            if isinstance(image_path_or_pil, Path):
                with Image.open(image_path_or_pil) as pil_img:
                    img_np = np.array(pil_img.convert('RGB'))
            else:
                img_np = np.array(image_path_or_pil.convert('RGB'))
            
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            
            h, w = img_bgr.shape[:2]
            aspect_ratio = w / h
            
            # Sharpness: Laplacian variance
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            # Color histogram
            hist = cv2.calcHist([img_bgr], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            
            return {
                "aspect_ratio": aspect_ratio,
                "sharpness": sharpness,
                "hist": hist,
                "size": (w, h)
            }
        except Exception:
            return None

    def train(self):
        """Loads features from the training directory."""
        if not self.training_dir.exists():
            print(f"[{self.name}] Training dir {self.training_dir} not found.")
            return False
        
        # Re-scan for categories
        self.category_names = [d.name for d in self.training_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        
        self.features = {}
        total_files = 0
        for category in self.category_names:
            cat_path = self.training_dir / category
            self.features[category] = []
            for file in cat_path.iterdir():
                if file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                    feat = self._extract_features(file)
                    if feat:
                        self.features[category].append(feat)
                        total_files += 1
        
        self.trained = True
        print(f"[{self.name}] Trained on {total_files} images across {len(self.category_names)} categories.")
        return True

    def classify(self, image: Image.Image, filename: Optional[str] = None) -> str:
        """Classifies an image using simple KNN (k=3) approach, weighing the filename if provided."""
        if not self.trained:
            if not self.train():
                return "N/A"

        new_feat = self._extract_features(image)
        if not new_feat:
            return "Erro"

        distances = []
        for category, cat_feats in self.features.items():
            # Name boost: if category name is in the filename, we give it a massive advantage
            name_boost = 1.0
            if filename:
                cat_lower = category.lower()
                file_lower = filename.lower()
                # Check for direct inclusion or with common separators
                if cat_lower in file_lower:
                    name_boost = 0.05 # 95% distance reduction

            for feat in cat_feats:
                # Calculate distances
                ar_dist = abs(new_feat["aspect_ratio"] - feat["aspect_ratio"])
                hist_dist = cv2.compareHist(new_feat["hist"], feat["hist"], cv2.HISTCMP_CHISQR)
                
                # Sharpness distance (log scale because it varies wildly)
                s1 = np.log1p(new_feat["sharpness"])
                s2 = np.log1p(feat["sharpness"])
                sharp_dist = abs(s1 - s2)
                
                # Weighted distance (Heuristic)
                # For quality, sharpness is more important than for production type
                if "qualidade" in str(self.training_dir).lower():
                    total_dist = (ar_dist * 5) + (hist_dist / 1000) + (sharp_dist * 20)
                else:
                    total_dist = (ar_dist * 15) + (hist_dist / 800) + (sharp_dist * 5)
                
                # Apply filename boost
                final_dist = total_dist * name_boost
                distances.append((final_dist, category))
        
        if not distances:
            return "Sem dados"
            
        distances.sort(key=lambda x: x[0])
        
        # Take top 3 neighbors and vote
        votes = {}
        for i in range(min(3, len(distances))):
            cat = distances[i][1]
            votes[cat] = votes.get(cat, 0) + 1
            
        winner = max(votes, key=votes.get)
        return winner

# Global instances
_prod_classifier = None
_quality_classifier = None

def get_prod_classifier():
    global _prod_classifier
    if _prod_classifier is None:
        _prod_classifier = ImageClassifier(r"Z:\IMPRESSÃO DE TOTENS\treinamentos", "Producao")
        _prod_classifier.train()
    return _prod_classifier

def get_quality_classifier():
    global _quality_classifier
    if _quality_classifier is None:
        _quality_classifier = ImageClassifier(r"Z:\IMPRESSÃO DE TOTENS\qualidade", "Qualidade")
        _quality_classifier.train()
    return _quality_classifier

# Para manter compatibilidade com código existente
def get_classifier():
    return get_prod_classifier()

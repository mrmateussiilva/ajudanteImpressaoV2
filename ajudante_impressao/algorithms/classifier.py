import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from typing import Optional, Dict, List

class ImageClassifier:
    def __init__(self, training_dir: str = r"Z:\IMPRESSÃO DE TOTENS\treinamentos"):
        self.training_dir = Path(training_dir)
        self.features = {} # Dict[category, List[Dict]]
        self.category_names = []
        if self.training_dir.exists():
            self.category_names = [d.name for d in self.training_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        self.trained = False

    def train(self):
        """Loads features from the training directory."""
        if not self.training_dir.exists():
            return False
        
        # Re-scan for categories in case new folders were added
        self.category_names = [d.name for d in self.training_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        
        self.features = {}
        for category in self.category_names:
            cat_path = self.training_dir / category
            if not cat_path.exists():
                continue
            
            self.features[category] = []
            for file in cat_path.iterdir():
                if file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                    feat = self._extract_features(file)
                    if feat:
                        self.features[category].append(feat)
        
        self.trained = True
        return True

    def _extract_features(self, image_path_or_pil: Path | Image.Image) -> Optional[Dict]:
        """Extracts features (Aspect Ratio, Color Histogram) from an image."""
        try:
            if isinstance(image_path_or_pil, Path):
                with Image.open(image_path_or_pil) as pil_img:
                    img_np = np.array(pil_img.convert('RGB'))
            else:
                img_np = np.array(image_path_or_pil.convert('RGB'))
            
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            h, w = img_bgr.shape[:2]
            aspect_ratio = w / h
            
            # Color histogram
            hist = cv2.calcHist([img_bgr], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            
            return {
                "aspect_ratio": aspect_ratio,
                "hist": hist
            }
        except Exception:
            return None

    def classify(self, image: Image.Image) -> str:
        """Classifies an image using simple KNN (k=3) approach."""
        if not self.trained:
            if not self.train():
                return "Desconhecido"

        new_feat = self._extract_features(image)
        if not new_feat:
            return "Erro ao processar"

        distances = []
        for category, cat_feats in self.features.items():
            for feat in cat_feats:
                # Calculate distance
                # We give more weight to AR or combine them
                ar_dist = abs(new_feat["aspect_ratio"] - feat["aspect_ratio"])
                hist_dist = cv2.compareHist(new_feat["hist"], feat["hist"], cv2.HISTCMP_CHISQR)
                
                # Normalize distances? Hist dist can be large.
                # Simple heuristic:
                total_dist = ar_dist * 10 + (hist_dist / 1000)
                distances.append((total_dist, category))
        
        if not distances:
            return "Sem dados de treino"
            
        distances.sort(key=lambda x: x[0])
        
        # Take top 3 neighbors and vote
        votes = {}
        for i in range(min(3, len(distances))):
            cat = distances[i][1]
            votes[cat] = votes.get(cat, 0) + 1
            
        winner = max(votes, key=votes.get)
        return winner

# Global instance
_classifier = None

def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = ImageClassifier()
        _classifier.train()
    return _classifier

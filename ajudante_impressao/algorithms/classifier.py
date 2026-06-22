import os
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from typing import Optional, Dict, List

import hashlib
import json

def _resolve_training_dir(default_windows_path: str, local_dirname: str) -> Path:
    # 1. Se estiver no Windows e o caminho Z:\ existir, usa ele
    win_path = Path(default_windows_path)
    if os.name == 'nt' and win_path.exists():
        return win_path
        
    # 2. Caminhos conhecidos no Linux (ambiente do usuário)
    user_home = Path.home()
    linux_paths = [
        Path("/home/mateus/Documentos/Projects/Pessoais/impressor") / local_dirname,
        user_home / "Documentos/Projects/Pessoais/impressor" / local_dirname,
        Path(".") / local_dirname,
    ]
    for p in linux_paths:
        if p.exists():
            return p
            
    # 3. Fallback no diretório do projeto ou home
    fallback = Path.home() / ".ajudante_impressao" / local_dirname
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class ImageClassifier:
    def __init__(self, training_dir: Path | str, name: str = "Classifier"):
        self.training_dir = Path(training_dir)
        self.name = name
        self.features = {} # Dict[category, List[Dict]]
        self.category_names = []
        self.trained = False
        self.cache_file = Path.home() / ".ajudante_impressao" / f"cache_{self.name.lower()}.json"
        
    def _get_training_state(self) -> str:
        """Retorna uma string MD5 única que representa o estado atual da pasta de treinamento (arquivos e modificações)."""
        if not self.training_dir.exists():
            return ""
        
        state_parts = []
        try:
            # Coleta todas as pastas e arquivos na ordem correta
            for cat_dir in sorted(self.training_dir.iterdir()):
                if cat_dir.is_dir() and not cat_dir.name.startswith('.'):
                    state_parts.append(f"cat:{cat_dir.name}")
                    for file in sorted(cat_dir.iterdir()):
                        if file.is_file() and file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                            mtime = file.stat().st_mtime
                            size = file.stat().st_size
                            state_parts.append(f"{file.name}:{mtime}:{size}")
        except Exception:
            return ""
            
        state_str = "|".join(state_parts)
        return hashlib.md5(state_str.encode('utf-8')).hexdigest()

    def _load_from_cache(self) -> bool:
        """Tenta carregar o classificador treinado a partir do cache JSON local."""
        try:
            if not self.cache_file.exists():
                return False
                
            current_hash = self._get_training_state()
            if not current_hash:
                return False
                
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if data.get("state_hash") != current_hash:
                return False  # O diretório de treinamento foi modificado
                
            self.category_names = data.get("category_names", [])
            self.features = {}
            total_files = 0
            for cat, feats in data.get("features", {}).items():
                self.features[cat] = []
                for feat in feats:
                    self.features[cat].append({
                        "aspect_ratio": feat["aspect_ratio"],
                        "sharpness": feat["sharpness"],
                        "hist": np.array(feat["hist"], dtype=np.float32),
                        "size": tuple(feat["size"])
                    })
                    total_files += 1
                    
            self.trained = True
            print(f"[{self.name}] Carregado do cache com sucesso: {total_files} imagens em {len(self.category_names)} categorias.")
            return True
        except Exception as e:
            print(f"[{self.name}] Erro ao carregar cache: {e}")
            return False

    def _save_to_cache(self) -> None:
        """Salva as features extraídas no arquivo de cache JSON local."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            serializable_features = {}
            for cat, feats in self.features.items():
                serializable_features[cat] = []
                for feat in feats:
                    serializable_features[cat].append({
                        "aspect_ratio": feat["aspect_ratio"],
                        "sharpness": feat["sharpness"],
                        "hist": feat["hist"].tolist(),
                        "size": list(feat["size"])
                    })
                    
            data = {
                "state_hash": self._get_training_state(),
                "category_names": self.category_names,
                "features": serializable_features
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"[{self.name}] Cache salvo em: {self.cache_file.name}")
        except Exception as e:
            print(f"[{self.name}] Erro ao salvar cache: {e}")

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
        """Loads features from the training directory, using local cache if available."""
        if not self.training_dir.exists():
            print(f"[{self.name}] Pasta de treinamento não encontrada: {self.training_dir}")
            return False
            
        # Tenta carregar do cache antes de treinar
        if self._load_from_cache():
            return True
            
        print(f"[{self.name}] Treinando a partir do diretório: {self.training_dir} ...")
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
        print(f"[{self.name}] Treinamento finalizado. {total_files} imagens mapeadas.")
        
        # Salva o novo cache
        self._save_to_cache()
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
        training_path = _resolve_training_dir(r"Z:\IMPRESSÃO DE TOTENS\treinamentos", "treinamentos")
        _prod_classifier = ImageClassifier(training_path, "Producao")
        _prod_classifier.train()
    return _prod_classifier

def get_quality_classifier():
    global _quality_classifier
    if _quality_classifier is None:
        training_path = _resolve_training_dir(r"Z:\IMPRESSÃO DE TOTENS\qualidade", "qualidade")
        _quality_classifier = ImageClassifier(training_path, "Qualidade")
        _quality_classifier.train()
    return _quality_classifier

# Para manter compatibilidade com código existente
def get_classifier():
    return get_prod_classifier()


def feed_back_to_training(
    folder: Path | str,
    filename: str,
    threshold: int,
    category: Optional[str] = None,
    quality: Optional[str] = None,
):
    """Copia a imagem limpa e cortada do cache para a pasta de treinamentos com a categoria/qualidade corrigida."""
    import shutil
    from .image_ops import _get_cache_key
    
    file_path = Path(folder) / filename
    if not file_path.exists():
        return
        
    try:
        key = _get_cache_key(file_path, threshold)
        cache_dir = Path(folder) / ".ajudante_cache"
        cache_png = cache_dir / f"{key}.png"
        if not cache_png.exists():
            return
            
        # 1. Producao feedback
        if category and category not in ("N/A", "Erro", "Sem dados"):
            prod_cls = get_prod_classifier()
            dest_dir = prod_cls.training_dir / category
            if dest_dir.parent.exists():
                dest_dir.mkdir(parents=True, exist_ok=True)
                
                # Remove from other folders to avoid duplicates
                for other_cat in prod_cls.category_names:
                    if other_cat != category:
                        for ext in (".png", ".jpg", ".jpeg"):
                            old_file = prod_cls.training_dir / other_cat / f"{file_path.stem}{ext}"
                            if old_file.exists():
                                old_file.unlink()
                            
                dest_file = dest_dir / f"{file_path.stem}.png"
                shutil.copy2(cache_png, dest_file)
                print(f"[Classifier] Realimentado em Produção/{category}: {dest_file.name}")
                
        # 2. Qualidade feedback
        if quality and quality not in ("N/A", "Erro", "Sem dados"):
            qual_cls = get_quality_classifier()
            dest_dir = qual_cls.training_dir / quality
            if dest_dir.parent.exists():
                dest_dir.mkdir(parents=True, exist_ok=True)
                
                for other_qual in qual_cls.category_names:
                    if other_qual != quality:
                        for ext in (".png", ".jpg", ".jpeg"):
                            old_file = qual_cls.training_dir / other_qual / f"{file_path.stem}{ext}"
                            if old_file.exists():
                                old_file.unlink()
                            
                dest_file = dest_dir / f"{file_path.stem}.png"
                shutil.copy2(cache_png, dest_file)
                print(f"[Classifier] Realimentado em Qualidade/{quality}: {dest_file.name}")
                
    except Exception as e:
        print(f"[Classifier] Erro ao realimentar treino: {e}")

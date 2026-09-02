from __future__ import annotations

import os
import re
import json
import shutil
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image


@dataclass
class ClassificationResult:
    category: str
    confidence_pct: float
    alternatives: List[Tuple[str, float]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    rule_matched: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.category} ({self.confidence_pct:.1f}%)"


def _get_app_config_dir() -> Path:
    config_dir = Path.home() / ".ajudante_impressao"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _resolve_training_dir(default_windows_path: str, local_dirname: str) -> Path:
    win_path = Path(default_windows_path)
    if os.name == "nt" and win_path.exists():
        return win_path

    user_home = Path.home()
    linux_paths = [
        Path("/home/mateus/Documentos/Projects/Pessoais/impressor") / local_dirname,
        user_home / "Documentos/Projects/Pessoais/impressor" / local_dirname,
        Path(".") / local_dirname,
    ]
    for p in linux_paths:
        if p.exists():
            return p

    fallback = _get_app_config_dir() / local_dirname
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class KeywordRulesEngine:
    """Motor de regras contextuais por palavras-chave e regex no nome do arquivo."""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or (_get_app_config_dir() / "rules_keywords.json")
        self.rules: Dict[str, List[str]] = self._load_rules()

    def _default_rules(self) -> Dict[str, List[str]]:
        return {
            "3mm sp": ["3mm sp", "3mm_sp", "3mm-sp", "3mm", "sp", "sem pe", "sem_pe", "totem 3mm"],
            "6mm cp": ["6mm cp", "6mm_cp", "6mm-cp", "6mm", "cp", "com pe", "com_pe", "totem 6mm"],
            "poliondas": ["polionda", "poliondas", "placa polionda", "canelado"],
            "adesivo": ["adesivo", "vinil", "rotulo", "etiqueta", "sticker"],
            "lona": ["lona", "banner", "faixa", "backlight", "frontlight"],
        }

    def _load_rules(self) -> Dict[str, List[str]]:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"[RulesEngine] Erro ao carregar regras: {e}")
        defaults = self._default_rules()
        self.save_rules(defaults)
        return defaults

    def save_rules(self, rules: Optional[Dict[str, List[str]]] = None) -> None:
        if rules is not None:
            self.rules = rules
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[RulesEngine] Erro ao salvar regras: {e}")

    def match(self, filename: str) -> Optional[Tuple[str, float, str]]:
        """Verifica se o nome do arquivo corresponde explicitamente a alguma regra.
        Retorna (categoria, confiança_boost, regra_casada) ou None."""
        if not filename:
            return None

        # Limpar nome removendo extensão e normalizando
        name_clean = Path(filename).stem.lower()
        # Normalizar separadores
        name_normalized = re.sub(r"[\-_\.\s]+", " ", name_clean).strip()
        tokens = set(name_normalized.split())

        best_match = None
        highest_score = 0.0

        for category, keywords in self.rules.items():
            for kw in keywords:
                kw_norm = re.sub(r"[\-_\.\s]+", " ", kw.lower()).strip()
                kw_tokens = kw_norm.split()

                # Caso 1: Expressão multi-palavras exata encontrada na frase
                if len(kw_tokens) > 1 and kw_norm in name_normalized:
                    score = 0.98 + (len(kw_norm) * 0.001)
                    if score > highest_score:
                        highest_score = score
                        best_match = (category, min(0.99, score), kw)

                # Caso 2: Token único correspondência exata
                elif len(kw_tokens) == 1 and kw_norm in tokens:
                    score = 0.92 if len(kw_norm) <= 2 else 0.96
                    if score > highest_score:
                        highest_score = score
                        best_match = (category, score, kw)

                # Caso 3: Substring contida
                elif kw_norm in name_normalized and len(kw_norm) >= 3:
                    score = 0.85
                    if score > highest_score:
                        highest_score = score
                        best_match = (category, score, kw)

        return best_match


class ImageClassifier:
    """Classificador híbrido de artes gráficas com extração multi-feature,
    aprendizado incremental em tempo real e cálculo de confiança estatística."""

    def __init__(self, training_dir: Path | str, name: str = "Classifier"):
        self.training_dir = Path(training_dir)
        self.name = name
        self.features: Dict[str, List[Dict[str, Any]]] = {}
        self.category_names: List[str] = []
        self.trained = False
        self.cache_file = _get_app_config_dir() / f"cache_{self.name.lower()}.json"
        self.rules_engine = KeywordRulesEngine()

    def _load_from_cache(self) -> bool:
        """Carrega as features a partir do cache JSON local instantaneamente."""
        try:
            if not self.cache_file.exists():
                return False

            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            features_dict = data.get("features", {})
            if not features_dict:
                return False

            self.category_names = data.get("category_names", list(features_dict.keys()))
            self.features = {}
            total_files = 0

            for cat, feats in features_dict.items():
                self.features[cat] = []
                for feat in feats:
                    hist_arr = np.array(feat.get("hist", []), dtype=np.float32)
                    self.features[cat].append({
                        "aspect_ratio": float(feat.get("aspect_ratio", 1.0)),
                        "fill_ratio": float(feat.get("fill_ratio", 1.0)),
                        "contour_complexity": float(feat.get("contour_complexity", 1.0)),
                        "edge_density": float(feat.get("edge_density", 0.0)),
                        "sharpness_tenengrad": float(feat.get("sharpness_tenengrad", 0.0)),
                        "sharpness_laplacian_norm": float(feat.get("sharpness_laplacian_norm", 0.0)),
                        "hist": hist_arr,
                        "size": tuple(feat.get("size", (100, 100))),
                        "width_cm": float(feat.get("width_cm", 0.0)),
                        "height_cm": float(feat.get("height_cm", 0.0)),
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
                        "aspect_ratio": float(feat["aspect_ratio"]),
                        "fill_ratio": float(feat.get("fill_ratio", 1.0)),
                        "contour_complexity": float(feat.get("contour_complexity", 1.0)),
                        "edge_density": float(feat.get("edge_density", 0.0)),
                        "sharpness_tenengrad": float(feat.get("sharpness_tenengrad", 0.0)),
                        "sharpness_laplacian_norm": float(feat.get("sharpness_laplacian_norm", 0.0)),
                        "hist": feat["hist"].tolist() if isinstance(feat["hist"], np.ndarray) else feat["hist"],
                        "size": list(feat["size"]),
                        "width_cm": float(feat.get("width_cm", 0.0)),
                        "height_cm": float(feat.get("height_cm", 0.0)),
                    })

            data = {
                "category_names": self.category_names,
                "features": serializable_features,
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[{self.name}] Erro ao salvar cache: {e}")

    def extract_features(self, image_path_or_pil: Path | Image.Image) -> Optional[Dict[str, Any]]:
        """Extrai vetor de features robusto e normalizado."""
        try:
            if isinstance(image_path_or_pil, (Path, str)):
                with Image.open(image_path_or_pil) as pil_img:
                    pil_img = pil_img.convert("RGBA")
                    w_orig, h_orig = pil_img.size
                    img_rgba = pil_img.copy()
            else:
                img_rgba = image_path_or_pil.convert("RGBA")
                w_orig, h_orig = img_rgba.size

            aspect_ratio = w_orig / max(1, h_orig)
            width_cm = (w_orig / 100.0) * 2.54
            height_cm = (h_orig / 100.0) * 2.54

            # Redimensionamento rápido para análise sem perder proporções
            thumb_size = 400
            scale = min(1.0, thumb_size / max(w_orig, h_orig))
            analysis_w = max(16, int(w_orig * scale))
            analysis_h = max(16, int(h_orig * scale))
            img_resized = img_rgba.resize((analysis_w, analysis_h), Image.Resampling.BILINEAR)

            arr_rgba = np.array(img_resized)
            arr_rgb = arr_rgba[:, :, :3]
            alpha = arr_rgba[:, :, 3]

            # 1. Fill Ratio (Área real de pixels úteis vs Bounding Box)
            non_zero_alpha = np.count_nonzero(alpha > 20)
            total_pixels = analysis_w * analysis_h
            fill_ratio = float(non_zero_alpha / max(1, total_pixels))

            # 2. Complexidade de Contorno (Perímetro / sqrt(Área))
            mask = (alpha > 20).astype(np.uint8) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                main_contour = max(contours, key=cv2.contourArea)
                perimeter = cv2.arcLength(main_contour, True)
                area = cv2.contourArea(main_contour)
                contour_complexity = float(perimeter / (np.sqrt(max(1.0, area)) * 2.0))
            else:
                contour_complexity = 1.0

            # 3. Conversão para Grayscale e BGR
            img_bgr = cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

            # 4. Densidade de Bordas via Canny
            edges = cv2.Canny(gray, 50, 150)
            edge_density = float(np.count_nonzero(edges) / max(1, total_pixels))

            # 5. Nitidez Tenengrad (Gradiente Sobel)
            sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            grad_mag = np.sqrt(sobel_x**2 + sobel_y**2)
            sharpness_tenengrad = float(np.mean(grad_mag))

            # 6. Nitidez Laplaciana Normalizada por Contraste
            lap = cv2.Laplacian(gray, cv2.CV_64F)
            lap_var = float(lap.var())
            contrast = float(np.std(gray))
            sharpness_laplacian_norm = float(lap_var / max(1.0, contrast))

            # 7. Histograma 3D de Cores HSV (8x8x8 normalizado)
            img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([img_hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()

            return {
                "aspect_ratio": aspect_ratio,
                "fill_ratio": fill_ratio,
                "contour_complexity": contour_complexity,
                "edge_density": edge_density,
                "sharpness_tenengrad": sharpness_tenengrad,
                "sharpness_laplacian_norm": sharpness_laplacian_norm,
                "hist": hist,
                "size": (w_orig, h_orig),
                "width_cm": width_cm,
                "height_cm": height_cm,
            }
        except Exception as exc:
            print(f"[{self.name}] Erro ao extrair features: {exc}")
            return None

    def train(self, force: bool = False) -> bool:
        """Carrega do cache ou lê a pasta de treinamento."""
        if not force and self._load_from_cache():
            return True

        if not self.training_dir.exists():
            print(f"[{self.name}] Pasta de treinamento não encontrada: {self.training_dir}")
            return False

        print(f"[{self.name}] Iniciando treinamento a partir de: {self.training_dir} ...")
        try:
            self.category_names = [
                d.name for d in self.training_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
        except Exception as e:
            print(f"[{self.name}] Erro ao listar diretórios: {e}")
            return False

        self.features = {}
        total_files = 0

        for category in self.category_names:
            cat_path = self.training_dir / category
            self.features[category] = []
            try:
                files = [
                    f for f in cat_path.iterdir()
                    if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
                ]
            except Exception:
                files = []

            with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
                results = list(ex.map(self.extract_features, files))
                for feat in results:
                    if feat:
                        self.features[category].append(feat)
                        total_files += 1

        self.trained = True
        print(f"[{self.name}] Treinamento finalizado: {total_files} imagens mapeadas em {len(self.category_names)} categorias.")
        self._save_to_cache()
        return True

    def _compute_distance(self, f1: Dict[str, Any], f2: Dict[str, Any], is_quality: bool) -> float:
        """Cálculo de distância euclidiana normalizada entre dois vetores de features."""
        ar_dist = abs(f1["aspect_ratio"] - f2["aspect_ratio"])
        fill_dist = abs(f1.get("fill_ratio", 1.0) - f2.get("fill_ratio", 1.0))
        edge_dist = abs(f1.get("edge_density", 0.0) - f2.get("edge_density", 0.0))
        complexity_dist = abs(f1.get("contour_complexity", 1.0) - f2.get("contour_complexity", 1.0))

        # Comparação de histograma via Chi-Square
        hist_dist = cv2.compareHist(f1["hist"], f2["hist"], cv2.HISTCMP_CHISQR)

        # Nitidez em escala logarítmica para estabilidade
        s1_ten = np.log1p(f1.get("sharpness_tenengrad", 0.0))
        s2_ten = np.log1p(f2.get("sharpness_tenengrad", 0.0))
        sharp_ten_dist = abs(s1_ten - s2_ten)

        s1_lap = np.log1p(f1.get("sharpness_laplacian_norm", 0.0))
        s2_lap = np.log1p(f2.get("sharpness_laplacian_norm", 0.0))
        sharp_lap_dist = abs(s1_lap - s2_lap)

        if is_quality:
            # Em qualidade, nitidez e histograma de detalhes têm maior relevância
            dist = (
                (sharp_ten_dist * 25.0)
                + (sharp_lap_dist * 20.0)
                + (hist_dist / 600.0)
                + (edge_dist * 15.0)
                + (ar_dist * 2.0)
            )
        else:
            # Em tipo de material, proporção, fill_ratio, contorno e escala física dominam
            dim_dist = 0.0
            if f1.get("width_cm") and f2.get("width_cm"):
                dw = abs(f1["width_cm"] - f2["width_cm"]) / max(1.0, f1["width_cm"])
                dh = abs(f1["height_cm"] - f2["height_cm"]) / max(1.0, f1["height_cm"])
                dim_dist = (dw + dh) * 5.0

            dist = (
                (ar_dist * 14.0)
                + (fill_dist * 18.0)
                + (complexity_dist * 10.0)
                + (edge_dist * 8.0)
                + (hist_dist / 900.0)
                + (sharp_ten_dist * 2.0)
                + dim_dist
            )

        return float(dist)

    def classify_with_details(
        self, image: Image.Image, filename: Optional[str] = None
    ) -> ClassificationResult:
        """Classifica a imagem e calcula pontuação de confiança e detalhes diagnósticos."""
        if not self.trained:
            if not self.train():
                return ClassificationResult("N/A", 0.0, [], {"error": "Treinamento indisponível"})

        new_feat = self.extract_features(image)
        if not new_feat:
            return ClassificationResult("Erro", 0.0, [], {"error": "Falha na extração de features"})

        # 1. Verificar correspondência com motor de regras de palavras-chave
        rule_match = self.rules_engine.match(filename) if filename else None
        rule_category = rule_match[0] if rule_match else None
        rule_confidence = rule_match[1] if rule_match else 0.0
        rule_kw = rule_match[2] if rule_match else None

        is_quality = "qualidade" in str(self.training_dir).lower() or self.name.lower() == "qualidade"

        # 2. Avaliar distâncias KNN para cada amostra do dataset
        all_distances: List[Tuple[float, str]] = []
        for cat, feat_list in self.features.items():
            # Se categoria coincidir com regra explícita no nome, aplica bônus ponderado
            cat_multiplier = 0.2 if (rule_category and rule_category.lower() == cat.lower()) else 1.0

            for sample_feat in feat_list:
                d = self._compute_distance(new_feat, sample_feat, is_quality=is_quality)
                final_d = d * cat_multiplier
                all_distances.append((final_d, cat))

        if not all_distances:
            # Se não houver amostras na base mas houver regra por nome, usa a regra
            if rule_category:
                return ClassificationResult(
                    category=rule_category,
                    confidence_pct=round(rule_confidence * 100.0, 1),
                    alternatives=[],
                    details={"features": new_feat, "rule": rule_kw},
                    rule_matched=rule_kw,
                )
            return ClassificationResult("Sem dados", 0.0, [], {"features": new_feat})

        # Ordenar por proximidade
        all_distances.sort(key=lambda x: x[0])
        k = min(7, len(all_distances))
        top_k = all_distances[:k]

        # 3. Cálculo de Probabilidades Ponderadas por Distância (Softmax inversa)
        weights: Dict[str, float] = {}
        for dist, cat in top_k:
            # Quanto menor a distância, maior o peso
            w = 1.0 / (dist + 0.05)
            weights[cat] = weights.get(cat, 0.0) + w

        # Se houver regra forte por nome, bonifica significativamente
        if rule_category:
            weights[rule_category] = weights.get(rule_category, 0.0) * (2.5 * rule_confidence)

        total_weight = sum(weights.values())
        cat_probs = [
            (cat, (w / total_weight) * 100.0)
            for cat, w in sorted(weights.items(), key=lambda item: item[1], reverse=True)
        ]

        winner_cat, winner_conf = cat_probs[0]
        alternatives = cat_probs[1:4]

        # Em caso de regra inequívoca por nome (>0.95), garante confiança alta
        if rule_category and rule_category == winner_cat and rule_confidence >= 0.95:
            winner_conf = max(winner_conf, rule_confidence * 100.0)

        return ClassificationResult(
            category=winner_cat,
            confidence_pct=round(min(99.9, winner_conf), 1),
            alternatives=[(c, round(p, 1)) for c, p in alternatives],
            details={
                "aspect_ratio": round(new_feat["aspect_ratio"], 2),
                "fill_ratio": round(new_feat["fill_ratio"] * 100.0, 1),
                "contour_complexity": round(new_feat["contour_complexity"], 2),
                "edge_density": round(new_feat["edge_density"] * 100.0, 1),
                "sharpness_tenengrad": round(new_feat["sharpness_tenengrad"], 1),
                "sharpness_laplacian_norm": round(new_feat["sharpness_laplacian_norm"], 1),
                "width_cm": round(new_feat["width_cm"], 1),
                "height_cm": round(new_feat["height_cm"], 1),
            },
            rule_matched=rule_kw if (rule_category == winner_cat) else None,
        )

    def classify(self, image: Image.Image, filename: Optional[str] = None) -> str:
        """Compatibilidade retroativa: retorna apenas o nome da categoria vencedora."""
        return self.classify_with_details(image, filename).category

    def learn_sample(
        self,
        image_or_path: Path | Image.Image,
        category: str,
        filename: Optional[str] = None,
        save_to_disk: bool = True,
    ) -> bool:
        """Aprendizado Incremental em Tempo Real (Online Learning).
        Injeta a amostra imediatamente em memória e persiste no cache."""
        if not category or category in ("N/A", "Erro", "Sem dados"):
            return False

        feat = self.extract_features(image_or_path)
        if not feat:
            return False

        # Injeta na lista de categorias ativas
        if category not in self.category_names:
            self.category_names.append(category)

        # Adiciona vetor de features em memória instantaneamente
        self.features.setdefault(category, []).append(feat)
        self.trained = True

        # Sincroniza cache JSON local
        self._save_to_cache()

        # Opcional: salvar a imagem no diretório de treinamento
        if save_to_disk:
            try:
                dest_dir = self.training_dir / category
                dest_dir.mkdir(parents=True, exist_ok=True)

                if filename:
                    stem = Path(filename).stem
                else:
                    stem = f"sample_{hashlib.md5(str(feat).encode()).hexdigest()[:8]}"

                # Remover de outras categorias se foi movido/corrigido
                for other_cat in list(self.category_names):
                    if other_cat != category:
                        for ext in (".png", ".jpg", ".jpeg", ".webp"):
                            old_f = self.training_dir / other_cat / f"{stem}{ext}"
                            if old_f.exists():
                                try:
                                    old_f.unlink()
                                except Exception:
                                    pass

                dest_file = dest_dir / f"{stem}.png"
                if isinstance(image_or_path, (Path, str)):
                    shutil.copy2(image_or_path, dest_file)
                else:
                    image_or_path.save(dest_file, format="PNG")
                print(f"[{self.name}] 🧠 Aprendizado registrado para '{category}': {dest_file.name}")
            except Exception as e:
                print(f"[{self.name}] Não foi possível gravar amostra física em disco: {e}")

        return True

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas detalhadas para a UI."""
        counts = {cat: len(feats) for cat, feats in self.features.items()}
        total_samples = sum(counts.values())
        return {
            "name": self.name,
            "trained": self.trained,
            "total_categories": len(self.category_names),
            "total_samples": total_samples,
            "category_counts": counts,
            "training_dir": str(self.training_dir),
            "cache_file": str(self.cache_file),
            "cache_exists": self.cache_file.exists(),
        }

    def add_category(self, name: str) -> bool:
        clean = name.strip()
        if not clean:
            return False
        if clean not in self.category_names:
            self.category_names.append(clean)
            self.features.setdefault(clean, [])
            self._save_to_cache()
            return True
        return False

    def rename_category(self, old_name: str, new_name: str) -> bool:
        clean_new = new_name.strip()
        if not clean_new or old_name not in self.category_names:
            return False

        if clean_new != old_name:
            if old_name in self.features:
                self.features[clean_new] = self.features.pop(old_name)
            idx = self.category_names.index(old_name)
            self.category_names[idx] = clean_new

            # Renomear pasta se existir
            old_dir = self.training_dir / old_name
            new_dir = self.training_dir / clean_new
            if old_dir.exists():
                try:
                    old_dir.rename(new_dir)
                except Exception:
                    pass

            self._save_to_cache()
            return True
        return False

    def remove_category(self, name: str) -> bool:
        if name in self.category_names:
            self.category_names.remove(name)
            self.features.pop(name, None)
            self._save_to_cache()
            return True
        return False


_prod_classifier: Optional[ImageClassifier] = None
_quality_classifier: Optional[ImageClassifier] = None


def get_prod_classifier() -> ImageClassifier:
    global _prod_classifier
    if _prod_classifier is None:
        training_path = _resolve_training_dir(r"Z:\IMPRESSÃO DE TOTENS\treinamentos", "treinamentos")
        _prod_classifier = ImageClassifier(training_path, "Producao")
        _prod_classifier.train()
    return _prod_classifier


def get_quality_classifier() -> ImageClassifier:
    global _quality_classifier
    if _quality_classifier is None:
        training_path = _resolve_training_dir(r"Z:\IMPRESSÃO DE TOTENS\qualidade", "qualidade")
        _quality_classifier = ImageClassifier(training_path, "Qualidade")
        _quality_classifier.train()
    return _quality_classifier


def get_classifier() -> ImageClassifier:
    return get_prod_classifier()


def feed_back_to_training(
    folder: Path | str,
    filename: str,
    threshold: int,
    category: Optional[str] = None,
    quality: Optional[str] = None,
) -> None:
    """Realimenta o classificador em tempo real (Online Learning) e sincroniza com o disco."""
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

        with Image.open(cache_png) as pil_cached:
            cached_copy = pil_cached.copy()

        # 1. Aprendizado em tempo real para Categoria / Tipo de Produção
        if category and category not in ("N/A", "Erro", "Sem dados"):
            prod_cls = get_prod_classifier()
            prod_cls.learn_sample(
                image_or_path=cached_copy,
                category=category,
                filename=filename,
                save_to_disk=True,
            )

        # 2. Aprendizado em tempo real para Qualidade
        if quality and quality not in ("N/A", "Erro", "Sem dados"):
            qual_cls = get_quality_classifier()
            qual_cls.learn_sample(
                image_or_path=cached_copy,
                category=quality.lower(),
                filename=filename,
                save_to_disk=True,
            )

    except Exception as e:
        print(f"[Classifier] Erro ao executar feed_back_to_training: {e}")

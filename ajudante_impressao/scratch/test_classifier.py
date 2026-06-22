import sys
import os
from pathlib import Path
from PIL import Image

# Adicionar o diretório do projeto ao sys.path para importar os módulos
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from ajudante_impressao.algorithms.classifier import get_prod_classifier, get_quality_classifier
from ajudante_impressao.algorithms.image_ops import add_label_to_image

def _resolve_test_dir(default_windows_path: str, local_dirname: str, subcat: str) -> Path:
    win_path = Path(default_windows_path) / subcat
    if os.name == 'nt' and win_path.exists():
        return win_path
    
    linux_paths = [
        Path("/home/mateus/Documentos/Projects/Pessoais/impressor") / local_dirname / subcat,
        Path.home() / "Documentos/Projects/Pessoais/impressor" / local_dirname / subcat,
    ]
    for p in linux_paths:
        if p.exists():
            return p
    return win_path

def test_classification():
    prod_cls = get_prod_classifier()
    qual_cls = get_quality_classifier()
    
    # Testar Prod
    print("\n--- Testando Produção ---")
    test_dirs_prod = {
        "3mm sp": _resolve_test_dir(r"Z:\IMPRESSÃO DE TOTENS\treinamentos", "treinamentos", "3mm sp"),
        "6mm cp": _resolve_test_dir(r"Z:\IMPRESSÃO DE TOTENS\treinamentos", "treinamentos", "6mm cp"),
        "poliondas": _resolve_test_dir(r"Z:\IMPRESSÃO DE TOTENS\treinamentos", "treinamentos", "poliondas")
    }
    
    for expected, folder in test_dirs_prod.items():
        if not folder.exists(): continue
        files = list(folder.iterdir())
        if not files: continue
        with Image.open(files[0]) as img:
            res = prod_cls.classify(img, filename=files[0].name)
            print(f"File: {files[0].name} | Exp: {expected} | Res: {res}")

    # Testar Qualidade
    print("\n--- Testando Qualidade ---")
    test_dirs_qual = {
        "boa": _resolve_test_dir(r"Z:\IMPRESSÃO DE TOTENS\qualidade", "qualidade", "boa"),
        "aceitavel": _resolve_test_dir(r"Z:\IMPRESSÃODE TOTENS\qualidade", "qualidade", "aceitavel"),
        "ruim": _resolve_test_dir(r"Z:\IMPRESSÃO DE TOTENS\qualidade", "qualidade", "ruim")
    }
    
    for expected, folder in test_dirs_qual.items():
        if not folder.exists(): continue
        files = list(folder.iterdir())
        if not files: continue
        with Image.open(files[0]) as img:
            res = qual_cls.classify(img, filename=files[0].name)
            print(f"File: {files[0].name} | Exp: {expected} | Res: {res}")
            
            # Testar a escrita combinada
            labeled = add_label_to_image(img.copy(), f"PROD | Q: {res}")
            out = Path(f"test_qual_{expected}.png")
            labeled.save(out)
            print(f"  -> Salvo em: {out.absolute()}")

if __name__ == "__main__":
    test_classification()

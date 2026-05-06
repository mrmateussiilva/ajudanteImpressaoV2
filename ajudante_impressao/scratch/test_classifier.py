import sys
from pathlib import Path
from PIL import Image

# Adicionar o diretório do projeto ao sys.path para importar os módulos
project_root = Path(r"c:\Users\User\Documents\Mateus\ajudanteImpressaoV2")
sys.path.append(str(project_root))

from ajudante_impressao.algorithms.classifier import get_prod_classifier, get_quality_classifier
from ajudante_impressao.algorithms.image_ops import add_label_to_image

def test_classification():
    prod_cls = get_prod_classifier()
    qual_cls = get_quality_classifier()
    
    # Testar Prod
    print("\n--- Testando Produção ---")
    test_dirs_prod = {
        "3mm sp": Path(r"Z:\IMPRESSÃO DE TOTENS\treinamentos\3mm sp"),
        "6mm cp": Path(r"Z:\IMPRESSÃO DE TOTENS\treinamentos\6mm cp"),
        "poliondas": Path(r"Z:\IMPRESSÃO DE TOTENS\treinamentos\poliondas")
    }
    
    for expected, folder in test_dirs_prod.items():
        if not folder.exists(): continue
        files = list(folder.iterdir())
        if not files: continue
        with Image.open(files[0]) as img:
            res = prod_cls.classify(img)
            print(f"File: {files[0].name} | Exp: {expected} | Res: {res}")

    # Testar Qualidade
    print("\n--- Testando Qualidade ---")
    test_dirs_qual = {
        "boa": Path(r"Z:\IMPRESSÃO DE TOTENS\qualidade\boa"),
        "aceitavel": Path(r"Z:\IMPRESSÃO DE TOTENS\qualidade\aceitavel"),
        "ruim": Path(r"Z:\IMPRESSÃO DE TOTENS\qualidade\ruim")
    }
    
    for expected, folder in test_dirs_qual.items():
        if not folder.exists(): continue
        files = list(folder.iterdir())
        if not files: continue
        with Image.open(files[0]) as img:
            res = qual_cls.classify(img)
            print(f"File: {files[0].name} | Exp: {expected} | Res: {res}")
            
            # Testar a escrita combinada
            labeled = add_label_to_image(img.copy(), f"PROD | Q: {res}")
            out = Path(f"test_qual_{expected}.png")
            labeled.save(out)
            print(f"  -> Salvo em: {out.absolute()}")

if __name__ == "__main__":
    test_classification()

from __future__ import annotations

import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from ajudante_impressao.algorithms.classifier import (
    ImageClassifier,
    KeywordRulesEngine,
    ClassificationResult,
    get_prod_classifier,
    get_quality_classifier,
)


def run_tests():
    print("=" * 60)
    print("🚀 INICIANDO TESTES DO MOTOR DE INTELIGÊNCIA & APRENDIZADO")
    print("=" * 60)

    # 1. Teste do Motor de Regras por Palavras-chave
    print("\n--- 1. Teste: KeywordRulesEngine ---")
    rules_engine = KeywordRulesEngine()
    test_filenames = [
        ("totem_homem_aranha_3mm_sp.png", "3mm sp"),
        ("totem_hulk_6mm_cp.png", "6mm cp"),
        ("placa_sinalizacao_polionda_100x50.png", "poliondas"),
        ("adesivo_promocional_vitrine.png", "adesivo"),
        ("banner_lona_evento_2026.png", "lona"),
        ("figura_sem_regra.png", None),
    ]

    for fname, expected in test_filenames:
        match = rules_engine.match(fname)
        if match:
            cat, conf, kw = match
            print(f"  ✓ '{fname}' -> [{cat}] (Confiança: {conf*100:.0f}%, Regra: '{kw}')")
            if expected:
                assert cat == expected, f"Esperado {expected}, obtido {cat}"
        else:
            print(f"  ✓ '{fname}' -> Sem regra direta no nome (OK)")
            assert expected is None, f"Esperava correspondência para {expected}"

    print("  -> KeywordRulesEngine validado com sucesso!")

    # 2. Teste de Extração de Features Avançadas
    print("\n--- 2. Teste: Extração de Features Geométricas & Nitidez ---")
    # Criar uma imagem sintética com canal alfa recortado (simulando um totem recortado)
    img_totem = Image.new("RGBA", (200, 500), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img_totem)
    draw.polygon([(40, 480), (160, 480), (130, 80), (70, 80)], fill=(50, 150, 250, 255))
    draw.ellipse((60, 20, 140, 100), fill=(255, 100, 100, 255))

    classifier = ImageClassifier(ROOT_DIR / "ajudante_impressao" / "scratch" / "test_train_dir", name="TestCls")
    feats = classifier.extract_features(img_totem)
    assert feats is not None, "Falha na extração de features"

    print(f"  ✓ Aspect Ratio: {feats['aspect_ratio']:.2f}")
    print(f"  ✓ Fill Ratio: {feats['fill_ratio']*100:.1f}% (corretamente recortado com transparência)")
    print(f"  ✓ Complexidade do Contorno: {feats['contour_complexity']:.2f}")
    print(f"  ✓ Densidade de Bordas: {feats['edge_density']*100:.1f}%")
    print(f"  ✓ Nitidez Tenengrad: {feats['sharpness_tenengrad']:.2f}")
    print(f"  ✓ Nitidez Laplaciana Norm: {feats['sharpness_laplacian_norm']:.2f}")
    print(f"  ✓ Dimensões em cm: {feats['width_cm']:.1f}x{feats['height_cm']:.1f}cm")

    assert feats['fill_ratio'] < 0.90, "Fill ratio deve detectar recorte e ser menor que 90%"
    assert feats['aspect_ratio'] < 0.6, "Proporção vertical esperada menor que 0.6"

    # 3. Teste de Aprendizado Incremental em Tempo Real (Online Learning)
    print("\n--- 3. Teste: Aprendizado Incremental em Tempo Real (Online Learning) ---")
    # Ensinar 2 categorias com artes distintas
    img_banner = Image.new("RGBA", (800, 250), (255, 200, 50, 255)) # retangular sólido

    success1 = classifier.learn_sample(img_totem, category="3mm sp", filename="totem_sample_01.png", save_to_disk=False)
    success2 = classifier.learn_sample(img_banner, category="lona", filename="banner_sample_01.png", save_to_disk=False)
    assert success1 and success2, "Falha ao registrar aprendizado incremental"

    # Validar que a base aprendeu imediatamente sem recarregar
    stats = classifier.get_stats()
    print(f"  ✓ Amostras aprendidas em RAM: {stats['total_samples']} em {stats['total_categories']} categorias")
    assert stats["total_categories"] >= 2
    assert "3mm sp" in classifier.category_names
    assert "lona" in classifier.category_names

    # 4. Teste de Classificação com Confiança e Alternativas
    print("\n--- 4. Teste: Classificação & Grau de Confiança % ---")
    # Testar totem similar
    test_totem_variant = Image.new("RGBA", (220, 520), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(test_totem_variant)
    d2.polygon([(45, 500), (170, 500), (140, 90), (75, 90)], fill=(60, 140, 230, 255))

    res = classifier.classify_with_details(test_totem_variant, filename="arte_desconhecida.png")
    print(f"  ✓ Resultado da predição: [{res.category}] com {res.confidence_pct:.1f}% de confiança")
    print(f"  ✓ Alternativas calculadas: {res.alternatives}")
    assert res.category == "3mm sp", f"Deveria classificar como '3mm sp', obteve {res.category}"
    assert res.confidence_pct >= 50.0, "Confiança deveria ser significativa"

    # 5. Teste com Imagens Reais do Projeto (test_qual_boa.png / test_qual_ruim.png)
    print("\n--- 5. Teste: Imagens de Teste de Qualidade ---")
    p_boa = ROOT_DIR / "test_qual_boa.png"
    p_ruim = ROOT_DIR / "test_qual_ruim.png"

    if p_boa.exists() and p_ruim.exists():
        with Image.open(p_boa) as im_boa:
            f_boa = classifier.extract_features(im_boa)
        with Image.open(p_ruim) as im_ruim:
            f_ruim = classifier.extract_features(im_ruim)

        print(f"  ✓ Qualidade Boa - Tenengrad: {f_boa['sharpness_tenengrad']:.2f}, Laplaciano Norm: {f_boa['sharpness_laplacian_norm']:.2f}")
        print(f"  ✓ Qualidade Ruim - Tenengrad: {f_ruim['sharpness_tenengrad']:.2f}, Laplaciano Norm: {f_ruim['sharpness_laplacian_norm']:.2f}")

    print("\n" + "=" * 60)
    print("🎉 TODOS OS TESTES DO MOTOR DE INTELIGÊNCIA FORAM APROVADOS COM SUCESSO!")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()

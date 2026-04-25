# Migracao para Rust

## Objetivo

Migrar os algoritmos mais pesados do projeto para Rust sem reescrever a aplicacao inteira.

O plano e manter:

- interface em `PySide6`
- orquestracao em Python
- leitura e salvamento de imagem em Python
- nucleo computacional em Rust

## Escopo Inicial

### Primeira leva

Portar primeiro o algoritmo de encaixe mascarado:

- `pack_images_masked`
- `_prepare_mask_variants`
- `_ensure_height`
- `_collides`
- `_stamp_reserved`
- `_score_candidate`

Arquivo de origem atual:

- [`ajudante_impressao/algorithms/packing.py`](/home/mateus/Documentos/Projetcts/Pessoais/ajudanteImpressaoV2/ajudante_impressao/algorithms/packing.py:1)

### Segunda leva

- `pack_images_tight`

### Terceira leva

- `remove_white`

Arquivo de origem atual:

- [`ajudante_impressao/algorithms/image_ops.py`](/home/mateus/Documentos/Projetcts/Pessoais/ajudanteImpressaoV2/ajudante_impressao/algorithms/image_ops.py:35)

## Tecnologia Recomendada

### Stack

- `Rust`
- `PyO3`
- `maturin`

### Motivo

Essa combinacao permite:

- gerar modulo nativo para Python
- manter build relativamente simples
- expor funcoes Rust como API Python
- evoluir o motor sem misturar logica de UI

## Estrutura Sugerida

```text
native/
  packer_rs/
    Cargo.toml
    pyproject.toml
    src/
      lib.rs
      masked.rs
      tight.rs
      image.rs
```

## Modelo de Integracao

### Regra principal

Python continua sendo a camada de aplicacao.
Rust vira uma biblioteca especializada.

### Fluxo esperado

1. Python carrega as imagens com `Pillow`
2. Python extrai dados necessarios:
   - largura
   - altura
   - mascara alfa
3. Python chama a funcao Rust
4. Rust devolve apenas resultado estrutural:
   - posicoes
   - dimensoes finais
5. Python monta o canvas final e salva o arquivo

## API Alvo

### Packing mascarado

```python
placements, final_width, final_height = pack_masked(
    masks=masks,
    widths=widths,
    heights=heights,
    max_width=max_width,
    spacing=spacing,
    margin=margin,
    step=step,
)
```

### Packing tight

```python
placements, final_width, final_height = pack_tight(
    widths=widths,
    heights=heights,
    max_width=max_width,
    spacing=spacing,
    margin=margin,
    step=step,
)
```

### Remove white

```python
rgba_bytes = remove_white_rgba(
    rgba_bytes=rgba_bytes,
    width=width,
    height=height,
    threshold=threshold,
    softness=softness,
)
```

## Contratos de Dados

### Entrada para packing

Cada item deve ter:

- `id`
- `width`
- `height`
- `mask`

Onde:

- `mask` pode ser uma matriz booleana achatada
- ou `bytes` representando alfa > 0

### Saida do packing

Cada posicionamento deve retornar:

- `id`
- `x`
- `y`
- `variant_index`

## Limites de Responsabilidade

### Python

- UI
- logs
- leitura de diretorio
- abertura de imagens
- previews
- montagem do canvas
- persistencia do resultado

### Rust

- busca de encaixe
- colisao por mascara
- expansao de grade de ocupacao
- scoring de candidatos
- operacoes pesadas por pixel

## Plano de Execucao

### Etapa 1

Criar benchmark Python para a implementacao atual.

### Etapa 2

Criar modulo Rust vazio com `PyO3`.

### Etapa 3

Implementar apenas `pack_masked`.

### Etapa 4

Criar adaptador Python:

- `packing_rust.py`
- fallback automatico para Python puro

### Etapa 5

Comparar saida Python vs Rust com testes fixos.

### Etapa 6

Trocar o modo padrao apenas depois de validar estabilidade.

## Estrategia de Fallback

O projeto nao deve depender exclusivamente do modulo Rust no inicio.

### Regra

Se o modulo nativo nao estiver instalado:

- continuar usando Python

### Exemplo

```python
try:
    from native_packer import pack_masked
except ImportError:
    pack_masked = None
```

## Riscos

### 1. Custo de conversao Python -> Rust

Se a serializacao dos dados for ruim, o ganho de performance cai.

### 2. Diferenca de resultado

O motor Rust pode gerar layouts diferentes do Python se a logica nao for portada com cuidado.

### 3. Build mais complexa

O projeto passa a depender de toolchain Rust.

### 4. Debug mais dificil

Erros de algoritmo ficam menos visiveis do que em Python puro.

## Criterios de Sucesso

Uma migracao so vale a pena se:

1. reduzir claramente o tempo do `pack_images_masked`
2. mantiver ou melhorar a qualidade do layout
3. nao complicar demais o empacotamento do projeto
4. tiver fallback estavel em Python

## Meta Final

Chegar a um modelo em que:

- Python controla a aplicacao
- Rust executa os pontos criticos
- o operador usa a mesma interface
- o sistema fica mais rapido sem perder previsibilidade

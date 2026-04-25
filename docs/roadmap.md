# Roadmap

## Objetivo

Evoluir o projeto como uma aplicacao focada apenas em `Rolo Packer` e `Cut Panel`, com melhoria progressiva de performance, organizacao e confiabilidade.

## Direcao do Produto

1. Manter o escopo fechado em dois fluxos:
   - `Rolo Packer`
   - `Cut Panel`
2. Evitar reintroduzir modulos paralelos que desviem do uso real da operacao.
3. Priorizar velocidade, previsibilidade e clareza do fluxo de trabalho.

## Fase 1: Base Estavel

### Meta

Consolidar a estrutura atual como base oficial do projeto.

### Acoes

1. Manter a arquitetura em:
   - `ajudante_impressao/ui`
   - `ajudante_impressao/services`
   - `ajudante_impressao/algorithms`
2. Padronizar nomes, logs e estados da interface.
3. Reduzir duplicacao restante nas telas.
4. Criar cenarios de teste com arquivos reais da operacao.

## Fase 2: Benchmark e Diagnostico

### Meta

Medir o custo real dos algoritmos antes de portar qualquer parte para Rust.

### Acoes

1. Criar benchmarks para:
   - `pack_images_masked`
   - `pack_images_tight`
   - `remove_white`
2. Medir com:
   - poucas imagens
   - muitas imagens
   - imagens grandes
   - imagens com mascara alfa complexa
3. Registrar:
   - tempo total
   - uso de memoria
   - altura final do layout
   - quantidade de imagens posicionadas

## Fase 3: Contratos para Motor Nativo

### Meta

Preparar interfaces simples entre Python e um futuro modulo Rust.

### Acoes

1. Definir entradas nativas em formatos simples:
   - largura e altura
   - mascara alfa
   - margem
   - espacamento
   - step
2. Definir saida padronizada:
   - lista de posicionamentos
   - largura final
   - altura final
3. Isolar conversoes entre `Pillow` e estruturas de dados puras.

## Fase 4: Portar Nucleo Pesado para Rust

### Meta

Mover primeiro apenas os algoritmos de maior retorno.

### Prioridade 1

- `pack_images_masked`
- `_prepare_mask_variants`
- `_ensure_height`
- `_collides`
- `_stamp_reserved`
- `_score_candidate`

### Prioridade 2

- `pack_images_tight`

### Prioridade 3

- `remove_white`

### Diretriz

Manter interface, carga de arquivos, preview e regras de aplicacao em Python.
Levar para Rust apenas o miolo computacional.

## Fase 5: Integracao com Python

### Meta

Conectar Rust sem desmontar a base atual.

### Stack sugerida

- `Rust`
- `PyO3`
- `maturin`

### API alvo

1. `pack_masked(...) -> placements`
2. `pack_tight(...) -> placements`
3. `remove_white_rgba(...) -> rgba`

## Fase 6: Validacao e Rollout

### Meta

Trocar a implementacao com seguranca.

### Acoes

1. Comparar Python vs Rust em:
   - tempo
   - memoria
   - colisao
   - altura final
   - consistencia visual
2. Liberar em etapas:
   - fase A: Rust opcional
   - fase B: Rust padrao com fallback Python
   - fase C: remover fallback so se a versao nativa estiver madura

## Fase 7: Melhorias de Produto

### Meta

Depois da base estar rapida e estavel, melhorar a operacao diaria.

### Acoes

1. Adicionar presets por material ou tipo de trabalho.
2. Criar fila de processamento.
3. Registrar historico de jobs.
4. Exportar resumo por execucao.
5. Melhorar a observabilidade do processamento.

## Estrutura Futura Sugerida

```text
ajudante_impressao/
  ui/
  services/
  algorithms/
native/
  packer_rs/
tests/
  benchmarks/
  golden_outputs/
docs/
  roadmap.md
```

## Regra de Prioridade

Sempre seguir esta ordem:

1. corrigir gargalo comprovado
2. manter compatibilidade funcional
3. melhorar performance
4. depois melhorar ergonomia e operacao

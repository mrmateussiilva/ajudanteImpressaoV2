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

Medir o custo real dos algoritmos.

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

## Fase 3: Refinamento Algorítmico

### Meta

Otimizar os algoritmos de encaixe puramente em Python.

### Acoes

1. Refinar a busca multi-escala em `pack_images_masked`.
2. Remover cálculos redundantes de colisão.
3. Explorar novas estratégias de empacotamento baseadas em perfis otimizados.

## Fase 4: Melhorias de Produto

### Meta

Depois da base estar rapida e estavel, melhorar a operacao diaria.

### Acoes

1. Adicionar presets por material ou tipo de trabalho.
2. Criar fila de processamento.
3. Registrar historico de jobs.
4. Exportar resumo por execucao.
5. Melhorar a observabilidade do processamento.

## Estrutura Sugerida

```text
ajudante_impressao/
  ui/
  services/
  algorithms/
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

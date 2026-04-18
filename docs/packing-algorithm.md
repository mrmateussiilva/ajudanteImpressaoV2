# Algoritmo de Encaixe de Imagens

Este documento descreve como o empacotamento de imagens funciona no projeto, com foco em `packing_algorithms.py`.

## Objetivo

Organizar imagens recortadas dentro da largura util do rolo com:

- margem externa
- espacamento entre pecas
- opcao de rotacao
- menor altura final possivel

O resultado de cada algoritmo e uma lista de itens no formato:

```python
(imagem, x, y)
```

mais a largura e a altura finais do canvas.

## Pipeline Antes do Encaixe

Antes do pack, as imagens passam por etapas em `image_utils.py`:

1. normalizacao de DPI
2. remocao de fundo branco
3. recorte da area transparente
4. ajuste de largura maxima, se necessario

Isso e importante porque o algoritmo trabalha em cima da geometria util da imagem, nao da tela bruta original.

## Modos de Encaixe

### `pack_images_gallery`

Modo por linhas.

Estrategia:

1. recorta bordas vazias
2. opcionalmente gira imagens muito verticais
3. normaliza tudo para uma altura-base
4. ordena por area
5. distribui em linhas
6. aplica um pequeno fator de escala para preencher melhor a largura

Vantagem:

- resultado visual mais regular
- bom para mosaico horizontal

Limite:

- ainda depende de linhas
- nao explora bem encaixe de formatos irregulares

### `pack_images_fast`

Modo guloso por linhas.

Estrategia:

1. prepara imagens
2. ordena por altura e largura
3. tenta encaixar cada item na linha com menor sobra horizontal
4. cria nova linha quando nao cabe

Vantagem:

- simples
- rapido

Limite:

- aproveitamento menor
- ruim para formatos muito diferentes

### `pack_images_tight`

Modo baseado em skyline 1D.

Estrategia:

1. ordena imagens por area
2. mantem um perfil de altura por coluna do rolo
3. testa posicoes em passos discretos (`step`)
4. escolhe a posicao que minimiza a base inferior da peca

Vantagem:

- melhor compactacao que os modos por linha
- custo computacional controlado

Limite:

- usa apenas a caixa delimitadora
- nao considera a forma real da area transparente

## Modo Poligonal por Mascara

### `pack_images_masked`

Este e o modo mais avancado atualmente.

Ele nao faz nesting geometrico por poligono matematico puro. Em vez disso, usa a mascara alfa real da imagem como area ocupada.

### Ideia central

Cada imagem vira uma mascara binaria:

- pixel com alfa > 0 = ocupado
- pixel transparente = livre

O encaixe passa a ser feito por colisao real entre mascaras, e nao apenas por retangulos.

## Etapas do `masked`

### 1. Preparacao de variantes

Funcao: `_prepare_mask_variants`

Para cada imagem:

1. recorta bordas vazias
2. gera variantes rotacionadas
3. limita a largura ao rolo util
4. gera mascara alfa binaria
5. remove variantes duplicadas por assinatura

Rotacoes usadas quando `allow_rotate=True`:

- `0`
- `90`
- `15`, `-15`
- `30`, `-30`
- `45`, `-45`
- `60`, `-60`
- `75`, `-75`

Isso melhora o aproveitamento sem entrar em busca angular continua.

### 2. Ordenacao das pecas

Cada peca e ordenada por:

- area real ocupada
- maior altura entre variantes
- maior largura entre variantes

Na pratica, pecas mais grandes entram primeiro, o que reduz a chance de sobrar apenas espacos pequenos e inuteis.

### 3. Mapa de ocupacao

O algoritmo mantem um `occupancy` 2D em `numpy`.

Esse mapa representa:

- pixels ja ocupados por pecas
- reserva extra para o espacamento

Quando a altura atual nao e suficiente, `_ensure_height` expande a matriz.

### 4. Pontos candidatos

Em vez de varrer o canvas inteiro, o algoritmo testa um conjunto de pontos candidatos.

Esses pontos nascem de:

- canto superior esquerdo inicial
- borda direita de pecas ja colocadas
- borda inferior de pecas ja colocadas
- um ponto intermediario abaixo da peca

Isso reduz custo e mantem boa qualidade.

### 5. Colisao real

Funcao: `_collides`

Para cada variante e ponto candidato:

1. verifica limites do canvas
2. cruza a mascara da peca com a regiao ocupada
3. rejeita a posicao se houver qualquer sobreposicao

Esse e o ponto que diferencia o modo `masked` dos modos baseados em caixa delimitadora.

### 6. Score local

Funcao: `_score_candidate`

Cada posicao recebe score com base em:

- altura maxima resultante
- base inferior da nova peca
- desperdicio local da bounding box
- proximidade das bordas laterais

Objetivo:

- reduzir altura final
- evitar espacos ruins
- manter layout mais compacto

### 7. Reserva de espacamento

Funcao: `_stamp_reserved`

Depois de posicionar uma peca, o algoritmo:

1. grava a mascara ocupada
2. expande essa ocupacao pela distancia de `spacing`
3. impede que a proxima peca encoste demais

Essa etapa usa uma dilatacao discreta da mascara base.

## Parametros que Mais Influenciam

### `spacing`

Controla a distancia minima entre pecas.

- maior `spacing` = mais seguranca
- menor `spacing` = melhor aproveitamento

### `margin`

Define a borda externa do rolo.

### `step`

Controla a granularidade da busca:

- `step` menor = melhor encaixe e maior custo
- `step` maior = busca mais rapida e possivelmente menos precisa

### `allow_rotate`

Ativa as variantes rotacionadas discretas.

## Tradeoffs

### Qualidade vs tempo

O modo `masked` entrega melhor aproveitamento, mas custa mais que `gallery`, `fast` e `tight`.

### Raster vs geometria vetorial

O algoritmo trabalha em raster binario.

Vantagem:

- integra bem com imagens recortadas por transparencia
- simples de validar

Limite:

- nao e um solver de nesting vetorial puro
- a precisao depende da resolucao da imagem e do `step`

## Quando usar cada modo

- `gallery`
  quando a prioridade e organizacao visual em linhas
- `fast`
  quando a prioridade e velocidade
- `tight`
  quando quer compactacao melhor com custo moderado
- `masked`
  quando a prioridade e aproveitar melhor formas irregulares

## Pontos futuros de evolucao

- busca multi-resolucao
- score com penalidade de fragmentacao de vazios
- refinamento local apos a solucao inicial
- heuristicas de ancoragem mais fortes
- representacao vetorial aproximada para no-fit polygon

# Algoritmo de Encaixe de Imagens

Este documento descreve como o empacotamento de imagens funciona no projeto, com foco no único modo suportado agora: `pack_images_masked`.

## Objetivo

Organizar imagens recortadas dentro da largura útil do rolo com:

- Margem externa
- Espaçamento entre peças
- Opção de rotação
- Menor altura final possível
- **Máximo contato entre peças** para evitar buracos e desperdício de mídia

O resultado é uma lista de itens no formato:

```python
(imagem, x, y)
```

mais a largura e a altura finais do canvas.

## Pipeline Antes do Encaixe

Antes do pack, as imagens passam por etapas em `image_ops.py`:

1. Normalização de DPI
2. Remoção de fundo branco
3. Recorte da área transparente
4. Ajuste de largura máxima, se necessário

Isso é importante porque o algoritmo trabalha em cima da geometria útil da imagem real (sua máscara alfa), não da sua bounding box (caixa delimitadora) retangular.

## Modo Poligonal por Máscara (`pack_images_masked`)

O algoritmo usa a máscara alfa real da imagem para calcular o encaixe. O encaixe é feito usando o conceito de **No-Fit Polygon (NFP) no espaço raster** aliado a uma simulação de **gravidade multidirecional**.

### Ideia Central do NFP Raster

Para saber onde uma peça cabe sem colidir com as outras, o algoritmo realiza uma operação de **erosão morfológica**:

1. Identifica o espaço livre atual no canvas (`livre = NOT ocupado`).
2. Erode esse espaço livre usando a máscara da peça (`posições_válidas = cv2.erode(livre, máscara)`).
3. Qualquer pixel com valor 1 no resultado da erosão é um ponto válido (x,y) onde o canto superior esquerdo da peça pode ser colocado sem gerar colisão.

Essa operação matemática em imagens binárias é extremamente rápida e retorna todos os pontos candidatos de uma vez, substituindo a antiga busca pixel a pixel (`_collides`).

### Etapas do Algoritmo

#### 1. Preparação de Variantes

Para cada imagem, o algoritmo gera variantes rotacionadas e recorta bordas vazias, criando uma máscara alfa binária para cada variante. Rotações suportadas (`allow_rotate=True`): 0, 90, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75 graus.

#### 2. Ordenação das Peças

As peças são ordenadas (peças maiores primeiro) por:
- Área real da máscara
- Altura máxima
- Largura máxima

#### 3. Busca Multi-Escala (Coarse-to-Fine)

Para ganhar velocidade, a erosão morfológica não é feita no tamanho original da imagem imediatamente:
- **Coarse**: O espaço livre e a máscara são reduzidos (fator de escala de 2x ou 4x, dependendo do `performance_mode`). A erosão é feita e os pixels válidos geram candidatos aproximados.
- **Fine**: Para os candidatos promissores, o algoritmo volta à escala original e testa o entorno próximo com `_collides` para garantir a precisão de 1 pixel.

#### 4. Avaliação (Scoring e Contato)

Cada posição válida encontrada recebe um score:
- Posições que aumentam a altura total do canvas são penalizadas.
- O algoritmo calcula o **contato** com as peças ao redor (usando `_score_contact`). Posições que tocam mais pixels de outras peças recebem um bônus.

O objetivo duplo é não aumentar a altura do rolo e evitar buracos isolados.

#### 5. Gravity Nudge Total

Depois de escolher a melhor posição inicial, a peça sofre a "gravidade":
A função `_nudge_gravity_full` testa mover a peça em 4 direções principais e diagonais (cima, esquerda, cima-esquerda, cima-direita) iterativamente, reduzindo o passo a cada iteração. Isso simula a peça escorregando pelos contornos das outras peças até encontrar um ponto mínimo local (o encaixe mais justo possível).

#### 6. Reserva de Espaçamento

Depois que a peça finaliza seu deslocamento gravitacional, o `_stamp_reserved` grava a máscara no mapa 2D (`occupancy`) e dilata as bordas pelo valor de `spacing`, garantindo a distância mínima para a próxima peça.

## Parâmetros que Mais Influenciam

### `spacing`
Controla a distância mínima entre peças.

### `margin`
Define a borda externa não imprimível do rolo.

### `step`
Afeta marginalmente o refinamento, mas grande parte da precisão agora é governada pela erosão do NFP.

### `performance_mode`
- `quality`: Fator de escala menor (1x ou 2x) para erosão morfológica, demorado mas encontra espaços exatos.
- `balanced`: Fator de escala médio (2x).
- `fast`: Fator de escala agressivo (4x), acha encaixes mais rápido mas pode pular vãos pequenos muito estreitos.

### `allow_rotate`
Ativa as variantes rotacionadas discretas (essencial para encaixes de peças triangulares ou muito assimétricas).

## Tradeoffs

A principal vantagem dessa abordagem híbrida (NFP Raster + Gradient Gravity) é o **altíssimo nível de compactação** para formatos muito irregulares (como recortes de displays, letras em acrílico, tótens de chão), dispensando a implementação complexa (e pesada) do NFP vetorial via polígonos. A desvantagem é o alto consumo de memória para a geração dos arrays numpy temporários em imagens de altíssima resolução.

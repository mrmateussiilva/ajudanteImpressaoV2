# Studio de Impressao

Aplicacao desktop para operacao grafica focada em duas tarefas de alto impacto no dia a dia:

- montagem inteligente de arquivos para impressao em rolo
- corte padronizado de paineis com base em largura de placa e gabarito

Este projeto existe para transformar trabalho manual repetitivo em um fluxo mais rapido, mais consistente e mais confiavel.

## Visao

O `Studio de Impressao` nao foi pensado como uma "caixa de ferramentas generica".
Ele foi desenhado para ser um sistema operacional de pre-producao para um recorte especifico da rotina grafica.

A proposta e simples:

- reduzir decisao manual onde a regra ja e conhecida
- acelerar tarefas que consomem tempo operacional
- padronizar saidas para diminuir erro humano
- preparar a base para automacao e performance nativa no futuro

## Problema que o projeto resolve

Em muitos fluxos de producao grafica, duas etapas costumam consumir tempo desproporcional:

1. organizar imagens em layouts eficientes para impressao em rolo
2. dividir paines grandes em partes prontas para corte e producao

Essas tarefas normalmente misturam:

- acao manual repetitiva
- ajuste visual cansativo
- risco de inconsistencias
- retrabalho por configuracao errada

O projeto ataca exatamente esse ponto.

## O que o sistema faz hoje

### Rolo Packer

Processa imagens e monta layouts para impressao em rolo.

Capacidades atuais:

- leitura de imagens em lote
- limpeza de branco e recorte de bordas vazias
- ajuste de imagens para largura util do rolo
- classificação automática de tipo de produção (baseada em treinamento visual)
- rotulagem automática das imagens com identificação do material
- modo de rotulagem externa (não sobrepõe a arte)
- multiplos modos de encaixe
- geracao do canvas final de saida

### Cut Panel

Prepara cortes de painel a partir de largura de placa e gabarito.

Capacidades atuais:

- carga de imagem principal e gabarito
- corte manual baseado na largura da placa
- processamento em lote
- numeracao e identificacao das partes geradas

### Inteligência e Classificação

O sistema conta com um módulo de classificação automática para otimizar a identificação de materiais e avaliar a qualidade visual das imagens. O diferencial é que **não são utilizados modelos pesados de *Deep Learning***; a abordagem é baseada em extração de características visuais via **OpenCV** e inferência pelo algoritmo **KNN (K-Nearest Neighbors)**.

- **Treinamento Dinâmico em Memória**: O sistema não gera arquivos de pesos. Ele aprende carregando as imagens "referência" em tempo de execução. Basta adicionar pastas com exemplos nos diretórios de base:
  - `Z:\IMPRESSÃO DE TOTENS\treinamentos`: Treina o classificador de produção (ex: 3mm sp, 6mm cp).
  - `Z:\IMPRESSÃO DE TOTENS\qualidade`: Treina o classificador de qualidade (ex: boa, aceitável, ruim).
- **Extração de Características**:
  - *Proporção (Aspect Ratio)*: Relação largura/altura, muito importante para o classificador de produção.
  - *Nitidez (Sharpness)*: Calculada via variância Laplaciana (`cv2.Laplacian`), vital para o classificador de qualidade detectar imagens borradas.
  - *Histograma de Cores*: Uma assinatura visual baseada em distribuição de cores.
- **Processo de Classificação (Inferência)**: A nova imagem é comparada com a base em memória. O sistema aplica pesos diferentes (ex: prioriza nitidez para qualidade, prioriza proporção para produção). O algoritmo KNN pega os 3 exemplos matematicamente mais próximos e faz uma votação para eleger a categoria vencedora.
- **Rotulagem de Produção**: Cada imagem recebe uma etiqueta de identificação do tipo (ex: 3mm sp) em uma margem inferior dedicada.
- **Indicadores de Qualidade na UI**: O nível de qualidade (Boa, Aceitável, Ruim) é exibido visualmente nos cards de cada imagem dentro do programa, com codificação por cores para rápida conferência.

## O que ja foi feito

O projeto passou por uma limpeza estrutural importante para sair de um estado experimental e caminhar para algo mais profissional.

Ja foi concluido:

- reducao do escopo para os dois modulos realmente usados
- reorganizacao do codigo em camadas mais claras
- separacao entre interface, servicos e algoritmos
- remocao de modulos que desviavam do fluxo principal
- consolidacao da base Qt em uma estrutura mais organizada
- documentacao de roadmap

## O que ainda vai ser feito

O projeto ainda esta evoluindo.
As proximas etapas mais importantes sao:

- melhorar a consistencia da experiencia de uso
- adicionar benchmark dos algoritmos pesados
- validar gargalos reais com casos da operacao
- evoluir logs, previsibilidade e organizacao do fluxo

Documentacao futura:

- [docs/roadmap.md](./docs/roadmap.md)

## Filosofia

O projeto segue cinco principios:

### 1. Foco no uso real

Tudo deve servir ao fluxo que realmente gera trabalho.
Menos modulos, menos distração, mais resultado.

### 2. Automacao com clareza

Automatizar nao pode significar esconder a regra.
O operador precisa entender o que foi feito e confiar na saida.

### 3. Performance orientada a gargalo

O processamento pesado de imagens e geometria usa aceleração matemática (Numba/NumPy) em Python.

### 4. Estrutura antes de expansao

Antes de crescer funcionalidade, a base precisa ser legivel, separada e sustentavel.

### 5. Evolucao incremental

A forma correta de melhorar o sistema e:

1. medir
2. simplificar
3. isolar
4. substituir
5. validar

## Stack

### Stack atual

- `Python 3.13`
- `PySide6`
- `Pillow`
- `numpy`
- `uv`

## Arquitetura

O projeto esta organizado para separar interface, regra de aplicacao e algoritmos.

### Estrutura principal

- [`main.py`](./main.py)
  Entrada principal da aplicacao.
- [`ajudante_impressao/ui/`](./ajudante_impressao/ui)
  Janela principal, componentes e telas.
- [`ajudante_impressao/services/`](./ajudante_impressao/services)
  Fluxos de aplicacao e orquestracao dos modulos.
- [`ajudante_impressao/algorithms/`](./ajudante_impressao/algorithms)
  Processamento de imagem, packing e corte.

## Como rodar

Instale as dependencias:

```bash
uv sync
```

Execute a aplicacao:

```bash
uv run python main.py
```

Ou:

```bash
python main.py
```

## Desenvolvimento

### Validacao rapida

```bash
python -m py_compile main.py pyside_main.py pyside_theme.py pyside_rolo_packer.py pyside_cut_panel.py ajudante_impressao/__init__.py ajudante_impressao/ui/*.py ajudante_impressao/ui/screens/*.py ajudante_impressao/services/*.py ajudante_impressao/algorithms/*.py
```

### Documentacao tecnica

- [docs/packing-algorithm.md](./docs/packing-algorithm.md)
- [docs/roadmap.md](./docs/roadmap.md)

## Direcao do projeto

O objetivo de longo prazo e ter uma aplicacao que:

- mantenha o operador no controle
- reduza o tempo de pre-producao
- gere saidas mais consistentes
- escale melhor com volume

Em resumo: menos clique, menos retrabalho, mais previsibilidade.

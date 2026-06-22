# Contexto do Projeto: Studio de Impressão (Ajudante de Impressão V2)

Este documento serve como um guia abrangente e de alta fidelidade para orientar o desenvolvimento, manutenção e evolução do **Studio de Impressão** (também referenciado como **ajudanteImpressaoV2**). Ele descreve o propósito do projeto, a arquitetura de software, as regras de negócios, os algoritmos e a stack tecnológica atual e futura.

---

## 1. Visão Geral e Propósito do Projeto

O **Studio de Impressão** é uma aplicação desktop desenvolvida em Python e PySide6 de pré-produção gráfica. Seu objetivo primário é eliminar tarefas manuais repetitivas no fluxo diário de uma gráfica de grande formato, focando especificamente em duas tarefas altamente custosas:

1. **Rolo Packer**: Otimizar e automatizar o encaixe (nesting/packing) bidimensional inteligente de diversas artes/imagens dentro de um rolo de impressão de largura fixa, reduzindo drasticamente o desperdício de material.
2. **Cut Panel**: Dividir e fatiar painéis gráficos de grandes dimensões em partes menores prontas para a produção (corte e montagem), baseando-se na largura física das placas de substrato e na aplicação automática de gabaritos e marcações de sobreposição.

### Princípios de Design e Filosofia
* **Foco no Uso Real**: Apenas ferramentas de alto impacto na operação diária. O escopo é estritamente limitado aos módulos `Rolo Packer` e `Cut Panel`.
* **Automação com Clareza**: O operador deve compreender e ter visibilidade do que o sistema está fazendo, mantendo o controle das decisões finais.
* **Performance Híbrida**: O que não é gargalo computacional permanece em Python pela rapidez de desenvolvimento; o processamento pesado de imagens e geometria usa aceleração matemática (Numba/NumPy).
* **Evolução Incremental**: Modificações devem ser medidas, testadas e introduzidas progressivamente, mantendo fallbacks robustos.

---

## 2. Estrutura de Diretórios e Arquitetura

O projeto adota uma arquitetura em camadas bem definida, separando a lógica de apresentação (UI), a coordenação de fluxos de trabalho (Services) e as operações computacionais puras (Algorithms).

```text
ajudanteImpressaoV2/
├── pyproject.toml              # Dependências e metadados da aplicação (Python >= 3.13)
├── uv.lock                    # Arquivo de trava de dependências do UV
├── main.py                     # Ponto de entrada que executa o app
├── ajudante_impressao/         # Pacote principal da aplicação
│   ├── __init__.py
│   ├── algorithms/            # Algoritmos de processamento, classificação e encaixe geométrico
│   │   ├── __init__.py
│   │   ├── classifier.py      # Classificação de produção e qualidade via KNN e OpenCV
│   │   ├── cut.py            # Regras e fatiamento físico de placas (Cut Panel)
│   │   ├── image_ops.py       # Pré-processamento de imagens (trim, remoção de branco, cache)
│   │   └── packing.py         # Algoritmos de nesting/packing bidimensional (inclui JIT Numba)
│   ├── services/              # Orquestradores de fluxo (ligação entre UI e algoritmos)
│   │   ├── __init__.py
│   │   ├── cut_panel.py
│   │   └── roll_packer.py
│   └── ui/                    # Telas, widgets e estilos em PySide6
│       ├── __init__.py
│       ├── common.py          # Componentes customizados reutilizáveis da interface
│       ├── main_window.py     # Janela principal e controle de abas
│       ├── theme.py           # Sistema de estilo unificado (Dark/Light mode via QSS)
│       └── screens/           # Telas de controle específicas dos módulos
│           ├── __init__.py
│           ├── cut_panel.py   # Interface visual do Cut Panel
│           └── roll_packer.py  # Interface visual do Rolo Packer
├── docs/                      # Documentação técnica de desenvolvimento
│   ├── packing-algorithm.md
│   └── roadmap.md
```

---

## 3. Módulos e Funcionamento Detalhado

### 3.1. Rolo Packer

Este módulo processa lotes de imagens e as organiza de forma compacta em um canvas contínuo representando o rolo físico.

#### Fluxo de Pré-processamento de Imagens (`image_ops.py`)
1. **Transposição EXIF**: Ajusta a rotação automática original do arquivo.
2. **Normalização de Resolução**: Converte todas as imagens para **100 DPI** como padrão interno (`normalize_to_100dpi`), otimizando o consumo de memória física.
3. **Limpeza de Branco (`remove_white`)**: Identifica e remove fundos brancos (com ajustes de `threshold` e suavização de borda/`softness` usando operações vetorizadas de NumPy) para expor a transparência alfa real da arte.
4. **Corte de Bordas Vazias (`trim_empty_borders`)**: Remove áreas transparentes sobressalentes da imagem (`getbbox()`), obtendo a caixa delimitadora geométrica real da arte.
5. **Classificação Automática**: Realiza duas classificações usando **OpenCV** e **KNN (K-Nearest Neighbors)** em tempo de execução:
   * **Tipo de Produção**: Identifica o material/tipo de impressão (ex: `3mm sp`, `6mm cp`) baseado em imagens de treino armazenadas na rede local em `Z:\IMPRESSÃO DE TOTENS\treinamentos`.
   * **Avaliação de Qualidade**: Analisa a nitidez da imagem (usando a variância do operador Laplaciano via `cv2.Laplacian`) e o histograma de cores em 8x8x8 bins normalizados, comparando com imagens de treino em `Z:\IMPRESSÃO DE TOTENS\qualidade` para classificar o arquivo em `Boa`, `Aceitável` ou `Ruim`.
   * *Aprimoramento por Nome*: Se a pasta de categoria (ex: `3mm sp`) estiver contida no nome do arquivo, aplica-se um multiplicador redutor de distância (`name_boost = 0.05`), garantindo altíssima assertividade.
6. **Rotulagem de Produção (`add_label_to_image`)**: Insere o rótulo da categoria identificada na arte. Suporta múltiplos modos e posicionamentos dinâmicos selecionáveis na interface:
   * **Margem Externa (External)**: Cria uma borda transparente inferior (mais estreita e ajustada) posicionando o rótulo à Esquerda, Centro ou Direita.
   * **Sobreposição (Overlay)**: Desenha o rótulo diretamente sobre a imagem, economizando espaço de rolo, nos cantos: Direita Inferior, Esquerda Inferior, Direita Superior ou Esquerda Superior. Utiliza uma caixa branca de fundo sólido garantindo 100% de legibilidade sobre qualquer arte.
7. **Cache Local (`.ajudante_cache`)**: Para acelerar carregamentos sucessivos, as imagens processadas são salvas em uma pasta oculta `.ajudante_cache` dentro da pasta de origem. A chave de cache é um hash MD5 contendo o caminho absoluto, tamanho do arquivo, data de modificação e o valor do threshold de branco.

#### Algoritmos de Encaixe/Packing (`packing.py`)
O sistema oferece quatro estratégias distintas de montagem:
1. **Gallery (`gallery`)**: Organiza as imagens em linhas horizontais simples, ordenadas por área de forma decrescente, centralizando e alinhando verticalmente pelo topo da linha.
2. **Fast (`fast`)**: Algoritmo baseado em prateleiras (Shelf Packing) no qual as imagens são ordenadas de forma decrescente por altura e largura. Tenta posicionar na prateleira com melhor aproveitamento de espaço disponível (`Best Fit`).
3. **Compacto/Tight (`tight`)**: Algoritmo de encaixe bidimensional 2D Strip Packing baseado em um perfil de altura (`profile`). Percorre a largura do rolo com um espaçamento (`step`) fixo de busca, encontrando o menor topo resultante para a peça.
4. **Poligonal/Masked (`masked`)**: O algoritmo mais avançado do sistema.
   * Realiza uma busca geométrica precisa através da colisão direta de máscaras alfa em multi-escala (Coarse-to-fine).
   * Redimensiona o espaço usando o OpenCV (`cv2.matchTemplate`) para encontrar rapidamente regiões candidatas promissoras em resoluções mais baixas.
   * Realiza uma simulação física de "gravidade/empurrão" (`nudge_gravity`) para puxar as peças o máximo possível para baixo e para a esquerda, preenchendo todos os vazios e encaixando imagens dentro dos vãos livres de outras imagens maiores.
   * Suporta rotações automáticas configuráveis em múltiplos ângulos de busca dependendo do perfil de performance (`fast`: 90°, 180°, 270°; `balanced` e `quality` testam variações adicionais como 45° ou até de 15° em 15°).
   * Oferece suporte a lookahead (analisa até 5 peças consecutivas em lote para definir a melhor ordem de encaixe).

#### Geração do Output
* Constrói o canvas final compondo as imagens em suas posições geométricas usando um processo ultra otimizado.
* Devido à limitação do formato JPEG (dimensão máxima de 65.535px), se o rolo gerado ultrapassar **65.000 pixels de altura**, o serviço (`roll_packer.py`) automaticamente divide a imagem final em múltiplos arquivos (ex: `..._parte1.jpg`, `..._parte2.jpg`) e salva em disco com DPI setado para 100.

---

### 3.2. Cut Panel

Este módulo atua no fatiamento guiado de imagens de grandes dimensões (painéis) baseado nas larguras de chapas de substrato e na inserção de sobreposições para colagem física.

#### Mecânica de Corte (`cut.py`)
1. **Determinação dos Pontos de Corte**: A partir da largura física da placa (`plate_width_cm`) e do DPI da imagem, o sistema calcula os pontos exatos de divisão de largura.
2. **Margens de Costura/Sangria (`pad_cm`)**: Aplica uma expansão branca ao redor das placas fatiadas para simular a margem necessária para impressão física e posterior manipulação.
3. **Inserção do Gabarito (Template)**: Aplica uma imagem de gabarito nos cantos e extremidades da placa fatiada. Dependendo da posição física da placa no painel, o comportamento muda:
   * **Start (Primeira placa)**: Aplica o gabarito no início e insere o número da placa no canto oposto. Adiciona o nome do arquivo na base.
   * **Middle (Placas intermediárias)**: Insere marcas de encaixe duplo (em ambas as extremidades laterais) e numeração consecutiva das sobreposições.
   * **End (Última placa)**: Aplica o gabarito apenas no encerramento e a numeração correspondente.
4. **Contorno e Numeração**: Aplica uma fina borda preta de 1px ao redor da arte fatiada (`add_contour`) e renderiza os números indicadores em preto, com fontes e tamanhos dinâmicos proporcionais ao DPI da arte original.
5. **Processamento em Lote**: Permite processar pastas inteiras de painéis de forma automatizada usando as mesmas definições paramétricas de tamanho e sangria.

---

## 4. Estrutura e Estilização da Interface (PySide6)

A interface gráfica é moderna, intuitiva e segue uma estética robusta e profissional.

### Componentes de UI (`common.py`)
* Contém componentes customizados de input de dados (com validações visuais automáticas, sinalizando campos incorretos ou em branco na cor vermelha).
* Console de logs estilizado que suporta múltiplos níveis de cores (`muted` para informações menores, `info` para dados regulares, `ok` em verde claro para sucessos, `warn` em amarelo para alertas e `err` em vermelho para erros críticos).

### Temas e Design System (`theme.py`)
Possui estilos definidos via QSS (Qt Style Sheets) para os temas **Dark** (padrão) e **Light**:
* **Dark Theme Palette**: 
  * Background Principal: `#0F1117`
  * Cartões/Containers: `#1A1D27`
  * Inputs e Alternativos: `#12151F`
  * Destaques (Accent): `#00C2A8` (Verde turquesa elétrico moderno)
  * Textos: `#E8EAF0`
* Possui suporte visual para micro-interações, estados de foco estilizados em verde/turquesa e botões de ação bem evidentes.

---

## 5. Estratégias de Otimização e Performance

Como a aplicação manipula arquivos de imagem extremamente pesados que facilmente chegam a centenas de megabytes em memória, diversas técnicas de otimização de baixo nível foram empregadas:

1. **Compilação JIT via Numba**:
   * O arquivo `packing.py` detecta a presença da biblioteca `numba`.
   * Se ativa, as funções geométricas cruciais `_collides_jit` (colisão de matriz binária de pixels), `_nudge_gravity_jit` (empurrão gravitacional iterativo de matrizes) e `_evaluate_batch_jit` (avaliação matemática em lote de candidatos a encaixe) são executadas em código de máquina compilado de forma nativa e paralela, liberando o GIL (Global Interpreter Lock).
   * A composição final de imagens no canvas (`_blend_canvas_jit`) também é totalmente acelerada via Numba para misturar canais RGBA de forma instantânea.
2. **Multiprocessamento Paralelo (`ProcessPoolExecutor`)**:
   * O pré-processamento de novas imagens (transposição, normalização, remoção de fundo e classificação KNN) é executado de forma concorrente em subprocessos separados, dividindo a carga em todos os núcleos da CPU.
3. **Coleção de Lixo Ativa (`gc.collect`)**:
   * Executa a liberação manual de referências e limpeza de memória durante os fatiamentos do `Cut Panel` para evitar vazamentos de memória (Memory Leaks) em lotes volumosos.

---

## 6. Direções e Roadmap Técnico (Próximos Passos)

O projeto encontra-se em uma fase em que a arquitetura e os algoritmos em Python puro estão consolidados e testados. Os objetivos técnicos de longo prazo são:

1. **Benchmark Sistemático**: Medir precisamente o tempo e o consumo de memória dos algoritmos em Python (com e sem Numba JIT) com imagens reais muito grandes para criar uma linha de base estável.
2. **Refinamento Algorítmico**: Melhorar os algoritmos de packing, otimizando o heurístico e reduzindo processamento redundante em Python puro.
3. **Usabilidade e Logs**: Melhorar a observabilidade do processamento, expondo melhor os gargalos para o operador.

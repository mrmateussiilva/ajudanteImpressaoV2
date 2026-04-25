# Ajudante de Impressao

Aplicacao desktop para fluxo de producao grafica, agora padronizada em `PySide6`.

## Stack

- `PySide6` para interface desktop
- `Pillow` para processamento de imagens
- `numpy` para operacoes de empacotamento e mascara

## Ferramentas

- `Rolo Packer`
  Gera layouts para impressao em rolo, incluindo modo poligonal por mascara alfa.
- `Cut Panel`
  Faz corte manual por largura de placa e processamento em lote com gabarito.
- `Redimensionar`
  Redimensiona imagens em lote por percentual, largura em cm ou largura em px.
- `Acabamento`
  Adiciona contorno, area de pad e nome do cliente.
- `Automacao`
  Monitora uma pasta e executa resize ou corte automatico em novos arquivos.

## Executar

Instale as dependencias:

```bash
uv sync
```

Rode a aplicacao:

```bash
uv run python main.py
```

Ou, se preferir:

```bash
python main.py
```

## Estrutura

- [main.py](./main.py)
  Entrada principal da aplicacao.
- [`ajudante_impressao/ui/`](./ajudante_impressao/ui)
  Janela principal, tema e telas Qt.
- [`ajudante_impressao/services/`](./ajudante_impressao/services)
  Orquestracao de casos de uso da aplicacao.
- [`ajudante_impressao/algorithms/`](./ajudante_impressao/algorithms)
  Algoritmos e processamento de imagem.
- [`ajudante_impressao/pipeline.py`](./ajudante_impressao/pipeline.py)
  Workflow engine orientado por configuracao TOML.
- `pyside_*.py`, `*_service.py`, `*_processing.py`
  Shims de compatibilidade para a estrutura antiga.

## Documentacao Tecnica

- [docs/packing-algorithm.md](./docs/packing-algorithm.md)
  Descreve os modos de encaixe e o funcionamento do algoritmo por mascara alfa.

## Observacoes

- A interface legada em `CustomTkinter` foi removida do fluxo ativo.
- A entrada oficial do projeto agora usa apenas `PySide6`.
- O `Cut Panel` em Qt cobre o fluxo principal, mas o editor visual de guias do canvas antigo ainda nao foi reimplementado.

## Desenvolvimento

Validacao rapida de sintaxe:

```bash
python -m py_compile main.py pyside_main.py pyside_theme.py pyside_rolo_packer.py pyside_cut_panel.py pyside_image_resizer.py pyside_art_finisher.py pyside_automation.py
```

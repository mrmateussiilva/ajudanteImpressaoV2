# Reescrita do Projeto

## Problema Atual

O projeto funciona como um conjunto de ferramentas separadas em `PySide6`, cada uma com seu proprio fluxo.
Isso gera tres problemas principais:

- a automacao nao e o centro do sistema
- regras de negocio ficam espalhadas entre UI, services e scripts
- fica dificil montar um fluxo de producao declarativo por tipo de pedido

## Direcao da Reescrita

O sistema passa a ter um nucleo de workflow orientado por configuracao.

Camadas alvo:

1. `ajudante_impressao/config.py`
   Carrega e valida configuracoes TOML.
2. `ajudante_impressao/models.py`
   Define producoes, acoes e contratos do workflow.
3. `ajudante_impressao/actions.py`
   Executa acoes concretas como `resize`, `cut` e `finishing`.
4. `ajudante_impressao/pipeline.py`
   Orquestra a execucao encadeada por producao.
5. `auto.py`
   Vira uma CLI fina em cima do workflow engine.

## Migracao Planejada

Fase 1:

- consolidar o fluxo automatico por TOML
- tirar regra de orquestracao da UI
- manter os modulos de processamento existentes

Fase 2:

- adaptar as telas Qt para consumir o workflow engine
- substituir configuracoes manuais por presets de producao

Fase 3:

- adicionar validacoes de pedido, leitura de pasta de entrada e saida padronizada
- conectar o fluxo a monitoramento e processamento automatico por fila

## Meta do Projeto

O objetivo deixa de ser "ter varias ferramentas".
O objetivo passa a ser "receber um pedido e executar o fluxo de producao quase sem intervencao manual".

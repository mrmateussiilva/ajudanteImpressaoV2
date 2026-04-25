from __future__ import annotations

import tomllib
from pathlib import Path

from .models import ActionDefinition, ProductionDefinition, SUPPORTED_ACTION_TYPES, WorkflowConfig


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def load_workflow_config(config_path: Path) -> WorkflowConfig:
    if not config_path.is_file():
        raise FileNotFoundError(f"Arquivo de configuracao nao encontrado: {config_path}")

    with config_path.open("rb") as file:
        raw_config = tomllib.load(file)

    raw_productions = raw_config.get("productions")
    raw_actions = raw_config.get("actions")
    if not isinstance(raw_productions, dict) or not raw_productions:
        raise ValueError("O TOML precisa ter a secao [productions] com pelo menos uma producao.")
    if not isinstance(raw_actions, dict) or not raw_actions:
        raise ValueError("O TOML precisa ter a secao [actions] com pelo menos uma acao.")

    productions: dict[str, ProductionDefinition] = {}
    for production_name, payload in raw_productions.items():
        if not isinstance(payload, dict):
            raise ValueError(f"A producao {production_name!r} precisa ser uma tabela TOML.")
        actions = payload.get("actions")
        if not isinstance(actions, list) or not actions or not all(isinstance(item, str) and item.strip() for item in actions):
            raise ValueError(f"A producao {production_name!r} precisa definir uma lista 'actions' valida.")
        productions[_normalize_name(production_name)] = ProductionDefinition(
            name=production_name,
            actions=tuple(item.strip() for item in actions),
        )

    action_definitions: dict[str, ActionDefinition] = {}
    for action_name, payload in raw_actions.items():
        if not isinstance(payload, dict):
            raise ValueError(f"A acao {action_name!r} precisa ser uma tabela TOML.")
        action_type = payload.get("type")
        if not isinstance(action_type, str) or action_type.strip() not in SUPPORTED_ACTION_TYPES:
            supported = ", ".join(sorted(SUPPORTED_ACTION_TYPES))
            raise ValueError(f"A acao {action_name!r} precisa ter um 'type' valido. Tipos suportados: {supported}.")
        params = {key: value for key, value in payload.items() if key != "type"}
        action_definitions[action_name] = ActionDefinition(
            name=action_name,
            action_type=action_type.strip(),
            params=params,
        )

    for production in productions.values():
        for action_name in production.actions:
            if action_name not in action_definitions:
                raise ValueError(f"A producao {production.name!r} referencia a acao inexistente {action_name!r}.")

    return WorkflowConfig(
        config_path=config_path.resolve(),
        productions=productions,
        actions=action_definitions,
    )

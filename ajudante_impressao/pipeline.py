from __future__ import annotations

from pathlib import Path

from .actions import ActionRunner
from .config import load_workflow_config
from .models import ActionDefinition, ProductionDefinition, WorkflowConfig


class WorkflowEngine:
    def __init__(self, config: WorkflowConfig):
        self._config = config
        self._runner = ActionRunner(config_dir=config.config_path.parent)

    @classmethod
    def from_file(cls, config_path: Path) -> "WorkflowEngine":
        return cls(load_workflow_config(config_path))

    @property
    def productions(self) -> dict[str, ProductionDefinition]:
        return self._config.productions

    @property
    def actions(self) -> dict[str, ActionDefinition]:
        return self._config.actions

    def get_production(self, production_name: str) -> ProductionDefinition:
        normalized = production_name.strip().lower()
        if not normalized:
            raise ValueError("O tipo de producao nao pode ser vazio.")
        try:
            return self._config.productions[normalized]
        except KeyError as exc:
            available_types = ", ".join(sorted(self._config.productions))
            raise ValueError(
                f"Tipo de producao invalido: {production_name!r}. Tipos disponiveis: {available_types}."
            ) from exc

    def describe_production(self, production_name: str) -> list[ActionDefinition]:
        production = self.get_production(production_name)
        return [self._config.actions[action_name] for action_name in production.actions]

    def execute(self, production_name: str, source_path: Path, log_fn=print) -> Path:
        if not source_path.exists():
            raise FileNotFoundError(f"Caminho de entrada nao encontrado: {source_path}")

        production = self.get_production(production_name)
        current_path = source_path.resolve()
        log_fn(f"Producao: {production.name}")
        log_fn(f"Entrada inicial: {current_path}")

        for index, action_name in enumerate(production.actions, start=1):
            action = self._config.actions[action_name]
            log_fn(f"[{index}/{len(production.actions)}] Executando acao {action.name!r} ({action.action_type})")
            current_path = self._runner.run(action.action_type, current_path, action.params)
            log_fn(f"Saida atual: {current_path}")

        return current_path

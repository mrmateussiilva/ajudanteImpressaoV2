from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_ACTION_TYPES = frozenset({"resize", "cut", "finishing"})


@dataclass(slots=True, frozen=True)
class ActionDefinition:
    name: str
    action_type: str
    params: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ProductionDefinition:
    name: str
    actions: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class WorkflowConfig:
    config_path: Path
    productions: dict[str, ProductionDefinition]
    actions: dict[str, ActionDefinition]


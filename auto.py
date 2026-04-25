from __future__ import annotations

import argparse
from pathlib import Path

from ajudante_impressao.pipeline import WorkflowEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Executa uma cadeia de acoes de producao definida em TOML.")
    parser.add_argument("production", help="Nome da producao definida em [productions].")
    parser.add_argument("source", nargs="?", default=".", help="Arquivo ou pasta de entrada.")
    parser.add_argument(
        "--config",
        default="auto.toml",
        help="Arquivo TOML com a definicao das producoes e acoes.",
    )
    parser.add_argument(
        "--show-actions",
        action="store_true",
        help="Mostra as acoes da producao e encerra sem processar imagens.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    engine = WorkflowEngine.from_file(Path(args.config).resolve())

    if args.show_actions:
        actions = engine.describe_production(args.production)
        print(f"Producao: {engine.get_production(args.production).name}")
        for index, action in enumerate(actions, start=1):
            print(f"{index}. {action.name} ({action.action_type})")
        return

    final_path = engine.execute(args.production, Path(args.source).resolve())
    print(f"Processo finalizado. Resultado em: {final_path}")


if __name__ == "__main__":
    main()

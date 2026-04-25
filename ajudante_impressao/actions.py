from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from .algorithms.cut import build_cut_points_from_plate_width, process_cut_folder, process_cut_images
from .algorithms.finishing import finish_image_file, process_finishing_folder
from .algorithms.image_resize import process_resize_folder, resize_image_file


def resolve_optional_int(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"O campo {field_name!r} precisa ser inteiro.") from exc
    if resolved <= 0:
        raise ValueError(f"O campo {field_name!r} precisa ser maior que zero.")
    return resolved


def resolve_optional_float(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"O campo {field_name!r} precisa ser numerico.") from exc


def require_str(params: dict[str, Any], field_name: str) -> str:
    value = params.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"O campo {field_name!r} e obrigatorio.")
    return value.strip()


def require_float(params: dict[str, Any], field_name: str) -> float:
    value = resolve_optional_float(params.get(field_name), field_name)
    if value is None:
        raise ValueError(f"O campo {field_name!r} e obrigatorio.")
    if value <= 0:
        raise ValueError(f"O campo {field_name!r} precisa ser maior que zero.")
    return value


class ActionRunner:
    def __init__(self, config_dir: Path):
        self._config_dir = config_dir

    def run(self, action_type: str, source_path: Path, params: dict[str, Any]) -> Path:
        if action_type == "resize":
            return self._run_resize(source_path, params)
        if action_type == "finishing":
            return self._run_finishing(source_path, params)
        if action_type == "cut":
            return self._run_cut(source_path, params)
        raise ValueError(f"Tipo de acao nao suportado: {action_type}")

    def _run_resize(self, source_path: Path, params: dict[str, Any]) -> Path:
        mode = require_str(params, "mode")
        target_value = require_float(params, "target_value")
        destination_mode = require_str(params, "destination_mode")
        output_name = str(params.get("output_name", "AUTO_REDIMENSIONADAS")).strip() or "AUTO_REDIMENSIONADAS"

        if source_path.is_dir():
            process_resize_folder(
                folder=source_path,
                mode=mode,
                target_value=target_value,
                output_name=output_name,
                destination_mode=destination_mode,
            )
            return source_path if destination_mode == "overwrite" else source_path / output_name

        result = resize_image_file(
            file=source_path,
            mode=mode,
            target_value=target_value,
            output_name=output_name,
            destination_mode=destination_mode,
        )
        return source_path if destination_mode == "overwrite" else Path(result["save_path"])

    def _run_finishing(self, source_path: Path, params: dict[str, Any]) -> Path:
        output_name = str(params.get("output_name", "ACABAMENTO")).strip() or "ACABAMENTO"
        dpi_override = resolve_optional_int(params.get("dpi_override"), "dpi_override")
        side_mode = str(params.get("side_mode", "auto")).strip() or "auto"

        if source_path.is_dir():
            process_finishing_folder(
                folder=source_path,
                output_name=output_name,
                dpi_override=dpi_override,
                side_mode=side_mode,
            )
            return source_path / output_name

        result = finish_image_file(
            file=source_path,
            output_name=output_name,
            dpi_override=dpi_override,
            side_mode=side_mode,
        )
        return Path(result["save_path"])

    def _run_cut(self, source_path: Path, params: dict[str, Any]) -> Path:
        template_value = require_str(params, "template_path")
        template_path = self._resolve_config_path(template_value)
        if not template_path.is_file():
            raise FileNotFoundError(f"Gabarito nao encontrado: {template_path}")

        plate_width_cm = require_float(params, "plate_width_cm")
        pad_cm = require_float(params, "pad_cm")
        dpi_override = resolve_optional_int(params.get("dpi_override"), "dpi_override")

        if source_path.is_dir():
            with Image.open(template_path) as template_image:
                process_cut_folder(
                    folder_path=str(source_path),
                    template_image=template_image.copy(),
                    plate_width_cm=plate_width_cm,
                    pad_cm=pad_cm,
                    dpi_override=dpi_override,
                )
            return source_path / "PAINEL_CUT"

        return self._run_cut_for_file(source_path, template_path, plate_width_cm, pad_cm, dpi_override)

    def _run_cut_for_file(
        self,
        file_path: Path,
        template_path: Path,
        plate_width_cm: float,
        pad_cm: float,
        dpi_override: int | None,
    ) -> Path:
        with Image.open(template_path) as template_image, Image.open(file_path) as image:
            cut_points = build_cut_points_from_plate_width(image, plate_width_cm, dpi_override=dpi_override)
            output_dir, _ = process_cut_images(
                original_image=image.copy(),
                template_image=template_image.copy(),
                image_path=str(file_path),
                real_cut_points=cut_points,
                pad_cm=pad_cm,
                dpi_override=dpi_override,
            )
        return output_dir

    def _resolve_config_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self._config_dir / path).resolve()

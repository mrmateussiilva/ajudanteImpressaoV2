from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from cut_processing import build_cut_points_from_plate_width, process_cut_images
from image_resize_processing import resize_image_file
from image_utils import VALID_EXT


LogCallback = Callable[[str], None]


@dataclass(slots=True)
class ResizeAutomationConfig:
    mode: str
    target_value: float
    destination_mode: str
    output_name: str


@dataclass(slots=True)
class CutAutomationConfig:
    template_path: str
    plate_width_cm: float
    pad_cm: float
    dpi_override: int | None = None


@dataclass(slots=True)
class AutomationConfig:
    source_folder: str
    poll_interval: float
    action: str
    resize: ResizeAutomationConfig | None = None
    cut: CutAutomationConfig | None = None


def snapshot_files(folder: str) -> dict[str, tuple[int, int]]:
    base = Path(folder)
    snapshot: dict[str, tuple[int, int]] = {}
    for file in base.iterdir():
        if file.is_file() and file.suffix.lower() in VALID_EXT:
            stat = file.stat()
            snapshot[str(file)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def process_automation_file(config: AutomationConfig, file: Path) -> str:
    if config.action == "resize":
        assert config.resize is not None
        result = resize_image_file(
            file=file,
            mode=config.resize.mode,
            target_value=config.resize.target_value,
            output_name=config.resize.output_name,
            destination_mode=config.resize.destination_mode,
        )
        return f"Resize OK {result['file']} -> {result['width']}x{result['height']}px em {result['save_path']}"

    assert config.cut is not None
    with Image.open(config.cut.template_path) as template, Image.open(file) as image:
        cut_points = build_cut_points_from_plate_width(
            image,
            config.cut.plate_width_cm,
            dpi_override=config.cut.dpi_override,
        )
        output_dir, total_parts = process_cut_images(
            original_image=image.copy(),
            template_image=template.copy(),
            image_path=str(file),
            real_cut_points=cut_points,
            pad_cm=config.cut.pad_cm,
            dpi_override=config.cut.dpi_override,
        )
    return f"Corte OK {file.name} -> {total_parts} partes em {output_dir}"


def watch_folder(config: AutomationConfig, running_check: Callable[[], bool], log_fn: LogCallback) -> None:
    known_files = snapshot_files(config.source_folder)
    log_fn("Monitor iniciado. Arquivos atuais foram ignorados; so novos/alterados serao processados.")
    while running_check():
        try:
            current = snapshot_files(config.source_folder)
            for file_path, signature in current.items():
                if not running_check():
                    return
                if known_files.get(file_path) == signature:
                    continue
                known_files[file_path] = signature
                file = Path(file_path)
                log_fn(f"Detectado: {file.name}")
                try:
                    result = process_automation_file(config, file)
                    log_fn(result)
                except Exception as exc:
                    log_fn(f"ERRO {file.name}: {exc}")
            time.sleep(config.poll_interval)
        except Exception as exc:
            log_fn(f"ERRO no monitor: {exc}")
            time.sleep(2)

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PIL import Image
from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..algorithms.image_ops import VALID_EXT, _process_single_image, cm_to_px
from .roll_packer import (
    PERFORMANCE_PROFILES,
    RollerPackRequest,
    RollerPackResult,
    run_roll_packer,
)


@dataclass
class HotFolderConfig:
    input_folder: Path
    output_folder: Path
    largura_cm: float = 125.0
    margem_cm: float = 0.5
    espaco_cm: float = 0.3
    threshold: int = 245
    step_px: int = 8
    allow_rotate: bool = True
    performance_mode: str = "balanced"
    label_position: str = "external_bottom_right"
    inactivity_seconds: int = 15
    settle_seconds: int = 3
    group_by_material: bool = True
    move_processed: bool = True
    auto_generate_dxf: bool = True
    min_batch_count: int = 1


@dataclass
class PendingFileState:
    path: Path
    last_size: int = -1
    last_mtime: float = 0.0
    first_seen: float = field(default_factory=time.time)
    last_change: float = field(default_factory=time.time)
    settled_ticks: int = 0


class HotFolderWorker(QObject):
    log = Signal(str, str)
    status = Signal(str)
    file_detected = Signal(str)
    file_staged = Signal(dict)
    queue_cleared = Signal()
    roll_completed = Signal(object)
    stats_updated = Signal(dict)

    def __init__(self, config: HotFolderConfig):
        super().__init__()
        self.config = config
        self._running = False
        self._pending_files: dict[Path, PendingFileState] = {}
        self._staged_items: list[dict] = []
        self._processed_filepaths: set[Path] = set()
        self._last_staged_time: float = 0.0
        self._stats = {
            "received_count": 0,
            "rolls_generated": 0,
            "last_active": "Iniciando...",
        }
        self._timer: QTimer | None = None

    def start(self) -> None:
        self._running = True
        self.config.input_folder.mkdir(parents=True, exist_ok=True)
        self.config.output_folder.mkdir(parents=True, exist_ok=True)

        self.status.emit("MONITORANDO")
        self.log.emit(
            f"🟢 Agente iniciado. Monitorando pasta:\n    {self.config.input_folder}\n",
            "ok",
        )
        self.log.emit(
            f"📁 Pasta de saída de rolos:\n    {self.config.output_folder}\n",
            "info",
        )
        self.log.emit(
            f"⚙️ Trigger de inatividade: {self.config.inactivity_seconds}s | Estabilização: {self.config.settle_seconds}s\n\n",
            "muted",
        )

        self._timer = QTimer(self)
        self._timer.setInterval(1000)  # Checa a cada 1 segundo
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def stop(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.status.emit("PAUSADO")
        self.log.emit("\n⚪ Agente pausado pelo usuário.\n", "warn")

    def _is_valid_image_file(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.suffix.lower() not in VALID_EXT:
            return False
        name = path.name
        if name.startswith(".") or name.startswith("~$") or name.endswith(".tmp"):
            return False
        if ".ajudante_cache" in str(path) or "Processados" in str(path):
            return False
        return True

    def _can_read_exclusively(self, path: Path) -> bool:
        try:
            with open(path, "rb") as f:
                header = f.read(1024)
                return len(header) > 0
        except (PermissionError, OSError):
            return False

    def _scan_input_folder(self) -> None:
        try:
            for item in self.config.input_folder.iterdir():
                if self._is_valid_image_file(item):
                    if item not in self._pending_files and item not in self._processed_filepaths:
                        now = time.time()
                        stat = item.stat()
                        self._pending_files[item] = PendingFileState(
                            path=item,
                            last_size=stat.st_size,
                            last_mtime=stat.st_mtime,
                            first_seen=now,
                            last_change=now,
                            settled_ticks=0,
                        )
                        self.file_detected.emit(item.name)
                        self.log.emit(f"📥 Novo arquivo detectado: {item.name} ({stat.st_size / 1024:.1f} KB)\n", "info")
        except Exception as exc:
            self.log.emit(f"⚠ Erro ao escanear pasta de entrada: {exc}\n", "warn")

    def _check_pending_files(self) -> list[Path]:
        ready_files: list[Path] = []
        now = time.time()

        for path, state in list(self._pending_files.items()):
            if not path.exists():
                del self._pending_files[path]
                continue

            try:
                stat = path.stat()
                if stat.st_size == state.last_size and stat.st_mtime == state.last_mtime:
                    state.settled_ticks += 1
                else:
                    state.last_size = stat.st_size
                    state.last_mtime = stat.st_mtime
                    state.last_change = now
                    state.settled_ticks = 0

                # Arquivo considerado estável se não mudar por N segundos e puder ser lido
                if state.settled_ticks >= self.config.settle_seconds:
                    if self._can_read_exclusively(path):
                        ready_files.append(path)
                        del self._pending_files[path]
            except Exception:
                pass

        return ready_files

    def _preprocess_ready_file(self, path: Path) -> None:
        try:
            roll_px = cm_to_px(self.config.largura_cm)
            margin_px = cm_to_px(self.config.margem_cm)
            usable_w = max(1, roll_px - 2 * margin_px)

            proc_res = _process_single_image(
                file=path,
                max_width_px=usable_w,
                threshold=self.config.threshold,
            )

            item_data = proc_res.get("item")
            if not item_data:
                for log_line, lvl in zip(proc_res.get("logs", []), proc_res.get("levels", [])):
                    self.log.emit(f"    {log_line}\n", lvl)
                return

            self._staged_items.append(item_data)
            self._processed_filepaths.add(path)
            self._last_staged_time = time.time()

            self._stats["received_count"] += 1
            self._stats["last_active"] = datetime.now().strftime("%H:%M:%S")
            self.stats_updated.emit(self._stats)

            category = item_data.get("category", "Geral")
            cat_conf = item_data.get("category_confidence", 0.0)
            quality = item_data.get("quality", "N/A")
            qual_conf = item_data.get("quality_confidence", 0.0)

            conf_str = f" ({cat_conf:.0f}%)" if cat_conf > 0 else ""
            qual_str = f" ({qual_conf:.0f}%)" if qual_conf > 0 else ""

            self.file_staged.emit(item_data)
            self.log.emit(
                f"    ✂️ Recortado e classificado: {path.name}  🏷️ [{category}{conf_str}]  ★ [{quality.upper()}{qual_str}]\n",
                "ok",
            )
            self.log.emit(
                f"    📦 Fila atual: {len(self._staged_items)} arte(s) aguardando fechamento do rolo.\n",
                "muted",
            )
        except Exception as exc:
            self.log.emit(f"    ✗ Erro ao processar '{path.name}': {exc}\n", "err")

    def _pack_staged_batch(self) -> None:
        if not self._staged_items:
            return

        self.status.emit("PROCESSANDO")
        total_items = len(self._staged_items)
        self.log.emit(
            f"\n{'═' * 60}\n🚀 DISPARO AUTOMÁTICO: Fechando lote com {total_items} artes...\n{'═' * 60}\n",
            "ok",
        )

        groups: dict[str, list[dict]] = {}
        if self.config.group_by_material:
            for it in self._staged_items:
                cat = it.get("category", "Geral")
                groups.setdefault(cat, []).append(it)
        else:
            groups["Geral"] = list(self._staged_items)

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        generated_results: list[RollerPackResult] = []

        for category, items in groups.items():
            self.log.emit(
                f"\n▶ Montando rolo para categoria: [{category}] ({len(items)} artes)...\n",
                "info",
            )
            safe_cat = "".join(c if c.isalnum() or c in "-_" else "_" for c in category.lower())
            output_name = f"rolo_{safe_cat}_{int(self.config.largura_cm)}cm_{now_str}.jpg"

            req = RollerPackRequest(
                folder=self.config.output_folder,
                largura_cm=self.config.largura_cm,
                margem_cm=self.config.margem_cm,
                espaco_cm=self.config.espaco_cm,
                threshold=self.config.threshold,
                step_px=self.config.step_px,
                allow_rotate=self.config.allow_rotate,
                row_height_cm=18.0,
                output_name=output_name,
                performance_mode=self.config.performance_mode,
                label_position=self.config.label_position,
                label_date=datetime.now().strftime("%d/%m/%Y"),
            )

            res = run_roll_packer(
                request=req,
                log_fn=lambda txt, lvl="info": self.log.emit(txt, lvl),
                status_fn=lambda txt: self.status.emit(txt),
                image_items=items,
            )

            if res is not None:
                generated_results.append(res)
                self._stats["rolls_generated"] += 1
                self.roll_completed.emit(res)
                self.log.emit(
                    f"  ✓ Rolo [{category}] exportado com sucesso: {res.output_path.name}\n",
                    "ok",
                )

        # Mover arquivos processados para subpasta Processados_YYYY-MM-DD
        if self.config.move_processed:
            proc_folder = self.config.input_folder / f"Processados_{datetime.now():%Y-%m-%d}"
            proc_folder.mkdir(parents=True, exist_ok=True)
            for path in list(self._processed_filepaths):
                if path.exists() and path.parent == self.config.input_folder:
                    try:
                        dest = proc_folder / path.name
                        shutil.move(str(path), str(dest))
                    except Exception as e:
                        self.log.emit(f"  ⚠ Não foi possível mover '{path.name}': {e}\n", "muted")

        self._staged_items.clear()
        self._processed_filepaths.clear()
        self.queue_cleared.emit()
        self.stats_updated.emit(self._stats)
        self.status.emit("MONITORANDO")
        self.log.emit(f"\n✨ Lote concluído! Agente aguardando novas artes...\n\n", "ok")

    def _tick(self) -> None:
        if not self._running:
            return

        # 1. Escanear novos arquivos
        self._scan_input_folder()

        # 2. Verificar arquivos que já terminaram de gravar (estabilizados)
        ready = self._check_pending_files()
        for path in ready:
            self._preprocess_ready_file(path)

        # 3. Checar trigger de inatividade para fechar o lote
        if self._staged_items and len(self._pending_files) == 0:
            elapsed = time.time() - self._last_staged_time
            if elapsed >= self.config.inactivity_seconds and len(self._staged_items) >= self.config.min_batch_count:
                self._pack_staged_batch()

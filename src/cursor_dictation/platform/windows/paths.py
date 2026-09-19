from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    settings_file: Path
    vocabulary_file: Path
    history_file: Path
    logs_dir: Path
    models_dir: Path
    downloads_dir: Path

    @classmethod
    def from_environment(cls) -> AppPaths:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise RuntimeError("Windows did not provide the LOCALAPPDATA directory.")
        return cls.from_local_app_data(Path(local_app_data))

    @classmethod
    def from_local_app_data(cls, local_app_data: Path) -> AppPaths:
        root = local_app_data / "CursorDictation"
        return cls(
            root=root,
            settings_file=root / "settings.json",
            vocabulary_file=root / "vocabulary.txt",
            history_file=root / "history.jsonl",
            logs_dir=root / "logs",
            models_dir=root / "models",
            downloads_dir=root / "downloads",
        )

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

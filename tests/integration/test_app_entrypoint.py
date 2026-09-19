from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_smoke_entrypoint_starts_and_stops_without_model_or_network(tmp_path: Path) -> None:
    data_root = tmp_path / "smoke-data"
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["PYTHONPATH"] = str(Path("src").resolve())

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cursor_dictation",
            "--smoke-test",
            "--data-root",
            str(data_root),
        ],
        cwd=Path.cwd(),
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (data_root / "logs" / "cursor-dictation.log").is_file()
    assert not (data_root / "models" / "small.en").exists()

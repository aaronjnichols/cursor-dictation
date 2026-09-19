from __future__ import annotations

import os

if os.environ.get("CURSOR_DICTATION_RUN_WINDOWS_INTEGRATION") == "1":
    os.environ["QT_QPA_PLATFORM"] = "windows"
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

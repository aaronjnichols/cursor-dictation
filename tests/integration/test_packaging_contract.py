from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_pyinstaller_contract_bundles_runtime_resources_and_is_windowed() -> None:
    specification = Path("packaging/cursor-dictation.spec").read_text(encoding="utf-8")

    assert "assets/models/default-small-en.json" in specification
    assert "assets/icons/cursor-dictation.svg" in specification
    assert "THIRD_PARTY_NOTICES.md" in specification
    assert 'name="Cursor Dictation"' in specification
    assert "console=False" in specification
    assert '"cudnn64_9.dll"' in specification
    assert '"icuuc.dll"' in specification
    assert 'python_root / "LICENSE.txt"' in specification
    assert 'python_root / "Doc/html/license.html"' in specification
    assert '"licenses"' in specification
    assert "third_party/licenses" in specification
    assert '"ThirdPartyNotices.txt"' in specification
    assert '"soxr"' in specification
    assert '"av"' in specification
    assert "faster_whisper_numpy_audio.py" in specification
    assert '"libportaudio64bit.dll"' in specification


def test_pyinstaller_contract_removes_unrelated_build_host_dlls() -> None:
    specification = Path("packaging/cursor-dictation.spec").read_text(encoding="utf-8")
    package_script = Path("scripts/package.ps1").read_text(encoding="utf-8")

    assert '"codex-runtimes" in source_parts' in specification
    assert '"av.libs" in source_parts' in specification
    assert '"msvcp140.dll"' in specification
    assert '"libcrypto-3-x64.dll"' in package_script
    assert '"libssl-3-x64.dll"' in package_script


def test_third_party_notices_are_release_content_not_a_placeholder() -> None:
    notices = Path("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "placeholder" not in notices.lower()
    assert "| faster-whisper | 1.2.1 |" in notices
    assert "| PySide6, PySide6 Essentials, PySide6 Addons, Shiboken6 | 6.11.2 |" in notices
    assert "Systran/faster-whisper-small.en" in notices
    assert "| CPython runtime | 3.11.9 |" in notices
    assert "| OpenSSL | 3.0.13 |" in notices
    assert "| SQLite | 3.45.1 |" in notices
    assert "| PyInstaller bootloader | 6.22.3 |" in notices
    assert "| Python-SoXR and libsoxr | 1.1.0 / 0.1.3 |" in notices
    assert "| sounddevice | 0.5.6 |" in notices
    assert "| PortAudio | 19.7.0 |" in notices
    assert "| PyAV |" not in notices
    assert "BUNDLE-NATIVE-INVENTORY.txt" in notices


def test_explicit_runtime_license_files_are_checked_in() -> None:
    expected = {
        "CTranslate2-LICENSE.txt",
        "FlatBuffers-LICENSE.txt",
        "PyInstaller-COPYING.txt",
        "Qt-GPL-3.0-only.txt",
        "Qt-LGPL-3.0-only.txt",
        "Tokenizers-LICENSE.txt",
        "Intel-Simplified-Software-License.txt",
        "PortAudio-LICENSE.txt",
    }
    license_root = Path("third_party/licenses")

    assert {path.name for path in license_root.glob("*.txt")} == expected
    assert all((license_root / name).stat().st_size > 1_000 for name in expected)
    portaudio_license = (license_root / "PortAudio-LICENSE.txt").read_text(encoding="utf-8")
    assert "Copyright (c) 1999-2006 Ross Bencina and Phil Burk" in portaudio_license
    assert "PortAudio/portaudio/blob/v19.7.0/LICENSE.txt" in portaudio_license


def test_packaged_smoke_runs_from_an_isolated_temporary_copy() -> None:
    script = Path("scripts/package.ps1").read_text(encoding="utf-8")

    assert "[IO.Path]::GetTempPath()" in script
    assert "[guid]::NewGuid()" in script
    assert "Copy-Item -LiteralPath $bundle -Destination $smokeBundle -Recurse" in script
    assert "-WorkingDirectory $smokeBundle" in script
    assert "Remove-Item -LiteralPath $smokeRoot -Recurse -Force" in script


def test_packaged_smoke_restores_the_callers_qt_platform_environment() -> None:
    script = Path("scripts/package.ps1").read_text(encoding="utf-8")

    assert "$priorQtPlatform = $env:QT_QPA_PLATFORM" in script
    assert "Remove-Item Env:QT_QPA_PLATFORM" in script
    assert "$env:QT_QPA_PLATFORM = $priorQtPlatform" in script


def test_package_contract_excludes_unused_codec_and_portaudio_binaries() -> None:
    script = Path("scripts/package.ps1").read_text(encoding="utf-8")

    assert '"_internal\\av.libs"' in script
    assert '"libportaudio32bit.dll"' in script
    assert '"libportaudio64bit-asio.dll"' in script
    assert '-Filter "libportaudio*"' in script
    assert '$_.Name -ne "libportaudio64bit.dll"' in script
    assert '"BUNDLE-NATIVE-INVENTORY.txt"' in script
    assert '"soxr_ext*.pyd"' in script


def test_package_contract_rejects_embedded_test_and_build_modules() -> None:
    specification = Path("packaging/cursor-dictation.spec").read_text(encoding="utf-8")
    package_script = Path("scripts/package.ps1").read_text(encoding="utf-8")

    for module in (
        "fsspec.conftest",
        "pytest",
        "_pytest",
        "pluggy",
        "iniconfig",
        "pygments",
        "setuptools",
        "_distutils_hack",
    ):
        assert f'"{module}"' in specification
        assert f'"{module}"' in package_script

    assert "pyi-archive_viewer" in package_script
    assert "$forbiddenArchiveModules" in package_script
    assert '"_internal\\setuptools"' in package_script
    assert '"licenses\\PortAudio-LICENSE.txt"' in package_script


def test_frozen_audio_hook_keeps_faster_whisper_on_numpy_path() -> None:
    code = """
import runpy
import sys
import numpy as np

runpy.run_path(r"packaging/runtime_hooks/faster_whisper_numpy_audio.py")
from faster_whisper import WhisperModel
from faster_whisper.audio import pad_or_trim

assert WhisperModel is not None
assert "av" not in sys.modules
assert pad_or_trim(np.ones(2, dtype=np.float32), 4).shape == (4,)
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

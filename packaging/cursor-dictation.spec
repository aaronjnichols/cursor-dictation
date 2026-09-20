import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    copy_metadata,
    get_package_paths,
)


project_root = Path(SPECPATH).parent
python_root = Path(sys.base_prefix)

datas = [
    (
        str(project_root / "assets/models/default-small-en.json"),
        "assets/models",
    ),
    (
        str(project_root / "assets/icons/cursor-dictation.svg"),
        "assets/icons",
    ),
    (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "third_party/licenses"), "licenses"),
]
for runtime_license in (
    python_root / "LICENSE.txt",
    python_root / "Doc/html/license.html",
):
    if not runtime_license.is_file():
        raise FileNotFoundError(f"Required runtime license is missing: {runtime_license}")
    datas.append((str(runtime_license), "licenses"))
onnxruntime_root = Path(get_package_paths("onnxruntime")[1])
for onnxruntime_notice in ("LICENSE", "ThirdPartyNotices.txt"):
    source = onnxruntime_root / onnxruntime_notice
    if not source.is_file():
        raise FileNotFoundError(f"Required ONNX Runtime notice is missing: {source}")
    datas.append((str(source), "licenses/onnxruntime"))
binaries = []
hiddenimports = []

sounddevice_data_root = Path(get_package_paths("_sounddevice_data")[1])
portaudio_root = sounddevice_data_root / "portaudio-binaries"
for portaudio_file in ("libportaudio64bit.dll", "README.md"):
    source = portaudio_root / portaudio_file
    if not source.is_file():
        raise FileNotFoundError(f"Required PortAudio file is missing: {source}")
    datas.append((str(source), "_sounddevice_data/portaudio-binaries"))
datas.extend(collect_data_files("faster_whisper"))
binaries.extend(collect_dynamic_libs("ctranslate2"))

for distribution in (
    "certifi",
    "cffi",
    "charset-normalizer",
    "colorama",
    "ctranslate2",
    "faster-whisper",
    "filelock",
    "flatbuffers",
    "fsspec",
    "huggingface-hub",
    "idna",
    "numpy",
    "onnxruntime",
    "packaging",
    "protobuf",
    "pycparser",
    "PySide6",
    "PySide6-Addons",
    "PySide6-Essentials",
    "pywin32",
    "PyYAML",
    "requests",
    "shiboken6",
    "soxr",
    "sounddevice",
    "tokenizers",
    "tqdm",
    "typing-extensions",
    "urllib3",
):
    datas.extend(copy_metadata(distribution))

analysis = Analysis(
    [str(project_root / "src/cursor_dictation/__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(project_root / "packaging/runtime_hooks/faster_whisper_numpy_audio.py"),
    ],
    excludes=[
        "av",
        "fsspec.conftest",
        "pytest",
        "_pytest",
        "pluggy",
        "iniconfig",
        "pygments",
        "setuptools",
        "_distutils_hack",
    ],
    noarchive=False,
    optimize=0,
)

# Cursor Dictation supports CPU inference only, so the optional cuDNN binary
# from the CTranslate2 wheel is not shipped. Some developer shells put a
# third-party Poppler ICU ahead of Windows' ICU on PATH. Exclude that accidental
# capture so QtCore resolves the Windows 11 system ICU it was built against.
excluded_runtime_files = {
    "cudnn64_9.dll",
    "icudt78.dll",
    "icuuc.dll",
    "libcrypto-3-x64.dll",
    "libportaudio.dylib",
    "libportaudio32bit.dll",
    "libportaudio32bit-asio.dll",
    "libportaudio64bit-asio.dll",
    "libportaudioarm64.dll",
    "libportaudioarm64-asio.dll",
    "libssl-3-x64.dll",
}


def _comes_from_unrelated_build_runtime(item):
    source_path = Path(item[1])
    source_parts = {part.lower() for part in source_path.parts}
    return (
        "codex-runtimes" in source_parts
        or "av.libs" in source_parts
        or "av" in source_parts
    )


analysis.binaries = [
    item
    for item in analysis.binaries
    if Path(item[0]).name.lower() not in excluded_runtime_files
    and not _comes_from_unrelated_build_runtime(item)
]
analysis.datas = [
    item
    for item in analysis.datas
    if Path(item[0]).name.lower() not in excluded_runtime_files
    and not _comes_from_unrelated_build_runtime(item)
]

# Some developer shells add unrelated native toolchains to PATH. After those
# files are removed, supply only the Microsoft runtimes the frozen Python and
# CTranslate2 binaries actually need, from Windows and the selected CPython.
required_runtime_binaries = {
    "msvcp140.dll": Path(os.environ["WINDIR"]) / "System32/msvcp140.dll",
    "vcruntime140.dll": python_root / "vcruntime140.dll",
    "vcruntime140_1.dll": python_root / "vcruntime140_1.dll",
}
required_runtime_names = set(required_runtime_binaries)
analysis.binaries = [
    item for item in analysis.binaries if Path(item[0]).name.lower() not in required_runtime_names
]
for destination_name, source_path in required_runtime_binaries.items():
    if not source_path.is_file():
        raise FileNotFoundError(f"Required Microsoft runtime is missing: {source_path}")
    analysis.binaries.append((destination_name, str(source_path), "BINARY"))
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Cursor Dictation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / "assets/icons/cursor-dictation.ico"),
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Cursor Dictation",
)

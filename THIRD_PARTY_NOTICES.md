# Third-party notices

Cursor Dictation is proprietary internal software. The components below retain their own
licenses. Versions match `uv.lock` as of September 19, 2026. Full license and third-party
notice files are copied into the packaged application's `_internal\licenses` directory.

## Speech recognition and model delivery

| Component | Version | License | Source |
| --- | ---: | --- | --- |
| faster-whisper | 1.2.1 | MIT | <https://github.com/SYSTRAN/faster-whisper> |
| CTranslate2 | 4.8.2 | MIT | <https://github.com/OpenNMT/CTranslate2> |
| huggingface-hub | 0.36.2 | Apache-2.0 | <https://github.com/huggingface/huggingface_hub> |
| tokenizers | 0.23.2 | Apache-2.0 | <https://github.com/huggingface/tokenizers> |
| ONNX Runtime | 1.30.0 | MIT | <https://github.com/microsoft/onnxruntime> |

The recommended model is `Systran/faster-whisper-small.en`, licensed MIT and sourced from
<https://huggingface.co/Systran/faster-whisper-small.en>. It is downloaded on first run, not
embedded in the application. Cursor Dictation pins commit
`d1d751a5f8271d482d14ca55d9e2deeebbae577f` and verifies every required file against the
SHA-256 values in `assets/models/default-small-en.json` before activation.

## Desktop and audio runtime

| Component | Version | License | Source |
| --- | ---: | --- | --- |
| PySide6, PySide6 Essentials, PySide6 Addons, Shiboken6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | <https://code.qt.io/cgit/pyside/pyside-setup.git/> |
| Qt libraries distributed by PySide6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | <https://www.qt.io/licensing/open-source-lgpl-obligations> |
| sounddevice and PortAudio binaries | 0.5.6 | MIT | <https://github.com/spatialaudio/python-sounddevice> |
| Python-SoXR and libsoxr | 1.1.0 / 0.1.3 | LGPL-2.1-or-later | <https://github.com/dofuuz/python-soxr> |
| PFFFT, included in the SoXR extension | bundled with SoXR 1.1.0 | BSD-like | <https://bitbucket.org/jpommier/pffft/> |
| pywin32 | 312 | PSF | <https://github.com/mhammond/pywin32> |
| Intel OpenMP runtime included with CTranslate2 | bundled with 4.8.2 | Intel Simplified Software License | <https://www.intel.com/content/www/us/en/content-details/749362/intel-simplified-software-license-version-october-2022.html> |
| PyInstaller bootloader | 6.22.3 | GPL-2.0-or-later with bootloader exception | <https://pyinstaller.org/en/stable/license.html> |

The optional cuDNN library present in the upstream CTranslate2 wheel is excluded because this
application deliberately runs inference on CPU.

The source dependency graph includes PyAV because faster-whisper can decode media files. Cursor
Dictation only passes in-memory NumPy audio to faster-whisper. The frozen Windows package replaces
that unused file-decoding import with a small in-memory-only compatibility module and excludes
PyAV, FFmpeg, video codecs, and their native libraries. The package also excludes PortAudio builds
for macOS, 32-bit Windows, ARM64 Windows, and ASIO. It retains only the 64-bit non-ASIO PortAudio
DLL used by this application.

## Embedded language and Windows runtimes

| Component | Version | License | Source |
| --- | ---: | --- | --- |
| CPython runtime | 3.11.9 | Python Software Foundation License 2.0 and bundled component terms | <https://www.python.org/downloads/release/python-3119/> |
| OpenSSL | 3.0.13 | Apache-2.0 | <https://www.openssl.org/source/openssl-3.0.13/> |
| SQLite | 3.45.1 | Public domain | <https://www.sqlite.org/copyright.html> |
| libffi | bundled with CPython 3.11.9 | MIT | <https://github.com/libffi/libffi> |
| Microsoft Visual C++ runtime | 14.x | Microsoft distributable-code terms | <https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/> |

The packaged `licenses` directory contains the complete CPython license and CPython's
third-party license document. Those files include the applicable OpenSSL, libffi, and
Microsoft Windows binary-build terms. SQLite's source and binaries are dedicated to the
public domain. Build verification rejects native DLLs accidentally discovered in unrelated
developer-tool directories. Component-specific files cover CTranslate2, tokenizers,
FlatBuffers, Qt/PySide6, PyInstaller, ONNX Runtime, and ONNX Runtime's bundled native
dependencies. Wheel-supplied license files are retained beside their distribution metadata.
The package writes `_internal/licenses/BUNDLE-NATIVE-INVENTORY.txt` during each build. Release
verification rejects the unused PyAV/FFmpeg tree and checks the required CTranslate2, Intel OpenMP,
SoXR, PortAudio, Qt, ONNX Runtime, and tokenizers native files.

## Python runtime dependencies

| Component | Version | License |
| --- | ---: | --- |
| NumPy | 2.4.6 | BSD-3-Clause and bundled component licenses |
| PyYAML | 6.0.3 | MIT |
| filelock | 4.0.1 | MIT |
| fsspec | 2026.9.0 | BSD-3-Clause |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| requests | 2.34.2 | Apache-2.0 |
| certifi | 2026.7.22 | MPL-2.0 |
| charset-normalizer | 3.5.1 | MIT |
| idna | 3.20 | BSD-3-Clause |
| urllib3 | 2.8.0 | MIT |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| colorama | 0.4.6 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| flatbuffers | 25.12.19 | Apache-2.0 |
| protobuf | 7.36.2 | BSD-3-Clause |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.0 | BSD-3-Clause |

This notice is informational, not a substitute for the full license texts distributed with
the corresponding components.

# Bundled license sources

These verbatim license files accompany native/runtime code in the Windows package when the
upstream wheel does not supply a complete license file of its own.

| File | Component | Pinned source |
| --- | --- | --- |
| `CTranslate2-LICENSE.txt` | CTranslate2 4.8.2 | `https://raw.githubusercontent.com/OpenNMT/CTranslate2/v4.8.2/LICENSE` |
| `Tokenizers-LICENSE.txt` | tokenizers 0.23.2 | `https://raw.githubusercontent.com/huggingface/tokenizers/v0.23.2/LICENSE` |
| `FlatBuffers-LICENSE.txt` | FlatBuffers 25.12.19 | `https://raw.githubusercontent.com/google/flatbuffers/v25.12.19/LICENSE` |
| `Qt-LGPL-3.0-only.txt` | Qt/PySide6 6.11.2 | `https://raw.githubusercontent.com/pyside/pyside-setup/v6.11.2/LICENSES/LGPL-3.0-only.txt` |
| `Qt-GPL-3.0-only.txt` | GNU GPL incorporated by LGPL 3 | `https://raw.githubusercontent.com/pyside/pyside-setup/v6.11.2/LICENSES/GPL-3.0-only.txt` |
| `PyInstaller-COPYING.txt` | PyInstaller 6.22.3 bootloader | `https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.22.3/COPYING.txt` |
| `Intel-Simplified-Software-License.txt` | Intel OpenMP runtime bundled by CTranslate2 4.8.2 | `https://www.intel.com/content/www/us/en/content-details/749362/intel-simplified-software-license-version-october-2022.html` |

The package also copies `onnxruntime/LICENSE`, `onnxruntime/ThirdPartyNotices.txt`, and the
selected CPython runtime's `LICENSE.txt` and `Doc/html/license.html` during the build. The
SoXR wheel metadata contributes its LGPL 2.1, libsoxr, and PFFFT license files.

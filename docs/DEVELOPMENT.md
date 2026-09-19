# Development guide

## Toolchain

Cursor Dictation targets 64-bit Windows and CPython 3.11. The repository uses `uv` to create the
environment from `pyproject.toml` and `uv.lock`.

```powershell
uv sync
```

The application stack is PySide6 for the desktop interface, sounddevice and PortAudio for capture,
SoXR for band-limited sample-rate conversion, faster-whisper and CTranslate2 for local inference,
and Win32 APIs for global shortcuts and cursor delivery.

## Daily verification

The standard gate formats, lints, type-checks, and runs every deterministic test:

```powershell
.\scripts\verify.ps1
```

The equivalent individual commands are:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m "not live_audio and not live_model and not windows_integration"
```

New behavior should start with a failing test and land as a working vertical slice. Keep the core
controller free of Qt, audio, model, and Win32 imports. Put platform behavior behind the existing
adapters and test the pure decision first.

## Opt-in live checks

These tests are excluded from the normal gate because they open hardware or change desktop state.
Run the audio and Windows checks from a local interactive Windows session, not Remote Desktop or a
headless agent session.

```powershell
$env:CURSOR_DICTATION_RUN_LIVE_AUDIO = "1"
uv run pytest tests/live/test_live_audio.py -q

$env:CURSOR_DICTATION_RUN_WINDOWS_INTEGRATION = "1"
uv run pytest tests/live/test_windows_integration.py -q
```

The Windows integration test temporarily replaces the clipboard, exercises paste, and restores the
captured text, HTML, image, and file-list payload in `finally`.

To verify local inference with networking forced off, provide an installed model and a 16 kHz mono
PCM WAV fixture:

```powershell
$env:CURSOR_DICTATION_MODEL_PATH = "C:\path\to\small.en"
$env:CURSOR_DICTATION_AUDIO_FIXTURE = "C:\path\to\speech.wav"
uv run pytest tests/live/test_live_model.py -q
```

## Benchmark

The benchmark performs one warm-up and reports cold model load, median inference time, real-time
factor, output character count, and process memory. It never prints transcript text.

```powershell
uv run python scripts/benchmark_model.py `
  "C:\path\to\small.en" `
  "C:\path\to\speech.wav" `
  --runs 5
```

Record machine details, fixture duration, and the JSON result when using a benchmark as release
evidence.

## Package

```powershell
.\scripts\package.ps1
```

The build creates `dist\Cursor Dictation\Cursor Dictation.exe`. The script runs the full
deterministic gate, freezes a windowed one-folder app, copies the folder to a unique temporary
location, and runs `--smoke-test` there. The smoke path imports the frozen inference stack, creates
application data, confirms no model download occurred, validates required licenses and native
libraries, and rejects unrelated build-host DLLs.

The default model is not embedded. First run downloads the immutable revision and verifies every
required file against `assets/models/default-small-en.json` before activation.

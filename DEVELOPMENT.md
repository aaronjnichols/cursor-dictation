# Development

## Requirements

- Windows 11
- Python 3.11
- `uv`

## Setup

```powershell
uv sync --python 3.11
```

## Verify

```powershell
.\scripts\verify.ps1
```

The normal quality gate does not need a microphone, model download, active text field, or
network connection. Tests that touch those resources carry explicit markers and run through
separate commands.

## Run from source

```powershell
uv run cursor-dictation
```

The default model is not bundled with the source checkout. First-run setup downloads and
verifies it before the app can transcribe.


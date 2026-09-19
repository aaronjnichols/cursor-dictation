# Cursor Dictation

Cursor Dictation is a Windows tray app that records speech, transcribes it with a local
Whisper model, and puts the final text in the field that has focus. A separate mode copies
the transcript without typing it.

The project is under active development. See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
for the agreed scope and [DEVELOPMENT.md](DEVELOPMENT.md) for local setup.

## Privacy boundary

- Audio stays in memory and is not saved.
- Transcription runs locally.
- The app has no telemetry and no cloud transcription fallback.
- Transcript history is off by default.

## Development status

The current source is not yet a packaged release. Run the local quality gate with:

```powershell
.\scripts\verify.ps1
```


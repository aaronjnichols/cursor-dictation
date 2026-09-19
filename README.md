# Cursor Dictation

Cursor Dictation is a Windows tray app for local speech-to-text. It records into memory,
transcribes with a local Whisper model, and either inserts the final text at the active cursor or
copies it to the clipboard.

## Use the packaged app

1. Extract the whole `Cursor Dictation` folder. The executable needs the adjacent `_internal`
   folder.
2. Run `Cursor Dictation.exe`.
3. On first run, install the recommended `small.en` model and choose a microphone. The verified
   download is about 486 MB.
4. Leave the app in the system tray and dictate with a shortcut.

The default shortcuts are:

| Action | Shortcut |
| --- | --- |
| Hold to talk and insert | `Ctrl+Alt+Space` |
| Toggle recording and insert | `Ctrl+Alt+D` |
| Toggle recording and copy | `Ctrl+Alt+C` |
| Cancel | `Ctrl+Alt+Escape` |

Open Settings from the tray to change shortcuts, choose a microphone, test its level, select a
downloaded CTranslate2 model, edit personal vocabulary, or opt into local history and launch at
sign-in.

## Privacy boundary

- Audio stays in memory and is not saved.
- Transcription runs on the local CPU.
- The app has no telemetry and no cloud transcription fallback.
- Transcript history is off by default.
- Logs exclude audio, transcripts, vocabulary, clipboard contents, and document text.

## Build and verification

The agreed design is in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md). Developer setup
is in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), the code boundaries are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and current acceptance evidence is in
[docs/QA_STATUS.md](docs/QA_STATUS.md).

Run the deterministic quality gate with:

```powershell
.\scripts\verify.ps1
```

Build and smoke-test the unsigned, one-folder Windows distribution with:

```powershell
.\scripts\package.ps1
```

This is an internal test build. Windows may show a SmartScreen warning because the executable is
not code-signed.

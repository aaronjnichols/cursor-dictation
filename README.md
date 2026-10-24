# Cursor Dictation

Cursor Dictation is a Windows tray app for local speech-to-text. It records into memory,
transcribes with a local Whisper model, and either inserts the final text at the active cursor or
copies it to the clipboard, or saves it as a Markdown file.

## Download and use

Download the Windows ZIP from the
[latest GitHub release](https://github.com/aaronjnichols/cursor-dictation/releases/latest), then:

1. Verify the ZIP against the accompanying `.sha256` file.
2. Extract the whole `Cursor Dictation` folder. The executable needs the adjacent `_internal`
   folder.
3. Run `Cursor Dictation.exe`.
4. On first run, install the recommended `small.en` model and choose a microphone. The verified
   download is about 486 MB.
5. Leave the app in the system tray and dictate with a shortcut.

The default shortcuts are:

| Action | Shortcut |
| --- | --- |
| Hold to talk and insert | `Ctrl+Alt+Space` |
| Toggle recording and insert | `Ctrl+Alt+D` |
| Hold to talk and copy | `Ctrl+Alt+C` |
| Hold to talk and save Markdown | `Ctrl+Alt+M` |
| Cancel | `Ctrl+Alt+Escape` |

For insert, copy, and Markdown, hold the shortcut while speaking and release its final key
to transcribe. `Ctrl+Alt+D` remains the optional toggle shortcut for insertion.

Open Settings from the tray to change shortcuts, choose a microphone, test its level, select a
downloaded CTranslate2 model, edit personal vocabulary, or opt into local history and launch at
sign-in.

## Save dictation as Markdown

In Settings > Markdown, choose an existing destination folder. This can be a folder in an
Obsidian vault or any ordinary folder. Optionally enter YAML properties without the `---` lines:

```yaml
tags: [dictation]
type: voice-note
status: inbox
```

Hold `Ctrl+Alt+M` while speaking, then release M to transcribe and save. The tray also has a
**Record to Markdown** command. Change the shortcut under Settings > Hotkeys.
Each recording creates a UTF-8 file such as `Dictation 2026-09-19 12-30-00.md`, with the
properties between `---` lines followed by the transcription. Leave properties blank for
plain Markdown. Existing files are never overwritten; repeated timestamps get numbered suffixes.
This command does not copy or insert text. Markdown files are saved independently of the history
setting. If saving fails, use **Copy recovered text** in the tray to recover the transcript.

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

Release builds are currently unsigned. Windows may show a SmartScreen warning.

Release instructions are in [docs/RELEASING.md](docs/RELEASING.md).

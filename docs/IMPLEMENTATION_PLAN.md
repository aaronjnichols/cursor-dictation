# Cursor Dictation implementation plan

Status: Approved for implementation  
Date: 2026-09-19  
Initial target: Aaron's current Windows PC  
Repository: `C:\_code\cursor-dictation`

## 1. Purpose

Cursor Dictation is a Windows tray application that records speech on demand, transcribes it with a local Whisper model, and inserts the final text wherever the text cursor is currently focused. It also supports a record-and-copy mode that leaves the transcript on the clipboard.

The first release is a single-user build for direct testing on the target machine. The code should remain suitable for later internal distribution, but enterprise deployment work must not delay validation of the dictation experience.

## 2. Product principles

1. Audio and transcription stay local.
2. The application remains out of the way during normal use.
3. A completed transcript appears only after recording stops.
4. The user always has a visible recording, processing, or error state.
5. The application does not rewrite the user's words.
6. Failure must preserve the transcript whenever possible, usually by copying it to the clipboard.
7. Source code, settings, logs, and model storage remain inspectable.

## 3. Version-one scope

### 3.1 Included

- Windows-only tray application.
- English dictation.
- Local CPU inference with `faster-whisper` and CTranslate2 `int8`.
- Default `small.en` model downloaded during first-run setup.
- Custom local CTranslate2 Whisper model selection.
- Configurable hold-to-talk hotkey.
- Configurable toggle-recording hotkey.
- Configurable record-and-copy hotkey.
- Configurable cancel hotkey.
- Direct insertion at the field focused when transcription finishes.
- Tray-menu command for record and copy.
- Temporary clipboard use for reliable insertion, followed by clipboard restoration.
- Direct keystroke fallback when paste is unavailable.
- Windows-default or user-selected microphone.
- Microphone test and input-level display.
- Per-user vocabulary used as transcription context.
- Small recording and processing indicator.
- Optional sound cues.
- Optional local transcript history, disabled by default.
- Optional launch at Windows sign-in, disabled by default.
- Local diagnostic logs that exclude audio and transcript text.
- Folder-based PyInstaller build.

### 3.2 Excluded

- Cloud transcription or cloud fallback.
- Telemetry.
- Accounts, login, or subscriptions.
- Multiple languages.
- Translation.
- Spoken commands.
- Grammar correction, filler-word removal, or other rewriting.
- Live partial text insertion.
- Concurrent recordings or queued dictations.
- Audio retention.
- Built-in automatic updates.
- Installer, code signing, or enterprise software deployment.
- Special support for elevated applications.
- macOS or Linux support.
- Multiple inference backends such as ONNX, PyTorch Whisper, or `whisper.cpp`.

## 4. User experience

### 4.1 First run

1. Cursor Dictation opens a short setup window.
2. The setup window explains that speech recognition runs on the computer.
3. The user confirms the recommended English model and install location.
4. The application downloads the model to a temporary directory.
5. It verifies the pinned revision, required files, and SHA-256 hashes.
6. It atomically moves the verified model into the model directory.
7. The user selects or confirms the microphone and tests its level.
8. Setup finishes and the application moves to the tray.

An interrupted or failed download must not create a selectable model or replace a working model.

### 4.2 Hold-to-talk

1. The user places the cursor in any normal editable field.
2. The user holds the configured shortcut, initially `Ctrl+Alt+Space`.
3. A bottom-center indicator shows `Recording...`, elapsed time, and a small waveform.
4. The user releases the shortcut.
5. The indicator changes to `Transcribing locally...`.
6. The final transcript is pasted into the field focused at delivery time.
7. The application restores the previous clipboard contents.
8. The indicator closes after a short success state.

### 4.3 Toggle recording

1. The user presses the configured toggle shortcut, initially `Ctrl+Alt+D`.
2. Recording continues until the user presses the shortcut again.
3. Transcription and delivery follow the same path as hold-to-talk.

### 4.4 Record and copy

1. The user starts record-and-copy from its hotkey, initially `Ctrl+Alt+C`, or from the tray menu.
2. The application records and transcribes normally.
3. It leaves the final transcript on the clipboard and shows a brief `Copied` confirmation.
4. It does not inject text into the active application.

### 4.5 Cancel

- The cancel shortcut initially uses `Ctrl+Alt+Escape`.
- The tray menu also exposes `Cancel dictation`.
- Cancel discards in-memory audio immediately.
- A cancelled item is never delivered, copied, or written to history.

### 4.6 Busy behavior

Version one processes one dictation at a time. If the user attempts to record while transcription or delivery is active, the application rejects the request with a short busy cue and a visible `Transcribing` state. It does not queue the recording.

## 5. Visual direction

Cursor Dictation uses its own name and microphone icon, with a visual system derived from the installed OpenChamber dark theme.

### 5.1 Design tokens

| Token | Initial value | Use |
| --- | --- | --- |
| Background | `#151313` | Main application background |
| Raised surface | approximately `#211E1D` | Cards and settings sections |
| Popover surface | approximately `#2B2725` | Tray menu and floating indicator |
| Foreground | `#CECDC3` | Primary text and icons |
| Muted foreground | approximately `#9F9A92` | Help text and metadata |
| Primary | `#EDB449` | Active microphone, selected controls, progress |
| Border | approximately `#49413F` | Thin separators and outlines |
| Success | restrained green | Ready and verified states only |
| Corner radius | approximately `9px` | Controls, cards, and popovers |

Use compact Segoe UI-style typography, thin-line icons, sparse spacing, and restrained translucent treatment for floating surfaces. Do not copy the OpenChamber name or logo.

### 5.2 Surfaces

- **Tray menu:** Start Dictation, Record and Copy, Cancel Dictation, Settings, Quit.
- **Status indicator:** Bottom-center pill for recording, transcribing, copied, busy, and error states.
- **Settings window:** General, Hotkeys, Audio, Model, Vocabulary, History, About.
- **First-run setup:** Model download, verification, install location, and microphone setup.

The indicator must remain visible without following or covering the text cursor.

## 6. Technology stack

| Concern | Choice |
| --- | --- |
| Language | Python 3.11 |
| Desktop UI | PySide6 |
| Speech engine | `faster-whisper` |
| Inference runtime | CTranslate2, CPU `int8` |
| Audio capture | `sounddevice` and NumPy |
| Windows integration | `pywin32` and narrow `ctypes` wrappers where necessary |
| Project metadata | `pyproject.toml` |
| Dependency locking | `uv.lock`, managed with `uv` |
| Tests | `pytest` and Qt test helpers |
| Formatting and linting | Ruff |
| Type checking | mypy |
| Packaging | PyInstaller, one-folder build |
| Source control | Git, `main` branch |

`pyproject.toml` records the supported Python version and intended dependency ranges. `uv.lock` records the exact resolved dependency graph used by development and packaging. Both files belong in source control.

## 7. Architectural approach

Cursor Dictation is a modular monolith. It runs as one Windows process with a Qt main thread, an audio worker, and a transcription worker.

### 7.1 Thread model

| Execution lane | Responsibilities |
| --- | --- |
| Qt main thread | Tray icon, settings, overlay, hotkey event handling, state transitions, delivery coordination |
| Audio worker | Microphone stream, sample buffering, elapsed time, input levels |
| Transcription worker | Model loading, inference, segment collection, final transcript assembly |

Qt queued signals carry events between threads. Version one does not use `asyncio`.

The audio callback must do minimal work. It copies each input block into a bounded in-memory buffer and returns. It must never perform model inference, UI work, filesystem writes, or logging that can block audio capture.

### 7.2 State machine

Primary states:

```text
Starting
  -> FirstRunSetup
  -> LoadingModel
  -> Idle

Idle
  -> Recording
  -> SettingsOpen
  -> Error

Recording
  -> Transcribing
  -> Idle              on cancel
  -> Error

Transcribing
  -> Delivering
  -> Error

Delivering
  -> Idle
  -> ErrorWithTranscript

Error / ErrorWithTranscript
  -> Idle
  -> LoadingModel
  -> FirstRunSetup
```

Every external input becomes an event handled by the state machine. UI controls and hotkey handlers must not independently mutate application state.

Representative events:

- `ApplicationStarted`
- `SetupCompleted`
- `ModelLoadRequested`
- `ModelLoaded`
- `HoldHotkeyPressed`
- `HoldHotkeyReleased`
- `ToggleHotkeyPressed`
- `CopyRecordingRequested`
- `CancelRequested`
- `AudioBlockReceived`
- `RecordingCompleted`
- `TranscriptCompleted`
- `DeliveryCompleted`
- `OperationFailed`

### 7.3 Dependency direction

The `core` package owns states, events, value objects, and transition rules. It imports no Qt, Windows, audio, or model libraries.

Adapters implement narrow interfaces defined by the application layer. This permits deterministic tests with fake microphones, fake transcribers, fake hotkeys, and fake delivery targets.

## 8. Proposed repository layout

```text
cursor-dictation/
  pyproject.toml
  uv.lock
  README.md
  ARCHITECTURE.md
  DEVELOPMENT.md
  THIRD_PARTY_NOTICES.md
  .gitignore
  assets/
    icons/
    sounds/
  docs/
    IMPLEMENTATION_PLAN.md
  scripts/
    verify.ps1
    package.ps1
    benchmark_model.py
  src/
    cursor_dictation/
      __init__.py
      app.py
      core/
        events.py
        models.py
        state_machine.py
      application/
        controller.py
        ports.py
      audio/
        recorder.py
        sounddevice_recorder.py
      transcription/
        engine.py
        faster_whisper_engine.py
        model_manifest.py
        model_manager.py
      output/
        delivery.py
        clipboard.py
        keyboard.py
      platform/
        windows/
          foreground.py
          hotkeys.py
          startup.py
      settings/
        schema.py
        store.py
        vocabulary.py
        history.py
      ui/
        tray.py
        setup_window.py
        settings_window.py
        status_overlay.py
        theme.py
      diagnostics/
        logging.py
  tests/
    unit/
    integration/
    ui/
    fixtures/
```

This is a target layout, not a mandate to create empty modules. Add a module when its responsibility is implemented.

## 9. Core contracts

Use `typing.Protocol` for boundaries. Keep payloads as frozen dataclasses or similarly explicit types.

### 9.1 Audio recorder

```python
class AudioRecorder(Protocol):
    def list_devices(self) -> Sequence[AudioDevice]: ...
    def start(self, device_id: str | None) -> None: ...
    def stop(self) -> RecordedAudio: ...
    def cancel(self) -> None: ...
```

`RecordedAudio` contains the sample rate, channel count, duration, and in-memory sample array. It does not contain a disk path.

### 9.2 Transcription engine

```python
class TranscriptionEngine(Protocol):
    def load(self, model_path: Path) -> ModelInfo: ...
    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript: ...
```

The engine returns one final `Transcript`. Segment timing may be retained in memory for diagnostics and tests, but version one does not expose or persist it.

### 9.3 Text delivery

```python
class TextDelivery(Protocol):
    def insert_at_cursor(self, text: str) -> DeliveryResult: ...
    def copy_to_clipboard(self, text: str) -> DeliveryResult: ...
```

`DeliveryResult` records success, delivery method, recoverability, and a user-facing error code. It must not be written to logs with transcript text.

### 9.4 Settings store

```python
class SettingsStore(Protocol):
    def load(self) -> AppSettings: ...
    def save(self, settings: AppSettings) -> None: ...
```

Writes use a temporary file and atomic replacement. The settings schema contains an integer `schema_version` and explicit migrations.

## 10. Audio pipeline

### 10.1 Capture format

- Single channel.
- 16 kHz target sample rate.
- Floating-point samples for the transcription boundary.
- Device-native capture may be resampled when required.
- Audio remains in memory.

The recorder must report device changes and a missing-device condition. If a pinned device disappears, the application falls back to the current Windows default and notifies the user.

### 10.2 Recording limits

- Initial hard safety limit: 10 minutes per dictation.
- The overlay warns the user at 9 minutes.
- Reaching the limit stops and transcribes the captured audio.
- No silence-triggered automatic stop in version one.

### 10.3 Audio tests

Test with generated tones, silence, fixture speech, device removal, default-device change, zero-length capture, and the 10-minute limit without retaining real microphone audio in the repository.

## 11. Transcription pipeline

### 11.1 Default model

- Model family: Whisper English `small.en`.
- Runtime: CTranslate2 through `faster-whisper`.
- Device: CPU.
- Compute type: `int8`.
- Language: fixed to English.
- Task: transcription, never translation.

The implementation must pin the model repository to an exact immutable revision. The model manifest records the repository, revision, required files, expected SHA-256 hashes, display name, language, and approximate installed size.

### 11.2 Model download

1. Download only after an explicit first-run action or later user request.
2. Use a unique temporary directory below the model root.
3. Support progress reporting and cancellation.
4. Verify the complete file set and hashes.
5. Smoke-load the model before activation.
6. Atomically rename the verified directory into place.
7. Record installed manifest metadata beside the model.
8. Run inference from the local path with no remote lookup.

### 11.3 Custom model validation

A custom model picker accepts a local directory only. Validation checks:

- Required CTranslate2 model files exist.
- Configuration and tokenizer files parse.
- The model declares or supports English transcription.
- CTranslate2 can load the model on CPU.
- A short bundled fixture can be transcribed without an exception.

Failure leaves the existing model active.

### 11.4 Vocabulary

`vocabulary.txt` contains one term or short phrase per line. The application:

- Trims whitespace.
- Ignores blank lines.
- Removes exact duplicates while preserving order.
- Rejects control characters.
- Applies a documented maximum entry count and prompt length.
- Passes the resulting text as Whisper initial context.

Vocabulary affects model context only. It does not run search-and-replace after transcription.

### 11.5 Transcript assembly

- Fully consume the segment generator before reporting completion.
- Join segments with appropriate whitespace.
- Trim leading and trailing whitespace.
- Preserve the model's wording, capitalization, and punctuation.
- Do not call a language model or grammar service.
- Treat an empty result as a recoverable error rather than inserting blank text.

## 12. Windows integration

### 12.1 Global hotkeys

The Windows hotkey adapter owns registration and conflict detection.

- Toggle, copy, and cancel shortcuts may use `RegisterHotKey` when possible.
- Hold-to-talk requires press and release events, so it uses a narrowly scoped low-level keyboard hook.
- The hook performs no model, audio, UI, or filesystem work. It posts a typed event and returns.
- The settings screen validates each shortcut for duplicates and failed Windows registration.
- Changing a shortcut unregisters the old binding before activating the new one. A failed change restores the old binding.

### 12.2 Clipboard insertion

Normal insertion uses a clipboard transaction:

1. Snapshot common clipboard MIME formats through Qt.
2. Place the transcript on the clipboard.
3. Send the paste shortcut to the current foreground application.
4. Wait long enough for the target to request clipboard data.
5. Restore the prior clipboard snapshot if the clipboard still contains Cursor Dictation's payload.

The snapshot must cover text, HTML, images, and file URLs. Integration tests must prove restoration for those types. If the application cannot safely snapshot the clipboard, it should use direct Unicode keystrokes or fall back to record-and-copy rather than silently destroy clipboard data.

Record-and-copy intentionally leaves the transcript on the clipboard.

### 12.3 Direct keystroke fallback

The fallback sends Unicode input through Windows `SendInput`. It is suitable for short text and applications that reject paste. It must:

- Preserve line breaks.
- Avoid interpreting transcript characters as shortcut keys.
- Stop and copy the remaining text if injection fails.
- Never run automatically when the foreground window belongs to Cursor Dictation.

### 12.4 Foreground destination

Delivery targets the field focused when delivery begins, not the field focused when recording began. Before sending input, verify that Cursor Dictation's own settings or overlay does not own focus. If it does, copy the transcript and show a clear notice instead.

### 12.5 Launch at sign-in

The opt-in setting writes a per-user startup entry. Disabling it removes only the entry owned by Cursor Dictation. Startup launches the application directly to the tray.

## 13. Local data

Application data root:

```text
%LOCALAPPDATA%\CursorDictation\
  settings.json
  vocabulary.txt
  history.jsonl
  logs\
  models\
  downloads\
```

### 13.1 Settings

`settings.json` stores hotkeys, selected microphone, selected model, output preferences, feedback settings, history preference, startup preference, and schema version.

Never store secrets. Write through a temporary file followed by atomic replacement.

### 13.2 History

- Disabled by default.
- Stores timestamp, transcript text, and delivery mode only.
- Does not store audio, target application, window title, or cursor context.
- Keeps the 500 most recent records.
- Supports copying one record and clearing all records.
- Clearing history rewrites or removes only `history.jsonl`.

### 13.3 Logs

Use structured rotating logs with:

- Timestamp.
- Severity.
- Component.
- Stable event name.
- Error type and safe technical details.
- Durations, sample counts, model identifier, and state transitions.

Exclude transcript text, vocabulary contents, audio samples, clipboard contents, document titles, and typed field contents. Keep five files of at most 2 MB each.

## 14. Error handling

Errors use stable codes and actionable messages.

| Condition | Behavior |
| --- | --- |
| Microphone missing | Fall back to Windows default when possible; otherwise remain idle and open Audio settings |
| Microphone disconnected mid-recording | Stop capture, discard unusable audio, return to idle |
| Model missing | Open setup or Model settings |
| Model invalid | Keep the prior model active and show validation details |
| Download interrupted | Keep partial data in a temporary directory eligible for safe retry |
| Transcription fails | Preserve audio only until the failure is reported, then release it; never save it to disk |
| Clipboard snapshot fails | Try Unicode input or leave transcript on clipboard with a warning |
| Paste cannot be verified | Leave transcript on clipboard and report the fallback |
| Hotkey registration fails | Keep the previous working binding and identify the conflicting shortcut |
| Unexpected worker exception | Transition to Error, release resources, and allow retry without restarting when safe |

If a final transcript exists, an error path must expose a Copy action before discarding it.

## 15. Testing strategy

### 15.1 Unit tests

- Every valid and invalid state transition.
- Busy and cancel behavior.
- Settings validation and migrations.
- Atomic settings writes.
- Vocabulary parsing and prompt limits.
- Model manifest validation.
- Transcript assembly.
- History retention and clearing.
- Error-to-message mapping.

### 15.2 Adapter contract tests

Run the same behavior tests against fakes and real adapters where practical:

- Audio recorder contract.
- Transcription engine contract.
- Text delivery contract.
- Settings store contract.
- Hotkey service contract.

### 15.3 Windows integration tests

- Register, trigger, change, and unregister every hotkey type.
- Detect shortcut conflicts.
- Hold-to-talk key-down and key-up behavior.
- Clipboard preservation for text, HTML, image, and file-list payloads.
- Unicode injection with punctuation and line breaks.
- Launch-at-sign-in entry ownership.
- Foreground application changes during transcription.

Tests that manipulate the real clipboard must snapshot it before the test and restore it in `finally` cleanup.

### 15.4 Model tests

- Load the pinned default model from a local path.
- Transcribe a short bundled English fixture.
- Confirm no network access during local load and inference.
- Reject an invalid custom model directory.
- Preserve the active model after failed validation.

Do not store user recordings as fixtures. Use a purpose-recorded or permissively licensed sample with source and license documented.

### 15.5 UI tests

- First-run progression and failure recovery.
- Settings validation.
- Microphone test state.
- Model selection.
- Vocabulary editing.
- History disabled and enabled states.
- Overlay states and screen placement.
- Tray menu enable and disable rules.

### 15.6 Manual acceptance matrix

Test direct insertion and record-and-copy in:

- Notepad.
- A browser text field.
- Microsoft Word.

For each target, test short prose, punctuation, a paragraph break produced by natural model punctuation, technical vocabulary, clipboard restoration, focus changes during transcription, and cancellation.

### 15.7 Performance benchmark

On the target Intel Core i5-14400 machine with 16 GB RAM and no discrete GPU, record:

- Cold model load time.
- Warm model readiness time.
- Peak process memory.
- Transcription time for 10, 30, and 60 seconds of speech.
- Real-time factor.
- Time from recording stop to delivered text.

Initial target: median stop-to-text time no greater than 2 seconds for a normal sentence after the model is warm. Report the measured result even if it misses the target. Do not conceal a slower result by changing the benchmark.

## 16. Verification command

`scripts\verify.ps1` is the local quality gate. It must run, in order:

1. Ruff formatting check.
2. Ruff lint check.
3. mypy.
4. Unit and adapter tests.
5. Safe integration tests that do not require a live microphone or foreground application.

The script returns a nonzero exit code on any failure. Live-device, model-download, GUI, and foreground-application tests use explicit separate commands so the normal verification run remains deterministic.

## 17. Packaging

### 17.1 Build shape

Version one uses a PyInstaller one-folder build. The model is not bundled with the application.

The build must include:

- Python runtime.
- PySide6 and required Qt plugins.
- CTranslate2 native libraries.
- PyAV libraries required by `faster-whisper`.
- `sounddevice` and PortAudio.
- `pywin32` components.
- Cursor Dictation icons, sounds, and default model manifest.
- Third-party notices.

### 17.2 Build verification

Test the packaged application from a clean directory, outside the source checkout and virtual environment. Confirm that it does not import packages from the development environment.

Version one does not produce a signed installer. Updates replace the application folder while `%LOCALAPPDATA%\CursorDictation` remains intact.

## 18. Implementation sequence

### Phase 0: repository baseline

- Initialize Git on `main`.
- Add `pyproject.toml`, `uv.lock`, source package, test package, and scripts.
- Add Ruff, mypy, and pytest configuration.
- Create the verification script.
- Add the four agreed documentation files.

Exit criterion: a minimal application imports, verification passes, and a development tray icon can start and exit.

### Phase 1: core state and configuration

- Implement states, events, transition rules, and application controller.
- Implement settings schema, migrations, and atomic file store.
- Implement vocabulary and history stores.
- Build fake adapters for deterministic tests.

Exit criterion: state-machine and persistence tests pass without importing Qt, Windows APIs, audio libraries, or Whisper.

### Phase 2: tray shell and visual system

- Implement tray menu, settings shell, first-run shell, and status overlay.
- Encode the approved dark tokens in one theme module.
- Wire UI actions to application events.
- Add the app icon and optional sound cues.

Exit criterion: every application state can be demonstrated with fake services and matches the approved visual direction.

### Phase 3: audio and hotkeys

- Implement device enumeration, default-device behavior, capture, levels, cancellation, and limits.
- Implement global hotkeys, hold-key release detection, conflict checks, and rebinding.
- Connect recording events to the state machine.

Exit criterion: both recording modes and cancel work reliably with the live microphone while the UI stays responsive.

### Phase 4: model management and transcription

- Define and pin the default model manifest.
- Implement first-run download, progress, verification, atomic activation, and retry.
- Implement custom model validation.
- Implement the `faster-whisper` adapter and vocabulary context.
- Add fixture and offline-inference tests.

Exit criterion: a live recording produces a final local transcript with the network disabled after setup.

### Phase 5: delivery

- Implement clipboard snapshot, paste, ownership check, and restoration.
- Implement record-and-copy.
- Implement Unicode keystroke fallback.
- Add Windows integration tests.

Exit criterion: the transcript is delivered in Notepad, a browser text field, and Word without losing the prior clipboard contents.

### Phase 6: hardening and packaging

- Add structured rotating logs and safe error messages.
- Run performance benchmarks and tune worker counts and transcription options.
- Build the PyInstaller folder distribution.
- Test packaged startup, model setup, offline operation, and replacement-folder update behavior.
- Generate third-party notices from the locked dependency set and model metadata.

Exit criterion: the packaged application meets the complete acceptance checklist below on the target machine.

## 19. Acceptance checklist

Version one is complete only when all items pass:

- [ ] Starts as a tray application without a console window.
- [ ] Downloads and verifies the pinned default model on first run.
- [ ] Performs transcription without network access after setup.
- [ ] Records through the Windows default microphone.
- [ ] Records through a pinned microphone.
- [ ] Falls back safely if the pinned microphone disappears.
- [ ] Hold-to-talk starts on press and stops on release.
- [ ] Toggle recording starts and stops correctly.
- [ ] Cancel discards the active recording.
- [ ] A second recording request is rejected while busy.
- [ ] Final text inserts into Notepad.
- [ ] Final text inserts into a browser text field.
- [ ] Final text inserts into Microsoft Word.
- [ ] Record-and-copy works through both hotkey and tray menu.
- [ ] Normal insertion restores prior text, HTML, image, and file-list clipboard data.
- [ ] Delivery failure leaves the transcript available to copy.
- [ ] Personal vocabulary affects transcription context.
- [ ] A valid custom CTranslate2 model can be selected.
- [ ] An invalid custom model does not replace the working model.
- [ ] History is disabled by default.
- [ ] Enabling and clearing local history works.
- [ ] Logs contain no audio, transcript, vocabulary, clipboard, or document text.
- [ ] The interface remains responsive during capture and transcription.
- [ ] The status indicator shows recording, transcribing, busy, success, and error states.
- [ ] Launch at sign-in remains opt-in and starts directly to the tray.
- [ ] Automated verification passes.
- [ ] Timed benchmark results are recorded for the target machine.
- [ ] The packaged build runs outside the development environment.
- [ ] Third-party notices cover shipped code and model files.

## 20. Main risks and mitigations

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| CPU transcription is slower than expected | Dictation feels disruptive | Benchmark early; tune CTranslate2 threads and beam settings; keep a future faster-model option without adding it to version one UI |
| Clipboard restoration races the target application | Lost clipboard data or failed paste | Track clipboard ownership, delay restoration, test multiple payload types, and fall back safely |
| Low-level keyboard hook becomes unstable | Missed release events or stuck recording | Keep hook callback minimal, add watchdog state, test repeated press and release sequences, always expose cancel |
| Hotkeys conflict with other software | Recording cannot start | Validate registration, report conflicts, retain the prior working binding |
| Model download changes upstream | Verification fails or unreviewed files enter the app | Pin an immutable revision and hashes; never download an unpinned default model |
| Native libraries are missing from the package | Packaged build fails on a clean machine | Maintain an explicit PyInstaller spec and test outside the virtual environment |
| Audio callback blocks | Dropped samples | Use bounded buffers and no heavy work in the callback |
| Custom model consumes too much memory | Application crash or severe slowdown | Validate by smoke load, report estimated model class, retain the default model, and recover on load failure |
| History or logs expose dictated content | Privacy failure | History off by default; no transcript logging; tests inspect log output for forbidden data |

## 21. Deferred work

Reconsider these only after version-one usage produces evidence:

- Signed installer and managed internal deployment.
- Automatic updates and rollback.
- Additional local models or inference backends.
- Additional languages.
- Streaming preview.
- Overlapping recording and transcription.
- Better elevated-application behavior.
- Shared company vocabulary.
- Central configuration.
- Telemetry, even local-only metrics beyond diagnostic logs.

## 22. Decision record

| Decision | Choice |
| --- | --- |
| Initial audience | Single-user validation, with later internal use in mind |
| Platform | Windows only |
| Application shape | Tray utility with on-demand settings |
| Language | English only |
| Default model | Whisper `small.en`, CPU `int8` |
| Custom models | Local CTranslate2 Whisper directories only |
| Recording controls | Hold-to-talk and toggle |
| Output controls | Insert at cursor and record-and-copy |
| Transcript timing | Final result only |
| Rewriting | None |
| Spoken commands | None |
| Audio retention | None |
| Text history | Optional, off by default |
| Vocabulary | Per-user only |
| UI framework | PySide6 |
| Concurrency | Qt event loop plus worker threads; no `asyncio` |
| Architecture | Modular monolith with interface-backed adapters |
| Local storage | Inspectable files under `%LOCALAPPDATA%` |
| Dependency management | `pyproject.toml` and `uv.lock` |
| Packaging | PyInstaller one-folder build |
| Updates | Manual folder replacement in version one |
| Visual style | Cursor Dictation layout with OpenChamber-derived dark color and surface treatment |


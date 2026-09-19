# Architecture

## Runtime path

```text
hotkey or tray action
        |
        v
DictationRuntime -> DictationController -> SoundDeviceRecorder
        |                    |
        |                    v
        |           QtTranscriptionQueue -> FasterWhisperEngine
        |                                      |
        v                                      v
StatusOverlay                         local CTranslate2 model
                                             |
                                             v
                              WindowsTextDelivery -> focused app
```

`DictationController` owns the dictation state machine. It accepts ports for capture,
transcription, delivery, history, and observers. It does not import Qt or Windows APIs.

`ApplicationCoordinator` owns the process lifetime. It loads settings, manages first-run setup and
model switching, creates one runtime, controls global shortcuts, and closes UI and worker resources
in a fixed order.

## Threading

- The Qt owner thread handles windows, tray actions, clipboard access, controller transitions, and
  completion callbacks.
- PortAudio invokes a short capture callback that copies float samples, calculates the level, and
  enforces the hard recording limit.
- `QtTranscriptionQueue` runs one inference job at a time in a worker pool.
- `QtTaskRunner` performs model installation and model validation away from the UI thread.

Shutdown closes each queue before waiting and clears queued callbacks. A result that arrives after
Quit cannot reach delivery.

## Audio contract

The recorder returns mono, 16 kHz, float32 audio in memory. It first asks the selected device for
16 kHz capture. If the device rejects that rate, it captures at the device's advertised native rate
and uses SoXR's band-limited high-quality converter. A spectral regression test verifies that
content above the 8 kHz output band is attenuated.

Recordings stop at ten minutes. The overlay warns at nine minutes. If a pinned microphone is gone,
the recorder uses the current Windows default and the app displays and logs a content-free warning
once per process session.

## Model boundary

The recommended model manifest pins `Systran/faster-whisper-small.en` to one immutable commit and
lists the SHA-256 digest of every required file. Downloads stay in a staging directory until all
files verify, then activate with a same-volume rename. Interrupted staging directories are not
selectable models.

Custom models must be local CTranslate2 directories with the required model, configuration, and
tokenizer files. A smoke load succeeds before the active engine changes.

The frozen app supports NumPy audio arrays only. faster-whisper's optional media-file decoder is
replaced at freeze time with a small compatibility module, so the package does not carry PyAV,
FFmpeg, or unused video codecs.

## Delivery boundary

Normal insertion snapshots all advertised clipboard formats plus a deep copy of Qt image data. It
places an owned text payload on the clipboard, sends paste, waits for the target, and restores the
snapshot only while it still owns the temporary payload. If paste cannot run, Unicode `SendInput`
is the short-text fallback. A partial Unicode send copies only the unsent suffix and never repeats
characters already delivered.

Delivery failure retains the transcript in controller memory until the user copies or discards it.
Transcript text never enters diagnostics.

## Persistence

Settings, vocabulary, optional history, models, and logs live under each user's local application
data directory. Settings and vocabulary files use temporary-file replacement. A settings save that
also changes vocabulary rolls runtime state back when either write fails.

Version one does not provide a crash-atomic transaction across the two separate settings and
vocabulary files. A power loss between those atomic replacements can leave one new file and one old
file. Each file remains valid, and the next save reconciles them. A journaled multi-file transaction
is deferred until the app has evidence that this narrow window matters in practice.

History is disabled by default. Diagnostics use an allowlist of content-free fields and rotate at a
fixed size.

## Frozen distribution

PyInstaller creates an unsigned one-folder package. The spec supplies only the required Microsoft
runtime files, strips GPU libraries and build-host contamination, keeps one x64 non-ASIO PortAudio
DLL, and excludes PyAV and FFmpeg. Each build writes a native-file inventory and carries component
licenses under `_internal\licenses` or the component's `.dist-info\licenses` directory.

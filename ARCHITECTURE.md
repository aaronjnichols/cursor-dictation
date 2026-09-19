# Architecture

Cursor Dictation is one Windows process split into small modules around explicit interfaces.
The core package knows nothing about Qt, Windows APIs, microphones, or Whisper.

## Runtime lanes

- The Qt main thread owns windows, the tray icon, state transitions, and delivery.
- The audio adapter owns the `sounddevice` input stream and in-memory sample buffer.
- A transcription worker loads and runs the local `faster-whisper` model.

Qt queued signals move results back to the main thread. The audio callback only copies sample
blocks and calculates a level. It does not touch the UI, filesystem, or model.

## Dependency direction

`core` contains states and value objects. `application` coordinates ports defined as Python
protocols. Packages such as `audio`, `transcription`, `output`, `platform`, and `ui` implement
those ports.

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the full state model,
storage rules, and acceptance criteria.


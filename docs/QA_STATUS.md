# QA status

Status recorded September 19, 2026 on the current Windows development machine.

## Passed

- 265 deterministic tests pass. Four opt-in live tests remain deselected by the normal gate.
- Ruff formatting and lint pass.
- Strict mypy passes for all 49 source files.
- The lockfile resolves 52 packages without drift.
- A clean PyInstaller build runs its smoke test from a copied folder outside the checkout.
- The packaged smoke path imports faster-whisper without PyAV or FFmpeg and does not download a
  model.
- The package contains one x64 non-ASIO PortAudio DLL and no PyAV, FFmpeg, cuDNN, foreign-architecture
  PortAudio, ASIO, or unrelated developer-runtime DLLs.
- The package contains the native inventory and checked license files for the frozen runtime.
- The executable archive excludes pytest, build-only packaging modules, and their transitive
  dependencies; package verification inspects the archive on every clean build.
- Native global shortcut registration and release passed in the available Windows session.
- Unit and integration coverage includes state transitions, hotkey conflicts, hold ownership,
  capture limits, native-rate resampling, model transactions, offline-only engine arguments,
  clipboard MIME restoration, partial keyboard sends, settings rollback, shutdown races, and
  packaged startup.

## Still needs an interactive local desktop

The current automation session exposes only remote audio outputs and Windows refuses to move the
foreground window to the test field. Those environment limits prevent honest sign-off on:

- real default and pinned microphone capture;
- missing-device fallback with physical hardware;
- hold-to-talk release under normal desktop input;
- insert-at-cursor in Notepad, a browser field, and Microsoft Word;
- native text, HTML, image, and file-list clipboard restoration after a real paste;
- end-to-end first-run model download, network-off transcription, and measured stop-to-text time;
- benchmark results for 10, 30, and 60 second speech fixtures.

The opt-in tests and benchmark command for these checks are in
[DEVELOPMENT.md](DEVELOPMENT.md). Do not mark the implementation-plan acceptance checklist complete
until this local-desktop matrix passes.

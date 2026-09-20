# Releasing Cursor Dictation

Releases use semantic version tags and are built on GitHub's Windows runner. The tag, Python
package version, and application version must match.

1. Update the version in `pyproject.toml` and `src/cursor_dictation/__init__.py`.
2. Add `docs/releases/vMAJOR.MINOR.PATCH.md` with user-facing release notes.
3. Run `uv lock`, `uv run python scripts/check_release_version.py vMAJOR.MINOR.PATCH`, and
   `scripts\package.ps1`.
4. Commit and push the release changes to `main`.
5. Create and push the annotated tag:

   ```powershell
   git tag -a vMAJOR.MINOR.PATCH -m "Cursor Dictation vMAJOR.MINOR.PATCH"
   git push origin vMAJOR.MINOR.PATCH
   ```

Never move or reuse a tag after pushing it. If a tagged build fails, fix the issue and increment the
patch version.

The release workflow repeats the full deterministic gate, builds the one-folder Windows package,
runs the packaged smoke test, and publishes a ZIP plus its SHA-256 checksum to GitHub Releases.
The default Whisper model is downloaded and verified on first run; it is not included in the ZIP.

Release builds are unsigned. Test the downloaded release on an interactive Windows desktop before
broad distribution, including microphone selection, global hotkeys, insertion into common target
applications, and clipboard restoration.

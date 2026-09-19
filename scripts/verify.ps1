$ErrorActionPreference = "Stop"

uv run ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run mypy
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run pytest -m "not live_audio and not live_model and not windows_integration"
exit $LASTEXITCODE


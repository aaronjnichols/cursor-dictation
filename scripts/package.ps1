$ErrorActionPreference = "Stop"

.\scripts\verify.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run pyinstaller --noconfirm packaging\cursor-dictation.spec
exit $LASTEXITCODE


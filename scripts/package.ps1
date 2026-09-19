$ErrorActionPreference = "Stop"

.\scripts\verify.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run python scripts\build_icon.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run pyinstaller --clean --noconfirm packaging\cursor-dictation.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$bundle = Join-Path $PSScriptRoot "..\dist\Cursor Dictation"
$executable = Join-Path $bundle "Cursor Dictation.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Packaged executable was not created: $executable"
}
$bundleRoot = (Resolve-Path -LiteralPath $bundle).Path
$bundleLicenseRoot = Join-Path $bundle "_internal\licenses"
New-Item -ItemType Directory -Path $bundleLicenseRoot -Force | Out-Null
$nativeInventory = Get-ChildItem -LiteralPath $bundle -Recurse -File | Where-Object {
    $_.Extension -in ".dll", ".pyd"
} | ForEach-Object {
    $_.FullName.Substring($bundleRoot.Length + 1)
} | Sort-Object
$nativeInventory | Set-Content -LiteralPath (
    Join-Path $bundleLicenseRoot "BUNDLE-NATIVE-INVENTORY.txt"
) -Encoding utf8
$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) (
    "CursorDictationSmoke-" + [guid]::NewGuid().ToString("N")
)
$smokeBundle = Join-Path $smokeRoot "Cursor Dictation"
$smokeData = Join-Path $smokeRoot "data"
$hadQtPlatform = Test-Path Env:QT_QPA_PLATFORM
$priorQtPlatform = $env:QT_QPA_PLATFORM

New-Item -ItemType Directory -Path $smokeRoot | Out-Null
try {
    Copy-Item -LiteralPath $bundle -Destination $smokeBundle -Recurse
    $smokeExecutable = Join-Path $smokeBundle "Cursor Dictation.exe"
    $env:QT_QPA_PLATFORM = "offscreen"
    $quotedSmokeData = '"{0}"' -f $smokeData
    $process = Start-Process -FilePath $smokeExecutable `
        -ArgumentList "--smoke-test", "--data-root", $quotedSmokeData `
        -WorkingDirectory $smokeBundle -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(20000)) {
        Stop-Process -Id $process.Id -Force
        throw "Packaged smoke test did not exit within 20 seconds."
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) {
        throw "Packaged smoke test failed with exit code $($process.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $smokeData "logs\cursor-dictation.log"))) {
        throw "Packaged smoke test did not create its application log."
    }
    if (Test-Path -LiteralPath (Join-Path $smokeData "models\small.en")) {
        throw "Packaged smoke test unexpectedly downloaded a model."
    }
    foreach ($forbiddenDirectory in @("_internal\av", "_internal\av.libs")) {
        if (Test-Path -LiteralPath (Join-Path $smokeBundle $forbiddenDirectory)) {
            throw "The package contains the unused PyAV/FFmpeg runtime: $forbiddenDirectory"
        }
    }
    $forbiddenRuntimeFiles = @(
        "cudnn64_9.dll",
        "icudt78.dll",
        "icuuc.dll",
        "libcrypto-3-x64.dll",
        "libssl-3-x64.dll",
        "libportaudio32bit.dll",
        "libportaudio32bit-asio.dll",
        "libportaudio64bit-asio.dll",
        "libportaudioarm64.dll",
        "libportaudioarm64-asio.dll"
    )
    foreach ($forbiddenName in $forbiddenRuntimeFiles) {
        if (Get-ChildItem -LiteralPath $smokeBundle -Recurse -File -Filter $forbiddenName) {
            throw "The package contains an excluded build-host runtime: $forbiddenName"
        }
    }
    $unexpectedPortAudio = Get-ChildItem -LiteralPath $smokeBundle -Recurse -File `
        -Filter "libportaudio*" | Where-Object { $_.Name -ne "libportaudio64bit.dll" }
    if ($unexpectedPortAudio) {
        throw "The package contains a non-x64 or ASIO PortAudio runtime."
    }
    foreach ($licensePath in @(
        "licenses\LICENSE.txt",
        "licenses\license.html",
        "licenses\CTranslate2-LICENSE.txt",
        "licenses\FlatBuffers-LICENSE.txt",
        "licenses\Tokenizers-LICENSE.txt",
        "licenses\Qt-LGPL-3.0-only.txt",
        "licenses\Qt-GPL-3.0-only.txt",
        "licenses\PyInstaller-COPYING.txt",
        "licenses\Intel-Simplified-Software-License.txt",
        "licenses\BUNDLE-NATIVE-INVENTORY.txt",
        "licenses\onnxruntime\LICENSE",
        "licenses\onnxruntime\ThirdPartyNotices.txt"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $smokeBundle "_internal\$licensePath"))) {
            throw "The package is missing required runtime license: $licensePath"
        }
    }
    $soxrMetadata = Get-ChildItem -LiteralPath (Join-Path $smokeBundle "_internal") `
        -Directory -Filter "soxr-*.dist-info" | Select-Object -First 1
    if ($null -eq $soxrMetadata) {
        throw "The package is missing SoXR distribution metadata."
    }
    foreach ($soxrLicense in @(
        "COPYING.LGPL",
        "LICENSE-libsoxr.txt",
        "LICENSE-PFFFT.txt",
        "LICENSE.txt"
    )) {
        $licensePath = Join-Path $soxrMetadata.FullName ("licenses\" + $soxrLicense)
        if (-not (Test-Path -LiteralPath $licensePath)) {
            throw "The package is missing required SoXR license: $soxrLicense"
        }
    }
    foreach ($requiredNativePattern in @(
        "ctranslate2.dll",
        "libiomp5md.dll",
        "soxr_ext*.pyd",
        "libportaudio64bit.dll",
        "Qt6Core.dll",
        "onnxruntime.dll",
        "tokenizers.pyd"
    )) {
        if (-not (Get-ChildItem -LiteralPath $smokeBundle -Recurse -File -Filter $requiredNativePattern)) {
            throw "The package is missing required native runtime: $requiredNativePattern"
        }
    }
}
finally {
    if ($hadQtPlatform) {
        $env:QT_QPA_PLATFORM = $priorQtPlatform
    }
    else {
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $smokeRoot) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force
    }
}

Write-Output "Package verified: $executable"

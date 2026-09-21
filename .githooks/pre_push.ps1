<#
.SYNOPSIS
    Full local gate executed before every git push.
#>

param ()

$ErrorActionPreference = "Stop"
$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location -LiteralPath $repoRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Stop-Hook([string]$Message) {
    Write-Host "[PRE-PUSH BLOCKED] $Message" -ForegroundColor Red
    exit 1
}

$gate = Join-Path $repoRoot "pre_review_checks.ps1"
if (-not (Test-Path -LiteralPath $gate)) {
    Stop-Hook "pre_review_checks.ps1 fehlt."
}

$pytestTempRoot = Join-Path $repoRoot (".pytest-push-{0}" -f [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $pytestTempRoot -Force | Out-Null
$pytestBase = Join-Path $pytestTempRoot "base"
& python -m pytest -q --basetemp $pytestBase
$pytestExit = $LASTEXITCODE
Remove-Item -LiteralPath $pytestTempRoot -Recurse -Force -ErrorAction SilentlyContinue
if ($pytestExit -ne 0) {
    Stop-Hook "Die isolierte pytest-Suite ist fehlgeschlagen."
}

# The review gate runs all remaining checks; pytest was already run above with
# the exact same interpreter and an isolated base directory.
& pwsh -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $gate -NoTranscript -NoArtifacts -SkipPytest
if ($LASTEXITCODE -ne 0) {
    Stop-Hook "Das vollstaendige Review-Gate ist fehlgeschlagen."
}

# The local gate keeps the legacy full-tree mypy report informative. The
# focused CI scope is nevertheless a blocking release check here as well.
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Stop-Hook "Python ist fuer den fokussierten mypy-Check nicht verfuegbar."
}
& python -m mypy --ignore-missing-imports --no-strict-optional --follow-imports=silent --warn-return-any `
    src/benchmark_config.py src/csv_writer.py
if ($LASTEXITCODE -ne 0) {
    Stop-Hook "Der fokussierte mypy-Check ist fehlgeschlagen."
}

Write-Host "[PRE-PUSH] Vollstaendige Suite und fokussierter mypy-Check bestanden." -ForegroundColor Green
exit 0

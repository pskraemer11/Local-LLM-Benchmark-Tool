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

# No Skip* switches: pre-push is the complete local safety net. Artifacts are
# temporary because the commit is already created when pre-push runs.
& pwsh -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $gate -NoTranscript -NoArtifacts
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

<#
.SYNOPSIS
    Fast staged-content gate executed before every commit.
#>

param ()

$ErrorActionPreference = "Stop"
$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location -LiteralPath $repoRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Stop-Hook([string]$Message) {
    Write-Host "[PRE-COMMIT BLOCKED] $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Hook "$FilePath fehlgeschlagen (Exit-Code $LASTEXITCODE)."
    }
}

$staged = @(git diff --cached --name-only --diff-filter=ACMR)
if ($LASTEXITCODE -ne 0) {
    Stop-Hook "Staged-Dateien konnten nicht ermittelt werden."
}
if ($staged.Count -eq 0) {
    Write-Host "[PRE-COMMIT] Keine staged Dateien; nichts zu pruefen." -ForegroundColor Yellow
    exit 0
}

# Whitespace errors are cheap to detect and often indicate an accidental edit.
$diffCheck = @(git diff --cached --check)
if ($LASTEXITCODE -ne 0 -or $diffCheck.Count -gt 0) {
    $diffCheck | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    Stop-Hook "Staged-Diff enthaelt Whitespace- oder Konfliktfehler."
}

# Never allow common credential/container formats into the repository.
$blockedFiles = @(
    $staged | Where-Object {
        $_ -match '(^|/)\.env(\..*)?$' -or
        $_ -match '(^|/)(id_rsa|id_ed25519)(\..*)?$' -or
        $_ -match '\.(pem|key|p12|pfx)$' -or
        $_ -match '(^|/)(credentials|secrets)[^/]*\.(json|ya?ml|toml)$'
    }
)
if ($blockedFiles.Count -gt 0) {
    $blockedFiles | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Stop-Hook "Staged-Datei sieht nach Zugangsdaten oder privatem Schluessel aus."
}

# High-confidence token patterns are checked only in added lines. Values are
# never printed, so a failed check cannot disclose the secret in the console.
$stagedDiff = @(git diff --cached --unified=0 -- @staged)
$addedLines = @($stagedDiff | Where-Object { $_ -match '^\+(?!\+\+\+)' })
$secretPatterns = @(
    'ghp_[A-Za-z0-9]{20,}',
    'github_pat_[A-Za-z0-9_]{20,}',
    'sk-[A-Za-z0-9]{20,}',
    'Bearer\s+[A-Za-z0-9._-]{30,}',
    'UNSLOTH_API_KEY\s*=\s*["'']?[A-Za-z0-9_-]{20,}'
)
foreach ($pattern in $secretPatterns) {
    if ($addedLines -match $pattern) {
        Stop-Hook "Moegliches Secret im staged Diff erkannt."
    }
}

$pythonFiles = @($staged | Where-Object { $_ -match '\.py$' })
if ($pythonFiles.Count -gt 0) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Stop-Hook "Python 3.12 ist fuer Python-Pruefungen nicht verfuegbar."
    }
    if (-not (Get-Command ruff -ErrorAction SilentlyContinue)) {
        Stop-Hook "ruff ist fuer den Pre-Commit-Check nicht verfuegbar."
    }
    Invoke-Checked "ruff" @("check", "--no-fix", "--", $pythonFiles)
    $compileArgs = @("-m", "py_compile") + $pythonFiles
    Invoke-Checked "python" $compileArgs
}

$yamlFiles = @($staged | Where-Object { $_ -match '\.(ya?ml)$' })
if ($yamlFiles.Count -gt 0) {
    $yamlCode = 'import sys; from pathlib import Path; from ruamel.yaml import YAML; y=YAML(typ="safe"); [y.load(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:]]'
    $yamlArgs = @("-c", $yamlCode) + $yamlFiles
    Invoke-Checked "python" $yamlArgs
}

$jsonFiles = @($staged | Where-Object { $_ -match '\.json$' })
if ($jsonFiles.Count -gt 0) {
    $jsonCode = 'import sys, json; from pathlib import Path; [json.loads(Path(p).read_text(encoding="utf-8-sig")) for p in sys.argv[1:]]'
    $jsonArgs = @("-c", $jsonCode) + $jsonFiles
    Invoke-Checked "python" $jsonArgs
}

if ($staged -contains "doc-git/model_registry.yaml") {
    Invoke-Checked "python" @("src/registry_tool.py", "validate", "--ci")
}

# A registry/provider change gets a focused regression test before commit.
$needsRegistryTest = $staged -contains "src/registry_tool.py" -or
    $staged -contains "tests/test_registry_tool.py" -or
    $staged -contains "doc-git/model_registry.yaml"
if ($needsRegistryTest) {
    Invoke-Checked "python" @("-m", "pytest", "tests/test_registry_tool.py", "-q", "--tb=short")
}

Write-Host "[PRE-COMMIT] Alle staged Checks bestanden." -ForegroundColor Green
exit 0

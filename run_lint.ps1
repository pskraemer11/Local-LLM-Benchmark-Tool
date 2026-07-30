<#
.SYNOPSIS
    Führt Ruff, Mypy, Bandit und Pylint auf den angegebenen Python-Dateien/Ordnern aus.
.PARAMETER targets
    Ein oder mehrere Dateien/Ordner. Standard: aktuelles Verzeichnis wenn keiner angegeben.
.PARAMETER check
    Nur prüfen, nicht formatieren (ruff format --check statt ruff format).
.EXAMPLE
    .\run_lint.ps1
    .\run_lint.ps1 -check src/ registry_tool.py
    .\run_lint.ps1 -targets src/, registry_tool.py
#>

param(
    [string[]]$targets,
    [switch]$check
)

if (-not $targets) {
    $targets = @(".")
}

$exit_code = 0
$ErrorActionPreference = "SilentlyContinue"

function Test-Tool {
    param($name)
    $null = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $?) {
        Write-Host "  [ÜBERSPRUNGEN] $name nicht installiert" -ForegroundColor Yellow
        return $false
    }
    return $true
}

function Run-Tool {
    param($name, $cmd)
    if (-not (Test-Tool $name)) { return }
    Write-Host "`n" ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $name" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    Invoke-Expression $cmd
    if ($global:LASTEXITCODE -ne 0) {
        $script:exit_code = $global:LASTEXITCODE
        Write-Host "  [FEHLER] $name abgebrochen (Exit $global:LASTEXITCODE)" -ForegroundColor Red
    } else {
        Write-Host "  [OK] $name" -ForegroundColor Green
    }
}

Run-Tool "ruff" "ruff check $($targets -join ' ')"
if ($check) {
    Run-Tool "ruff" "ruff format --check $($targets -join ' ')"
} else {
    Run-Tool "ruff" "ruff format $($targets -join ' ')"
}
Run-Tool "mypy" "mypy $($targets -join ' ')"
Run-Tool "bandit" "bandit -r $($targets -join ' ')"
Run-Tool "pylint" "pylint $($targets -join ' ')"

Write-Host "`n" ("=" * 60) -ForegroundColor Cyan
if ($exit_code -eq 0) {
    Write-Host "  [OK] Alle Prüfungen bestanden" -ForegroundColor Green
} else {
    Write-Host "  [FEHLER] Einige Prüfungen fehlgeschlagen (Exit $exit_code)" -ForegroundColor Red
}
Write-Host ("=" * 60) -ForegroundColor Cyan
exit $exit_code

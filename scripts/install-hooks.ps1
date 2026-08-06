<#
.SYNOPSIS
    Installiert/deinstalliert die Git-Hooks des Repos (core.hooksPath -> scripts/hooks).

.DESCRIPTION
    Setzt repo-lokal 'git config core.hooksPath scripts/hooks'. Git fuehrt dann
    automatisch scripts/hooks/pre-push vor jedem Push aus (Review-Gate).
    Der Config-Eintrag ist relativ und damit portabel.

.PARAMETER Uninstall
    Entfernt core.hooksPath wieder (Standard-Git-Hooks-Verzeichnis).

.PARAMETER Force
    Ueberschreibt eine vorhandene Hook-Datei.

.EXAMPLE
    .\scripts\install-hooks.ps1
    .\scripts\install-hooks.ps1 -Uninstall
#>

param(
    [switch]$Uninstall,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $projectRoot

if ($Uninstall) {
    git config --unset core.hooksPath
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] core.hooksPath entfernt - Git nutzt wieder das Standard-Hooks-Verzeichnis." -ForegroundColor Green
    } else {
        Write-Host "[INFO] core.hooksPath war nicht gesetzt." -ForegroundColor Yellow
    }
    exit 0
}

$hooksDir = "scripts/hooks"
$hookFile = Join-Path $projectRoot "$hooksDir\pre-push"

if (-not (Test-Path -LiteralPath $hookFile)) {
    Write-Error "Hook-Datei fehlt: $hookFile"
    exit 1
}

$hookContent = @'
#!/bin/sh
# Git pre-push hook -> Review-Gate (pre_review_checks.ps1)
# Installiert via: scripts/install-hooks.ps1  (setzt core.hooksPath)
exec pwsh -NoProfile -ExecutionPolicy Bypass -File "$(dirname "$0")/../pre-push.ps1" "$@"
'@

if ($Force -or -not (Test-Path -LiteralPath $hookFile)) {
    Set-Content -LiteralPath $hookFile -Value $hookContent -Encoding ascii
    Write-Host "[OK] Hook-Datei geschrieben: $hookFile" -ForegroundColor Green
}

git config core.hooksPath $hooksDir
if ($LASTEXITCODE -ne 0) {
    Write-Error "git config core.hooksPath fehlgeschlagen"
    exit 1
}

Write-Host "[OK] core.hooksPath gesetzt: $hooksDir" -ForegroundColor Green
Write-Host "[OK] pre-push-Hook aktiv - jeder 'git push' fuehrt das Review-Gate aus." -ForegroundColor Green
Write-Host "     Umgehung nur fuer Notfaelle: git push --no-verify" -ForegroundColor DarkGray
exit 0

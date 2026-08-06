<#
.SYNOPSIS
    Git pre-push Hook - fuehrt das Review-Gate (pre_review_checks.ps1) vor jedem Push aus.

.DESCRIPTION
    Wird vom Git-Hook scripts/hooks/pre-push aufgerufen. Fuehrt das vollstaendige
    Review-Gate aus (validate --repro, ruff, mypy informativ, pytest, GGUF-Check).
    Blockiert den Push bei blockierenden Fehlern (Exit 1).

    Umgehung nur fuer Notfaelle: git push --no-verify

.PARAMETER SkipGguf
    Reicht -SkipGguf an das Gate durch (schnellerer Push, weniger Transparenz).

.PARAMETER SkipPytest
    Reicht -SkipPytest an das Gate durch.

.EXAMPLE
    # Installiert den Hook:
    .\scripts\install-hooks.ps1
#>

param(
    [switch]$SkipGguf,
    [switch]$SkipPytest
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $projectRoot

# Push-Infos vom Hook-Stdin lesen (<local ref> <local oid> <remote ref> <remote oid>)
$pushInfo = @($input | ForEach-Object { $_ })
if ($pushInfo.Count -gt 0) {
    Write-Host "`n=== pre-push Hook: $(Get-Date -Format 'HH:mm:ss') ===" -ForegroundColor Cyan
    foreach ($line in $pushInfo) {
        $parts = $line -split "\s+"
        if ($parts.Count -ge 3) {
            Write-Host ("  {0} -> {1}" -f $parts[0], $parts[2]) -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "`n=== pre-push Hook (keine Push-Refs gelesen) ===" -ForegroundColor Cyan
}

$gateArgs = @{ NoTranscript = $true }
if ($SkipGguf) { $gateArgs.SkipGguf = $true }
if ($SkipPytest) { $gateArgs.SkipPytest = $true }

& (Join-Path $projectRoot "pre_review_checks.ps1") @gateArgs
$gateExit = $LASTEXITCODE

if ($gateExit -ne 0) {
    Write-Host "`n[PUSH ABGEBROCHEN] Review-Gate fehlgeschlagen. Fixen oder bewusst 'git push --no-verify' nutzen." -ForegroundColor Red
} else {
    Write-Host "`n[PUSH OK] Review-Gate bestanden." -ForegroundColor Green
}
exit $gateExit

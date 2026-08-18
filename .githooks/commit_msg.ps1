<#
.SYNOPSIS
    Validates commit message shape and prevents credentials in messages.
#>

param (
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$MessageFile
)

$ErrorActionPreference = "Stop"

function Stop-Hook([string]$Message) {
    Write-Host "[COMMIT-MSG BLOCKED] $Message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $MessageFile)) {
    Stop-Hook "Commit-Message-Datei nicht gefunden."
}

$lines = @(Get-Content -LiteralPath $MessageFile -Encoding utf8)
$subject = ($lines | Where-Object { $_ -notmatch '^\s*#' } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($subject)) {
    Stop-Hook "Commit-Message darf nicht leer sein."
}
if ($subject.Length -gt 72) {
    Stop-Hook "Die erste Commit-Message-Zeile darf maximal 72 Zeichen lang sein."
}
if ($subject -match '(ghp_|github_pat_|sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{30,})') {
    Stop-Hook "Commit-Message enthaelt moeglicherweise ein Secret."
}

# Allow Git-generated merge/revert messages; regular project commits use the
# same conventional prefixes already established in the repository history.
$allowedGenerated = $subject -match '^(Merge |Revert )'
$allowedPrefix = $subject -match '^(feat|fix|refactor|docs|test|chore|ci|build|perf|style|revert)(\([^()]+\))?:\s+\S+'
if (-not ($allowedGenerated -or $allowedPrefix)) {
    Stop-Hook "Commit-Message muss ein Projektpraefix wie 'fix:' oder 'docs:' enthalten."
}

Write-Host "[COMMIT-MSG] Commit-Message ist gueltig." -ForegroundColor Green
exit 0

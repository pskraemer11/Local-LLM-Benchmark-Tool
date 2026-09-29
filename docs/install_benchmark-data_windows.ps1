#requires -Version 5.1

<##
.SYNOPSIS
    Legacy-Vorschau für die globalen Benchmark-Python-Abhängigkeiten.

.DESCRIPTION
    Das Benchmarks-Projekt wird nicht weiter aktiv gepflegt und besitzt bewusst
    keine eigene venv. Dieses Skript verwendet deshalb explizit Python 3.12,
    ändert standardmäßig aber nichts. Vor einer optionalen Installation werden
    pip check und ein gemeinsamer Resolver-Dry-Run über alle vorhandenen Pakete
    ausgeführt. Eine echte Änderung erfordert ausdrücklich -Apply.
#>

[CmdletBinding()]
param([switch]$Apply)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
$downloadScript = Join-Path $repoRoot 'download_real_benchmarks.py'
$requestedPackages = @(
    'requests'
    'datasets'
    'numpy'
    'pandas'
    'matplotlib'
    'seaborn'
    'psutil'
    'nvidia-ml-py'
    'langdetect'
    'immutabledict'
    'antlr4-python3-runtime==4.11'
    'lm-eval[math]'
    'nltk'
)

function Invoke-Python312 {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & py '-3.12' @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 ist mit Exit-Code $LASTEXITCODE fehlgeschlagen." }
}

function Get-PipJson {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $output = @(& py '-3.12' -m pip @Arguments)
    if ($LASTEXITCODE -ne 0) { throw "Die Pip-Abfrage ist fehlgeschlagen: $($Arguments -join ' ')" }
    try { return @((($output -join [Environment]::NewLine) | ConvertFrom-Json)) }
    catch { throw "Die JSON-Ausgabe von Pip konnte nicht gelesen werden: $($_.Exception.Message)" }
}

function Test-PipDependencies {
    $output = @(& py '-3.12' -m pip check 2>&1)
    $exitCode = $LASTEXITCODE
    if ($output.Count -gt 0) { $output | ForEach-Object { Write-Host $_ } }
    if (($exitCode -ne 0) -or ($output -match 'Ignoring invalid distribution')) {
        throw 'Die globale Python-3.12-Umgebung ist vor der Änderung nicht konsistent.'
    }
}

function Get-RequirementName {
    param([Parameter(Mandatory)][string]$Requirement)
    return (($Requirement -replace '\[.*$', '') -replace '[<>=!~].*$', '').Trim().ToLowerInvariant()
}

function Save-Freeze {
    param([Parameter(Mandatory)][ValidateSet('before','after')][string]$Phase)
    $backupDirectory = Join-Path $scriptDir 'pip-backups'
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    $file = Join-Path $backupDirectory "global-python312-freeze-$Phase-$(Get-Date -Format yyyyMMdd-HHmmss).txt"
    $freeze = @(& py '-3.12' -m pip freeze)
    if ($LASTEXITCODE -ne 0) { throw 'pip freeze konnte nicht erstellt werden.' }
    $freeze | Set-Content -LiteralPath $file -Encoding UTF8
    Write-Host "Freeze-Sicherung: $file"
    return $file
}

Write-Host 'Prüfe Python 3.12 ...'
Invoke-Python312 -Arguments @('--version')
Write-Host 'Hinweis: Dieses Legacy-Skript nutzt keine Benchmark-venv und ist standardmäßig nur eine Vorschau.' -ForegroundColor Yellow

Test-PipDependencies
$installed = @(Get-PipJson -Arguments @('list', '--format=json'))
$desiredByName = @{}
foreach ($package in $requestedPackages) { $desiredByName[(Get-RequirementName $package)] = $package }
$installedNames = @{}
foreach ($package in $installed) { $installedNames[([string]$package.name).ToLowerInvariant()] = $true }

$transactionLines = @(
    $installed | Sort-Object -Property name | ForEach-Object {
        $name = ([string]$_.name).ToLowerInvariant()
        if ($desiredByName.ContainsKey($name)) { $desiredByName[$name] }
        else { '{0}=={1}' -f $_.name, $_.version }
    }
    foreach ($package in $requestedPackages) {
        if (-not $installedNames.ContainsKey((Get-RequirementName $package))) { $package }
    }
)

$requirementsFile = Join-Path ([System.IO.Path]::GetTempPath()) ("benchmark-legacy-$([guid]::NewGuid()).txt")
try {
    $transactionLines | Set-Content -LiteralPath $requirementsFile -Encoding UTF8
    $pipPlan = @('-m', 'pip', 'install', '--upgrade-strategy', 'only-if-needed', '--requirement', $requirementsFile)
    $dryRunPlan = [string[]]$pipPlan + '--dry-run'
    Write-Host 'Prüfe den vollständigen Benchmark-Paketplan mit pip --dry-run ...'
    Invoke-Python312 -Arguments $dryRunPlan

    if (-not $Apply) {
        Write-Host 'Nur Vorschau. Wegen des Legacy-Status wird keine Installation ausgeführt.' -ForegroundColor Yellow
        return
    }

    Save-Freeze -Phase before | Out-Null
    Invoke-Python312 -Arguments $pipPlan
    Test-PipDependencies
    Invoke-Python312 -Arguments @('-c', "import datasets, langdetect, nltk, numpy, pandas, requests, seaborn")
    Save-Freeze -Phase after | Out-Null

    Write-Host 'Lade NLTK-Daten (punkt, punkt_tab) ...'
    Invoke-Python312 -Arguments @('-c', "import sys, nltk; ok = nltk.download('punkt', quiet=True) and nltk.download('punkt_tab', quiet=True); sys.exit(0 if ok else 1)")
    Write-Host 'Installation abgeschlossen.' -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $requirementsFile) { Remove-Item -LiteralPath $requirementsFile -Force }
}

if (Test-Path -LiteralPath $downloadScript -PathType Leaf) {
    Write-Host "Legacy-Datenskript vorhanden, aber nicht Teil der aktiven Pipeline: $downloadScript"
}
Write-Host 'Aktiver Benchmark-Einstiegspunkt: src\run_benchmarks.py'

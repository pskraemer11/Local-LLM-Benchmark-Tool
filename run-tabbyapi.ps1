# Benchmark-Lauf gegen TabbyAPI (exllamav3-Backend).
# Startet die Benchmarks fuer die in run.tabbyapi.yaml gelisteten EXL3-Modelle.
# Voraussetzung: TabbyAPI laeuft mit geladenem Modell auf 127.0.0.1:5000.
#
# Verwendung:  .\run-tabbyapi.ps1 [-SampleSize 30] [-NumParallel 4] [-Models "key1,key2"]

param(
    [string]$Models = $null,
    [int]$SampleSize = 30,
    [int]$NumParallel = 4
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:LLM_API_BASE = "http://127.0.0.1:5000/v1"

$args = @("src\run_benchmarks.py", "--run-spec", "run.tabbyapi.yaml",
          "--sample-size", "$SampleSize", "--num-parallel", "$NumParallel")
if ($Models) { $args += @("--model", $Models) }

$logDir = "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir | Out-Null }
$logFile = Join-Path $logDir ("tabbyapi_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

Write-Host "LLM_API_BASE=$env:LLM_API_BASE  (TabbyAPI/exllamav3)"
Write-Host "Log: $logFile"
py -3.14 @args 2>&1 | Tee-Object -FilePath $logFile
exit $LASTEXITCODE

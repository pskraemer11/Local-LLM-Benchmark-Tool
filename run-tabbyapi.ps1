# Benchmark-Lauf gegen TabbyAPI (exllamav3-Backend).
# Startet die Benchmarks fuer die in run.tabbyapi.yaml gelisteten EXL3-Modelle.
# Voraussetzung: TabbyAPI laeuft mit geladenem Modell auf 127.0.0.1:5000.
#
# Verwendung:  .\run-tabbyapi.ps1 [-SampleSize 30] [-Models "key1,key2"]

param(
    [string]$Models = $null,
    [int]$SampleSize = 30
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:LLM_PROVIDER = "tabbyapi"
$env:LLM_API_BASE = "http://127.0.0.1:5000/v1"
$tabbyRoot = Join-Path (Split-Path $PSScriptRoot -Parent) "tabbyAPI"
if (Test-Path (Join-Path $tabbyRoot "config.yml")) { $env:TABBYAPI_CONFIG = Join-Path $tabbyRoot "config.yml" }
if (Test-Path (Join-Path $tabbyRoot "models")) { $env:TABBYAPI_MODEL_DIR = Join-Path $tabbyRoot "models" }

$args = @("src\run_benchmarks.py", "--run-spec", "run.tabbyapi.yaml",
          "--sample-size", "$SampleSize")
if ($Models) { $args += @("--model", $Models) }

$logDir = "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory $logDir | Out-Null }
$logFile = Join-Path $logDir ("tabbyapi_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

Write-Host "LLM_PROVIDER=$env:LLM_PROVIDER  LLM_API_BASE=$env:LLM_API_BASE  (TabbyAPI/exllamav3)"
Write-Host "TABBYAPI_MODEL_DIR=$env:TABBYAPI_MODEL_DIR"
Write-Host "Log: $logFile"
py -3.12 @args 2>&1 | Tee-Object -FilePath $logFile
exit $LASTEXITCODE

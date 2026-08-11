# Wartet auf Abschluss von Pass 1 und startet dann Pass 2 automatisch
# Verwendung: .\scripts\run-pass2-after-pass1.ps1

$ErrorActionPreference = "Stop"
$projectRoot = "C:\Users\pskra\Python-Projekte\Benchmarks"
Set-Location $projectRoot

$logFile = "Doku-intern\Benchmark-Pass2-auto_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

function Write-Log {
    param([string]$msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

# Pruefe ob Pass 1 noch laeuft
$pass1Running = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*run.qwen-re-run-pass1*"
}

if ($pass1Running) {
    Write-Log "Pass 1 laeuft noch (PID $($pass1Running.Id)). Warte auf Abschluss..."
    $pass1Running.WaitForExit()
    Write-Log "Pass 1 beendet (Exit Code: $($pass1Running.ExitCode))"
} else {
    Write-Log "Pass 1 nicht gefunden — starte Pass 2 direkt."
}

# Starte Pass 2
Write-Log "Starte Pass 2: Andere fehlende Modelle"
$log2 = "Doku-intern\Terminalausgabe Benchmark Qwen-Pass2_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
$err2 = "Doku-intern\Qwen-Pass2_stderr_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

Remove-Item "ergebnisse\.benchmark.lock" -Force -ErrorAction SilentlyContinue

$proc = Start-Process -FilePath "python" -ArgumentList "src\run_benchmarks.py","--run-spec","run.qwen-re-run-pass2.yaml" `
    -RedirectStandardOutput $log2 -RedirectStandardError $err2 -PassThru -NoNewWindow

Write-Log "Pass 2 gestartet (PID $($proc.Id))"
Write-Log "stdout: $log2"
Write-Log "stderr: $err2"

$proc.WaitForExit()
Write-Log "Pass 2 beendet (Exit Code: $($proc.ExitCode))"
Write-Log "Beide Passes fertig. Log: $logFile"

<#
.SYNOPSIS
    Installiert Abhaengigkeiten und laedt alle Benchmark-Datensaetze herunter.
    Ausfuehrung: PowerShell (als Administrator empfohlen).
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$DownloadScript = Join-Path $RepoRoot "download_real_benchmarks.py"

Write-Host "=" * 60
Write-Host "  Install-Skript fuer lokale LLM-Benchmarks (Windows)"
Write-Host "=" * 60

# ─── 1. Python-Pruefung ───
Write-Host "`n[1/4] Pruefe Python-Installation..."
try {
    $pyVersion = & python --version 2>&1
    Write-Host "  [OK] $pyVersion"
} catch {
    Write-Host "  [ERROR] Python nicht gefunden. Installiere Python 3.10+ von:"
    Write-Host "          https://www.python.org/downloads/"
    Write-Host "  Stelle sicher, dass 'python' im PATH ist."
    exit 1
}

# ─── 2. LM Studio-Pruefung ───
Write-Host "`n[2/4] Pruefe LM Studio (lms.exe)..."
try {
    $lmsVersion = & lms --version 2>&1
    Write-Host "  [OK] $lmsVersion"
} catch {
    Write-Host "  [WARN] lms.exe nicht im PATH."
    Write-Host "  Installiere LM Studio von: https://lmstudio.ai/"
    Write-Host "  Nach Installation: 'lms' muss im System-PATH sein."
    Write-Host "  (Standard: C:\Users\$env:USERNAME\AppData\Local\LM Studio\LM Studio)"
}

# ─── 3. Python-Pakete installieren ───
Write-Host "`n[3/4] Installiere Python-Abhaengigkeiten..."
$packages = @(
    "requests"
    "datasets"
    "numpy"
    "pandas"
    "matplotlib"
    "seaborn"
    "psutil"
    "nvidia-ml-py"
)
foreach ($pkg in $packages) {
    Write-Host "  Installiere $pkg ..." -NoNewline
    try {
        & pip install --quiet $pkg 2>&1 | Out-Null
        Write-Host " OK"
    } catch {
        Write-Host " FEHLGESCHLAGEN"
        Write-Host "  [WARN] $pkg konnte nicht installiert werden."
    }
}

# ─── 4. Benchmark-Daten herunterladen ───
Write-Host "`n[4/4] Lade Benchmark-Datensaetze herunter..."
if (Test-Path $DownloadScript) {
    & python $DownloadScript
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Download abgeschlossen."
    } else {
        Write-Host "  [ERROR] Download fehlgeschlagen (Exit-Code: $LASTEXITCODE)."
        exit 1
    }
} else {
    Write-Host "  [ERROR] $DownloadScript nicht gefunden."
    Write-Host "  Stelle sicher, dass das Skript im selben Ordner liegt."
    exit 1
}

Write-Host "`n" + "=" * 60
Write-Host "  Installation abgeschlossen."
Write-Host "  Starte das Benchmark-Skript mit:"
Write-Host "    python run_benchmarks_v3.py --model <modell> --benchmarks all"
Write-Host "=" * 60

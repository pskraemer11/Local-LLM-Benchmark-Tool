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
    # ── lm-eval-harness Dependencies ──
    # Ohne diese schlagen IFEval und MATH-500 mit ModuleNotFoundError fehl
    # (siehe Terminalausgabe Benchmark Run 12.07.2026):
    #   - IFEval:       'No module named langdetect' + 'immutabledict'
    #                   (lm_eval/tasks/ifeval/instructions.py:36, instructions_util.py:23)
    #   - MATH-500:     'No module named math_verify' + 'antlr4-python3-runtime==4.11'
    #                   (lm_eval/tasks/minerva_math/utils.py:16,19)
    "langdetect"
    "immutabledict"
    "antlr4-python3-runtime==4.11"
    "lm-eval[math]"
    # nltk wird von lm_eval für TruthfulQA benötigt
    "nltk"
)
foreach ($pkg in $packages) {
    Write-Host "  Installiere $pkg ..." -NoNewline
    try {
        & pip install --quiet $pkg 2>&1 | Out-Null
        Write-Host " OK"
    } catch {
        Write-Host " FEHLGESCHLAGEN"
        Write-Host "  [WARN] $pkg konnte nicht installiert werden."
        Write-Host "         Manuelle Installation: pip install $pkg"
    }
}

# NLTK Daten herunterladen (für TruthfulQA Tokenisierung)
Write-Host "  Lade NLTK-Daten (punkt, punkt_tab) ..." -NoNewline
try {
    & python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True)" 2>&1 | Out-Null
    Write-Host " OK"
} catch {
    Write-Host " FEHLGESCHLAGEN"
    Write-Host "  [WARN] NLTK-Daten fehlen. TruthfulQA kann fehlschlagen."
}

# ─── 4. Benchmark-Daten herunterladen ───
# DEPRECATED 12.07.2026: download_real_benchmarks.py ist nicht mehr
# in der aktiven Pipeline. Die simple_evals/ JSONL-Dateien sollten
# manuell via evalplus / HuggingFace CLI bezogen werden.
Write-Host "`n[4/4] Benchmark-Datensaetze..."
Write-Host "  [INFO] download_real_benchmarks.py ist DEPRECATED."
Write-Host "  [INFO] Manuelle Installation empfohlen – siehe Skript-Header."
if (Test-Path $DownloadScript) {
    Write-Host "  [INFO] $DownloadScript existiert noch fuer Legacy-Zwecke."
    Write-Host "  [WARN] Datenformate entsprechen NICHT dem v13-Schema."
}

Write-Host "`n" + "=" * 60
Write-Host "  Installation abgeschlossen."
Write-Host "  Starte das Benchmark-Skript mit:"
Write-Host "    python run_benchmarks_v3.py --model <modell> --benchmarks all"
Write-Host "=" * 60

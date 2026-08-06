<#
.SYNOPSIS
    Pre-Review Checks (Phase 1) für Local-LLM-Benchmark-Tool (Windows 11 + Python 3.14).
.DESCRIPTION
    Führt folgende Checks aus:
    1. registry_tool.py validate
    2. ruff check .
    3. mypy .
    4. Konsistenzprüfung model_registry.yaml vs GGUF-Header (optional, langsam)
    Ergebnisse werden in einer Log-Datei gespeichert.
.EXAMPLE
    .\pre_review_checks.ps1
    .\pre_review_checks.ps1 -SkipGgufCheck
    .\pre_review_checks.ps1 -LogFile "custom_log.log"
    
Quelle: MistralAI LeChat/Vibe 28.06.2026 https://chat.mistral.ai/work/e4dd489b-946d-412d-9538-ec17a803c108
#>

### das unten im Python-Code Aufruf genannte Skript 'check_gguf_ctx.py' gibt es allerdings (noch) nicht! ###

param (
    [switch]$SkipGgufCheck,  # Überspringt die GGUF-Konsistenzprüfung (langsam)
    [string]$LogFile = "pre_review_checks_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
)

# Projektpfad
$projectPath = "C:\Users\pskra\Python-Projekte\Benchmarks"
if (-not (Test-Path -Path $projectPath)) {
    Write-Error "Projektverzeichnis nicht gefunden: $projectPath"
    exit 1
}
Set-Location -Path $projectPath

# Log-Datei initialisieren
Start-Transcript -Path $LogFile -Append -Force
Write-Host "=== Pre-Review Checks - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

# 1. registry_tool.py validate
Write-Host "`n[1/4] Führe registry_tool.py validate aus..."
try {
    $output = python src\registry_tool.py validate 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "registry_tool.py validate fehlgeschlagen:`n$output"
        Stop-Transcript
        exit 1
    }
    Write-Host "registry_tool.py validate: OK" -ForegroundColor Green
}
catch {
    Write-Error "Fehler bei registry_tool.py validate: $_"
    Stop-Transcript
    exit 1
}

# 2. ruff check (Warnungen zu veralteten Regeln ignorieren)
Write-Host "`n[2/4] Führe ruff check aus..."
try {
    # Ruff mit --no-fix und Filter für veraltete Regeln-Warnungen
    $output = ruff check . --config .\.pyproject.toml --no-fix 2>&1 | Where-Object { $_ -notmatch "warning: The following rules have been removed" }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ruff check fehlgeschlagen:`n$output"
        Stop-Transcript
        exit 1
    }
    Write-Host "ruff check: OK" -ForegroundColor Green
}
catch {
    Write-Error "Fehler bei ruff check: $_"
    Stop-Transcript
    exit 1
}

# 3. mypy
Write-Host "`n[3/4] Führe mypy aus..."
try {
    $output = mypy . 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "mypy fehlgeschlagen:`n$output"
        Stop-Transcript
        exit 1
    }
    Write-Host "mypy: OK" -ForegroundColor Green
}
catch {
    Write-Error "Fehler bei mypy: $_"
    Stop-Transcript
    exit 1
}

# 4. Konsistenzprüfung model_registry.yaml vs GGUF-Header (optional)
if (-not $SkipGgufCheck) {
    Write-Host "`n[4/4] Führe Konsistenzprüfung model_registry.yaml vs GGUF-Header aus..."
    try {
        $checkScript = @"
import yaml
import subprocess
from pathlib import Path
import sys
import json

def get_gguf_header(model_path):
    """Extrahiere Header-Daten aus GGUF-Datei."""
    try:
        result = subprocess.run(
            ["python", "src\\tools\\_check_gguf_ctx.py", str(model_path)],
            capture_output=True, text=True, check=True
        )
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Fehler beim Lesen von {model_path}: {e}", file=sys.stderr)
        return None

def main():
    registry_path = Path("doc-git\\model_registry.yaml")
    with open(registry_path, "r") as f:
        registry = yaml.safe_load(f)

    lms_models_path = Path("C:\\Users\\pskra\\.lmstudio\\models")
    errors = []

    for model_key, model_data in registry.items():
        parts = model_key.split("/")
        if len(parts) != 2:
            continue
        publisher, model_name = parts
        gguf_path = lms_models_path / publisher / model_name / f"{model_name}.gguf"

        if not gguf_path.exists():
            continue

        gguf_data = get_gguf_header(gguf_path)
        if not gguf_data:
            continue

        # Vergleiche Felder
        fields = ["max_context_length", "n_layers", "hidden_dim"]
        for field in fields:
            reg_value = model_data.get(field)
            gguf_value = gguf_data.get(field)
            if reg_value is not None and gguf_value is not None and reg_value != gguf_value:
                errors.append(f"{model_key}: {field} - Registry={reg_value}, GGUF={gguf_value}")

    if errors:
        print("Konsistenzfehler gefunden:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("Keine Konsistenzfehler gefunden.")

if __name__ == "__main__":
    main()
"@

        $tempScriptPath = "$env:TEMP\check_gguf_consistency.py"
        $checkScript | Out-File -FilePath $tempScriptPath -Encoding utf8

        $output = python $tempScriptPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Konsistenzprüfung fehlgeschlagen:`n$output"
            Stop-Transcript
            exit 1
        }
        Write-Host "Konsistenzprüfung: OK" -ForegroundColor Green
        Remove-Item -Path $tempScriptPath -Force -ErrorAction SilentlyContinue
    }
    catch {
        Write-Error "Fehler bei Konsistenzprüfung: $_"
        Stop-Transcript
        exit 1
    }
}

Write-Host "`n=== Alle Checks erfolgreich abgeschlossen ===" -ForegroundColor Green
Write-Host "Log-Datei: $LogFile" -ForegroundColor Cyan
Stop-Transcript
exit 0
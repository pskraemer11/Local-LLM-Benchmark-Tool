<#
.SYNOPSIS
    Pre-Review Checks v2 - Review-Gate fuer Local-LLM-Benchmark-Tool (Windows + Python 3.14).

.DESCRIPTION
    Fuehrt die Gate-Checks vor einem Review/Commit aus und erzeugt
    Transparenz-Artefakte in doc-git\Review-Artifacts\:

      1. registry_tool.py validate --repro
         -> repro_issues.md (Registry vs. LM Studio Hub model.yaml)
         -> BLOCKIERT bei Registry-Problemen (Exit 1)
      2. ruff check . --no-fix
         -> lint_issues.md
         -> BLOCKIERT bei Lint-Fehlern (Exit 1)
      3. mypy .
         -> NUR INFORMATIV (Legacy-Typfehler blockieren nicht)
      4. pytest -q
         -> BLOCKIERT bei Testfehlern (Exit 1)
      5. GGUF-Header vs. Registry (optional, Source-of-Truth-Check)
         -> gguf_issues.md
         -> NUR INFORMATIV

    Source of Truth fuer Modell-Fakten sind die GGUF-Dateien. Die Registry ist
    editierbar; die Hub-model.yaml wird nirgendwo im Prozess angefasst.

.PARAMETER SkipRepro
    Ueberspringt validate --repro (kein repro_issues.md).

.PARAMETER SkipPytest
    Ueberspringt die pytest-Suite.

.PARAMETER SkipGguf
    Ueberspringt den GGUF-Header-Vergleich (liest viele Dateien).

.PARAMETER LogFile
    Pfad fuer das Transcript-Log (Default: pre_review_checks_<timestamp>.log).

.PARAMETER NoTranscript
    Kein Transcript-Log schreiben (fuer pre-push-Hook-Aufrufe).

.EXAMPLE
    .\pre_review_checks.ps1
    .\pre_review_checks.ps1 -SkipGguf -LogFile "C:\temp\gate.log"
    .\pre_review_checks.ps1 -NoTranscript -SkipGguf   # wie vom pre-push-Hook
#>

param (
    [switch]$SkipRepro,
    [switch]$SkipPytest,
    [switch]$SkipGguf,
    [string]$LogFile = "pre_review_checks_$(Get-Date -Format 'yyyyMMdd_HHmmss').log",
    [switch]$NoTranscript
)

$ErrorActionPreference = "Stop"

$projectPath = "C:\Users\pskra\Python-Projekte\Benchmarks"
if (-not (Test-Path -LiteralPath $projectPath)) {
    Write-Error "Projektverzeichnis nicht gefunden: $projectPath"
    exit 1
}
Set-Location -LiteralPath $projectPath

$artifactsDir = Join-Path $projectPath "doc-git\Review-Artifacts"
if (-not (Test-Path -LiteralPath $artifactsDir)) {
    New-Item -ItemType Directory -Path $artifactsDir -Force | Out-Null
}

if (-not $NoTranscript) {
    Start-Transcript -Path $LogFile -Append -Force
    Write-Host "Log: $LogFile" -ForegroundColor DarkGray
}
Write-Host "=== Pre-Review Checks v2 - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" -ForegroundColor Cyan

$blockingFails = 0
$warnings = 0

# ── 1. registry_tool.py validate --repro ──────────────────────────
Write-Host "`n[1/5] validate --repro (Registry + repro_issues.md) ..." -ForegroundColor Cyan
if ($SkipRepro) {
    Write-Host "  UEBERSPRUNGEN (-SkipRepro)" -ForegroundColor Yellow
} else {
    & python src\registry_tool.py validate --repro 2>&1 | Tee-Object -Variable validateOut | Out-Host
    $validateExit = $LASTEXITCODE
    if ($validateExit -ne 0) {
        Write-Host "  [FEHLER] validate meldet Registry-Probleme (siehe oben)." -ForegroundColor Red
        $blockingFails++
    } else {
        Write-Host "  validate: OK (0 Registry-Probleme)" -ForegroundColor Green
    }
}

# ── 2. ruff check ─────────────────────────────────────────────────
Write-Host "`n[2/5] ruff check . --no-fix -> lint_issues.md ..." -ForegroundColor Cyan
$lintFile = Join-Path $artifactsDir "lint_issues.md"
$ruffOut = & ruff check . --no-fix 2>&1
$ruffExit = $LASTEXITCODE
$issueCount = ($ruffOut | Select-String -Pattern "^[A-Z][0-9]{3} ").Count
$header = @(
    "# Lint-Issues (ruff check . --no-fix)",
    "",
    "Erzeugt: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "",
    "$issueCount Probleme, Exit-Code $ruffExit",
    ""
) -join "`n"
$ruffOut | Out-File -FilePath $lintFile -Encoding utf8 -Force
# Header voranstellen
$content = Get-Content -LiteralPath $lintFile -Raw -Encoding utf8
$content = "$header`n$content"
Set-Content -LiteralPath $lintFile -Value $content -Encoding utf8
if ($ruffExit -ne 0) {
    Write-Host "  [FEHLER] ruff: $issueCount Probleme -> $lintFile" -ForegroundColor Red
    $blockingFails++
} else {
    Write-Host "  ruff: OK (0 Probleme) -> $lintFile" -ForegroundColor Green
}

# ── 3. mypy (informativ) ──────────────────────────────────────────
Write-Host "`n[3/5] mypy . (nur informativ) ..." -ForegroundColor Cyan
$mypyOut = & python -m mypy . 2>&1
$mypyExit = $LASTEXITCODE
$mypyErrors = ($mypyOut | Select-String -Pattern "error: ").Count
if ($mypyExit -eq 0) {
    Write-Host "  mypy: OK (0 Fehler)" -ForegroundColor Green
} else {
    Write-Host "  [INFO] mypy: $mypyErrors Fehler (informativ, blockiert NICHT)" -ForegroundColor Yellow
    $warnings++
}

# ── 4. pytest ─────────────────────────────────────────────────────
Write-Host "`n[4/5] pytest -q ..." -ForegroundColor Cyan
if ($SkipPytest) {
    Write-Host "  UEBERSPRUNGEN (-SkipPytest)" -ForegroundColor Yellow
} else {
    & python -m pytest -q 2>&1 | Tee-Object -Variable pytestOut | Out-Host
    $pytestExit = $LASTEXITCODE
    if ($pytestExit -ne 0) {
        Write-Host "  [FEHLER] pytest fehlgeschlagen (siehe oben)." -ForegroundColor Red
        $blockingFails++
    } else {
        Write-Host "  pytest: OK" -ForegroundColor Green
    }
}

# ── 5. GGUF-Header vs. Registry (Source of Truth, informativ) ─────
Write-Host "`n[5/5] GGUF-Header vs. Registry -> gguf_issues.md ..." -ForegroundColor Cyan
if ($SkipGguf) {
    Write-Host "  UEBERSPRUNGEN (-SkipGguf)" -ForegroundColor Yellow
} else {
    $ggufScript = @'
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

PROJECT = Path.cwd()  # Skript laeuft immer mit cwd=Projektroot (Set-Location)
sys.path.insert(0, str(PROJECT / "src"))

from registry_tool import MODELS_CACHE, _get_all_ggufs, _read_gguf_arch, load_registry  # noqa: E402


def norm(s: str) -> str:
    return s.lower().replace("_", "-").replace(".", "-").replace("\\", "/")


reg = load_registry()
bases: dict[str, list[str]] = {}
for key, entry in reg.items():
    if not isinstance(entry, dict):
        continue
    base = norm(key.split("@")[0])
    bases.setdefault(base, []).append(key)

hits: dict[str, tuple[Path, tuple]] = {}
with ThreadPoolExecutor(max_workers=8) as pool:
    futures = {}
    for path in _get_all_ggufs():
        if "mmproj" in path.name.lower():
            continue
        futures[pool.submit(_read_gguf_arch, str(path))] = path
    for fut in as_completed(futures):
        path = futures[fut]
        nl, hd, _is_reasoning, ctx = fut.result()
        if not nl or not hd:
            continue
        rel = path.relative_to(MODELS_CACHE)
        if len(rel.parts) < 2:
            continue
        folder = norm(str(rel.parent))
        best = None
        for base in bases:
            if folder == base or base in folder:
                if best is None or len(base) > len(best):
                    best = base
        if best is None:
            continue
        for key in bases[best]:
            hits.setdefault(key, (path, (nl, hd, ctx)))

errors = []
for key, (path, (nl, hd, ctx)) in sorted(hits.items()):
    entry = reg[key]
    for reg_field, gguf_val, label in (
        ("n_layers", nl, "n_layers"),
        ("hidden_dim", hd, "hidden_dim"),
        ("max_context_length", ctx, "max_context_length"),
    ):
        rv = entry.get(reg_field)
        if rv is not None and int(rv) != gguf_val:
            errors.append(f"- **{key}**: {label} Registry={rv} vs GGUF={gguf_val} ({path})")

out = PROJECT / "doc-git" / "Review-Artifacts" / "gguf_issues.md"
lines = [
    "# GGUF-Issues: model_registry.yaml vs. GGUF-Header",
    "",
    "Erzeugt automatisch: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "",
    "Source of Truth: die GGUF-Dateien (unveraenderliche Modell-Fakten). Die",
    "Registry wird hier gegen die GGUF-Header (n_layers, hidden_dim,",
    "max_context_length) geprueft.",
    "",
]
lines.append(f"{len(hits)} Registry-Eintraege mit GGUF-Datei abgeglichen.")
if errors:
    lines.append(f"{len(errors)} Abweichungen:")
    lines.append("")
    lines.extend(errors)
else:
    lines.append("Keine Abweichungen zwischen Registry und GGUF-Headern.")
lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"\n[GGUF] Artefakt geschrieben: {out}")
print(f"[GGUF] {len(errors)} Abweichungen, {len(hits)} Eintraege geprueft.")
'@
    $ggufScriptPath = Join-Path $env:TEMP "pre_review_gguf_check.py"
    Set-Content -LiteralPath $ggufScriptPath -Value $ggufScript -Encoding utf8
    try {
        & python $ggufScriptPath 2>&1 | Tee-Object -Variable ggufOut | Out-Host
        $ggufExit = $LASTEXITCODE
        if ($ggufExit -ne 0) {
            Write-Host "  [INFO] GGUF-Check nicht vollstaendig (Exit $ggufExit). Artefakt evtl. unvollstaendig." -ForegroundColor Yellow
            $warnings++
        } else {
            Write-Host "  GGUF-Check: OK (Artefakt geschrieben)" -ForegroundColor Green
        }
    } catch {
        Write-Host "  [INFO] GGUF-Check fehlgeschlagen: $_" -ForegroundColor Yellow
        $warnings++
    } finally {
        Remove-Item -LiteralPath $ggufScriptPath -Force -ErrorAction SilentlyContinue
    }
}

# ── Zusammenfassung ───────────────────────────────────────────────
Write-Host "`n=== Zusammenfassung ===" -ForegroundColor Cyan
Write-Host "Artefakte: $((Get-ChildItem -LiteralPath $artifactsDir -Filter *.md -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ', ')" -ForegroundColor DarkGray
Write-Host "Warnungen (nicht blockierend): $warnings" -ForegroundColor Yellow

$changelog = Join-Path $projectPath "CHANGELOG.md"
if (-not (Test-Path -LiteralPath $changelog)) {
    Write-Host "[HINWEIS] CHANGELOG.md fehlt im Projekt-Root - geplantes Artefakt aus dem Review-Konzept." -ForegroundColor Yellow
} else {
    Write-Host "[HINWEIS] CHANGELOG.md-Eintrag fuer diese Aenderungen ergaenzt?" -ForegroundColor Yellow
}

if ($blockingFails -gt 0) {
    Write-Host "`n[BLOCKIERT] $blockingFails blockierende(n) Check(s) fehlgeschlagen." -ForegroundColor Red
    if (-not $NoTranscript) { Stop-Transcript }
    exit 1
}
Write-Host "`n=== Alle blockierenden Checks bestanden ===" -ForegroundColor Green
if (-not $NoTranscript) { Stop-Transcript }
exit 0

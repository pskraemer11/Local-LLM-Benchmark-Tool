<#
.SYNOPSIS
    Pre-Review Checks v3 - Review-Gate fuer Local-LLM-Benchmark-Tool (Windows + Python auf PATH).

.DESCRIPTION
    Fuehrt die Gate-Checks vor einem Review/Commit aus und erzeugt
    Transparenz-Artefakte in doc-git\Review-Artifacts\:

      1. registry_tool.py validate --repro
         -> repro_issues.md (Registry, GGUF-Header und Provider-Runtime-Drift)
         -> BLOCKIERT bei Validierungsproblemen (Exit 1)
      2. ruff check . --no-fix
         -> lint_issues.md
         -> BLOCKIERT bei Lint-Fehlern (Exit 1)
      3. mypy .
         -> NUR INFORMATIV (Legacy-Typfehler blockieren nicht)
      4. pytest -q
         -> BLOCKIERT bei Testfehlern (Exit 1)
      5. GGUF-Header vs. Registry (optional, technical facts)
         -> gguf_issues.md
         -> NUR INFORMATIV
      6. CHANGELOG + LM Studio Config-np Verifikation (advisory)
         -> WARNUNGEN, kein harter Blocker

    Source of Truth in Schichten:
      - GGUF-Header fuer Architektur- und Kontext-Fakten
      - model_registry.yaml fuer Benchmark-Policy und provider-neutrale Runtime-Werte
      - Provider-Artefakte (LM Studio JSON, TabbyAPI, Unsloth) sind abgeleitete Laufzeitdaten

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
Write-Host "=== Pre-Review Checks v3 - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" -ForegroundColor Cyan

$blockingFails = 0
$warnings = 0

# ── 1. registry_tool.py validate --repro ──────────────────────────
Write-Host "`n[1/6] validate --repro (Registry + GGUF + Provider-Runtime) ..." -ForegroundColor Cyan
if ($SkipRepro) {
    Write-Host "  UEBERSPRUNGEN (-SkipRepro)" -ForegroundColor Yellow
} else {
    & python src\registry_tool.py validate --repro 2>&1 | Tee-Object -Variable validateOut | Out-Host
    $validateExit = $LASTEXITCODE
    if ($validateExit -ne 0) {
        Write-Host "  [FEHLER] validate meldet Probleme (siehe oben)." -ForegroundColor Red
        $blockingFails++
    } else {
        Write-Host "  validate: OK" -ForegroundColor Green
    }
}

# ── 2. ruff check ─────────────────────────────────────────────────
Write-Host "`n[2/6] ruff check . --no-fix -> lint_issues.md ..." -ForegroundColor Cyan
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
Write-Host "`n[3/6] mypy . (nur informativ) ..." -ForegroundColor Cyan
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
Write-Host "`n[4/6] pytest -q ..." -ForegroundColor Cyan
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

# ── 5. GGUF-Header vs. Registry (technische Fakten, informativ) ─────
Write-Host "`n[5/6] GGUF-Header vs. Registry -> gguf_issues.md ..." -ForegroundColor Cyan
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
        nl, hd, _is_reasoning, ctx, _exp = fut.result()
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
    "Generated automatically: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "",
    "Source of truth for architecture facts: the GGUF files.",
    "The registry is checked here against the GGUF headers (n_layers, hidden_dim,",
    "max_context_length).",
    "",
]
lines.append(f"{len(hits)} registry entries matched against GGUF files.")
if errors:
    lines.append(f"{len(errors)} deviations:")
    lines.append("")
    lines.extend(errors)
else:
    lines.append("No deviations between registry and GGUF headers.")
lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"\n[GGUF] Artifact written: {out}")
print(f"[GGUF] {len(errors)} deviations, {len(hits)} entries checked.")
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

# ── 6. CHANGELOG + Config-np Verifikation (advisory) ──────────────
Write-Host "`n[6/6] CHANGELOG + LM Studio Config-np Verifikation (advisory) ..." -ForegroundColor Cyan

# CHANGELOG: Gibt es seit letztem Commit neue CHANGELOG-Einträge?
$changelog = Join-Path $projectPath "CHANGELOG.md"
if (-not (Test-Path -LiteralPath $changelog)) {
    Write-Host "  [WARN] CHANGELOG.md fehlt im Projekt-Root." -ForegroundColor Yellow
    $warnings++
} else {
    # Prüfe ob heute ein CHANGELOG-Eintrag erstellt wurde
    $today = Get-Date -Format "dd.MM.yyyy"
    $changelogContent = Get-Content $changelog -Raw -Encoding utf8
    if ($changelogContent -notlike "*$today*") {
        Write-Host "  [HINWEIS] Kein CHANGELOG-Eintrag für heute ($today) — bei substanziellen Änderungen ergänzen." -ForegroundColor Yellow
        $warnings++
    } else {
        Write-Host "  CHANGELOG: Eintrag für heute gefunden." -ForegroundColor Green
    }
}

# Config-np: Alle aktiven Configs sollten np=4 haben
$cfgRoot = Join-Path $env:USERPROFILE ".lmstudio\.internal\user-concrete-model-default-config"
$npWarnings = 0
if (Test-Path $cfgRoot) {
    Get-ChildItem $cfgRoot -Recurse -Filter "*.json" | ForEach-Object {
        if ($_.Name -like "*.bak*") { return }
        try {
            $data = Get-Content $_.FullName -Raw | ConvertFrom-Json
            $loadFields = $data.load.fields
            foreach ($f in $loadFields) {
                if ($f.key -eq "llm.load.numParallelSessions" -and $f.value -ne 4) {
                    Write-Host "  [WARN] np=$($f.value) (nicht 4): $($_.Name)" -ForegroundColor Yellow
                    $npWarnings++
                }
            }
        } catch { }
    }
}
if ($npWarnings -eq 0) {
    Write-Host "  LM Studio Config-np: Alle Configs haben np=4." -ForegroundColor Green
} else {
    Write-Host "  [WARN] $npWarnings Configs mit np!=4 gefunden (sollten auf 4 gesetzt werden)." -ForegroundColor Yellow
    $warnings++
}

# ── Zusammenfassung ───────────────────────────────────────────────
Write-Host "`n=== Zusammenfassung ===" -ForegroundColor Cyan
Write-Host "Artefakte: $((Get-ChildItem -LiteralPath $artifactsDir -Filter *.md -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name) -join ', ')" -ForegroundColor DarkGray
Write-Host "Warnungen (nicht blockierend): $warnings" -ForegroundColor Yellow

if ($blockingFails -gt 0) {
    Write-Host "`n[BLOCKIERT] $blockingFails blockierende(n) Check(s) fehlgeschlagen." -ForegroundColor Red
    Write-Host "  Bekannte pre-existente Fehler (nicht blockierend wenn nur diese):" -ForegroundColor Yellow
    Write-Host "  - tests/test_model_manager.py::TestUnloadAllModels, TestWaitForModelReady, TestValidateModelKey" -ForegroundColor DarkGray
    Write-Host "    (API-Pfad /v1/model vs /v1/chat/completions — wird separat gefixt)" -ForegroundColor DarkGray
    if (-not $NoTranscript) { Stop-Transcript }
    exit 1
}
Write-Host "`n=== Alle blockierenden Checks bestanden ===" -ForegroundColor Green
Write-Host "[HINWEIS] Nach Push: Compaction + CHANGELOG-Eintrag nicht vergessen (Trigger: commit/push)." -ForegroundColor Cyan
if (-not $NoTranscript) { Stop-Transcript }
exit 0

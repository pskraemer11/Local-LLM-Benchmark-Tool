#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Synchronisiert neu heruntergeladene LM Studio Modelle mit der
    model_registry.yaml und fuehrt die Prompt-Assembly aus.

.DESCRIPTION
    Erkennt neue Modelle (per lms ls --json + Config-Scan), fuegt sie bei
    Bedarf in die Registry ein und durchlaeuft den Blueprint-Workflow.

    Ablauf:
      1. lms ls --json -> Modellliste (Hub-verwaltet)
      2. registry_tool.py compare -> Vergleichsreport
      3. Bei -AutoAdd/-FullSync: registry_tool.py add -> fehlende Modelle eintragen
         (Architektur-Mapping, Default: k_cache=q8_0, v_cache=iq4_nl, offload=1, num_parallel=1/4)
      4. registry_tool.py configs -> load.fields in JSON-Configs schreiben
         (offloadRatio, numParallelSessions aus Registry)
      5. Bei -FullSync: registry_tool.py sync-ctx -> context_length aus JSON-Configs in Registry
      6. Pipeline: classify -> assemble -> validate

    Was das Skript NICHT macht:
      - Keine model.yaml im Hub erstellen (riskiert HTTP-500-Konflikt)
      - Keine Jinja-Templates kopieren (nur Gemma-4, manuell)
      - Keine verwaisten Configs loeschen
      - Keine manuell gesetzten k_cache/v_cache ueberschreiben
      - Kein Ueberschreiben von contextLength in JSON-Configs
        (geht nur JSON-Config -> Registry, nie umgekehrt)

.PARAMETER Status
    Nur Report anzeigen (Default).
    Zeigt: LMS-Modelle, Registry-Eintraege, JSON-Configs auf Disk,
    neue Modelle (LMS ohne Registry), verwaiste Configs (ohne Eintrag),
    nicht-in-LMS gelistete Registry-Eintraege.

.PARAMETER AutoAdd
    Neue Modelle automatisch in Registry aufnehmen + configs + Klassifikation.
    Durchlaeuft Schritte 3 (add) + 4 (configs) + classify.
    Ergibt: Modelle in Registry, load.fields geschrieben, Klassifikation aktuell.

.PARAMETER FullSync
    Komplettdurchlauf: AutoAdd + sync-ctx + assemble + validate.
    Empfohlen nach dem Herunterladen mehrerer neuer Modelle.
    Durchlaeuft: add -> configs -> sync-ctx -> classify -> assemble -> validate.

.PARAMETER SyncCtx
    Nur context_length aus JSON-Configs in Registry uebernehmen (registry_tool.py sync-ctx).
    Ohne add/configs/Pipeline. Nützlich nach manueller Aenderung der contextLength im LMS GUI.

.PARAMETER FillCtx
    Nur fehlende context_length: 16384 in der Registry ergaenzen (registry_tool.py fill-ctx).
    Ohne add/configs/Pipeline.

.PARAMETER Help
    Diese Hilfe anzeigen.

.EXAMPLE
    PS> .\sync_model_configs.ps1
    PS> .\sync_model_configs.ps1 -Status
    Nur Status-Report (Default). Keine Aenderungen.

.EXAMPLE
    PS> .\sync_model_configs.ps1 -AutoAdd
    Neue LMS-Modelle werden in Registry eingetragen,
    load.fields geschrieben und klassifiziert.

.EXAMPLE
    PS> .\sync_model_configs.ps1 -FullSync
    Komplette Synchronisation inkl. Prompt-Assembly und Validierung.

.LINK
    https://github.com/anomalyco/opencode
    registry_tool.py (compare/add/configs)
    assemble_blueprint.py (classify/assemble/validate)
    model_registry.yaml, blueprint_definitions.yaml
#>
param([switch]$Status,[switch]$AutoAdd,[switch]$FullSync,[switch]$SyncCtx,[switch]$FillCtx,[string]$AddModel="",[switch]$Help)
if ($Help -or !($Status -or $AutoAdd -or $FullSync -or $SyncCtx -or $FillCtx -or $AddModel)) {
@"
SYNC-MODEL-CONFIGS: LM Studio Modelle mit Registry abgleichen

USAGE:
  .\sync_model_configs.ps1               Nur Report (Default)
  .\sync_model_configs.ps1 -Status       Nur Report (Default)
  .\sync_model_configs.ps1 -AutoAdd      Neue Modelle eintragen + configs + classify
  .\sync_model_configs.ps1 -FullSync     Komplett: add + configs + sync-ctx + classify + assemble + validate
  .\sync_model_configs.ps1 -SyncCtx      Nur context_length aus JSON -> Registry uebernehmen
  .\sync_model_configs.ps1 -FillCtx      Nur fehlende context_length: 16384 in Registry ergaenzen

ABLAUF (-AutoAdd / -FullSync):
  1. lms ls --json -> Modellliste (Hub-verwaltet)
  2. registry_tool.py compare -> Vergleichsreport
  3. registry_tool.py add -> fehlende Modelle eintragen
     (Architektur-Mapping, Default: k_cache=q8_0, v_cache=iq4_nl, offload=1, num_parallel=1/4)
  4. registry_tool.py configs -> load.fields in JSON-Configs schreiben
     (offloadRatio + numParallelSessions aus Registry)
  5. registry_tool.py sync-ctx -> context_length aus JSON-Configs in Registry (nur -FullSync)
  6. Pipeline: classify + assemble + validate (FullSync) / nur classify (AutoAdd)

WAS DAS SKRIPT NICHT MACHT:
  - Keine model.yaml im Hub erstellen (riskiert HTTP-500-Konflikt)
  - Keine Jinja-Templates kopieren (nur Gemma-4, manuell)
  - Keine verwaisten Configs loeschen
  - Keine manuell gesetzten k_cache/v_cache ueberschreiben
"@
    exit 0
}

$SR = Split-Path -Parent $PSCommandPath
$RT = Join-Path $SR "registry_tool.py"
$RP = Join-Path (Join-Path $SR "doc-git") "model_registry.yaml"
$AS = Join-Path $SR "assemble_blueprint.py"
$CR = Join-Path (Join-Path (Join-Path $env:USERPROFILE ".lmstudio") ".internal") "user-concrete-model-default-config"
$LJ = Join-Path $env:TEMP "lms_models_snapshot.json"

if (!(Test-Path $RP)) { Write-Error "Registry nicht gefunden: $RP"; exit 1 }

# LMS-Liste
try {
    Write-Host "[1] LMS-Modellliste (lms ls --json) ..." -ForegroundColor Cyan
    $raw = lms ls --json 2>$null
    $raw | Out-File -FilePath $LJ -Encoding utf8 -Force
    $c = python -c "import json; print(len(json.load(open('$($LJ.Replace('\','/'))','r',encoding='utf-8-sig'))))"
    Write-Host "  -> $c Modelle" -ForegroundColor Green
} catch { Write-Warning "lms ls fehlgeschlagen: $_"; $c = 0 }

# Vergleich (via registry_tool.py)
Write-Host "[2] Registry <> LMS <> Configs (registry_tool.py compare) ..." -ForegroundColor Cyan
$cmp = python $RT compare
try { $r = $cmp | ConvertFrom-Json } catch { Write-Warning "Vergleich fehlgeschlagen: $_"; $r = $null }

if ($r) {
    Write-Host "`n========== SYNC-REPORT ==========" -ForegroundColor Cyan
    Write-Host "  LMS:      $($r.lms) Modelle"
    Write-Host "  Registry: $($r.reg) Eintraege"
    Write-Host "  Configs:  $($r.cfg) JSON-Dateien"
    if ($r.new -gt 0) {
        Write-Host "`n  [+NEU] LMS ohne Registry ($($r.new)):" -ForegroundColor Yellow
        foreach ($m in $r.newd) {
            $v = ""; if ($m.vision) { $v = " [Vision]" }
            $t = ""; if ($m.tools) { $t = " [ToolUse]" }
            Write-Host "    $($m.key) ($($m.publisher), $($m.arch), $($m.params))$v$t" -ForegroundColor Yellow
        }
    } else { Write-Host "`n  [+NEU] Alle LMS-Modelle in Registry" -ForegroundColor Green }
    if ($r.missing -gt 0) {
        Write-Host "`n  [NICHT IN LMS] Registry ohne lms-ls-Eintrag ($($r.missing))" -ForegroundColor DarkGray
        Write-Host "    (manuell importierte GGUFs, die nicht via lms ls gelistet werden)" -ForegroundColor DarkGray
    }
    if ($r.orphan -gt 0) {
        Write-Host "`n  [VERWAIST] Configs ohne Registry ($($r.orphan)):" -ForegroundColor DarkYellow
        foreach ($oc in $r.orphd) { Write-Host "    $oc" -ForegroundColor DarkYellow }
    }
    Write-Host "================================"
}

if ($AutoAdd -or $FullSync) {
    if ($r -and $r.new -gt 0) {
        Write-Host "[3] Neue Modelle zur Registry (registry_tool.py add) ..." -ForegroundColor Cyan
        $mj = [System.IO.Path]::GetTempFileName() + ".json"
        $mjContent = $r.newd | ConvertTo-Json -Compress
        # PowerShell 5.1 single-element-array Bug
        if ($r.newd.Count -eq 1) { $mjContent = "[$mjContent]" }
        $mjContent | Out-File -FilePath $mj -Encoding utf8 -Force
        $am = python $RT add $mj
        Remove-Item $mj -Force -ErrorAction SilentlyContinue
        try {
            $ra = $am | ConvertFrom-Json
            Write-Host "  -> $($ra.added.Count) hinzugefuegt, $($ra.skipped.Count) uebersprungen" -ForegroundColor Green
            foreach ($s in $ra.skipped) { Write-Host "     Uebersprungen: $($s[0]) - $($s[1])" -ForegroundColor DarkYellow }
        } catch { Write-Warning "Add fehlgeschlagen" }
    } else { Write-Host "[3] Keine neuen Modelle" -ForegroundColor Green }

    Write-Host "[4] JSON-Configs (load.fields) aus Registry schreiben (registry_tool.py configs) ..." -ForegroundColor Cyan
    $cu = python $RT configs
    try { $cur = $cu | ConvertFrom-Json; Write-Host "  -> $($cur.updated) geupdated, $($cur.skipped) skipped, $($cur.errors) errors" -ForegroundColor Green } catch { Write-Warning "configs fehlgeschlagen" }
}

if ($SyncCtx) {
    Write-Host "[S] context_length aus JSON-Configs in Registry (registry_tool.py sync-ctx) ..." -ForegroundColor Cyan
    python $RT sync-ctx 2>&1
} elseif ($FillCtx) {
    Write-Host "[S] Fehlende context_length: 16384 in Registry ergaenzt (registry_tool.py fill-ctx) ..." -ForegroundColor Cyan
    python $RT fill-ctx 2>&1
} elseif ($FullSync) {
    Write-Host "[5] context_length aus JSON-Configs in Registry (registry_tool.py sync-ctx) ..." -ForegroundColor Cyan
    python $RT sync-ctx 2>&1
    Write-Host "[6] Pipeline: classify + assemble + validate ..." -ForegroundColor Cyan
    python $AS classify 2>&1 | ForEach-Object { if ($_ -match "Updated|Reasoning:|Blueprint:") { Write-Host "  $_" } }
    python $AS assemble 2>&1 | ForEach-Object { if ($_ -match "Summary:|Error|OK]") { Write-Host "  $_" } }
    python $AS validate 2>&1
} elseif ($AutoAdd) {
    Write-Host "[5] Klassifikation ..." -ForegroundColor Cyan
    python $AS classify 2>&1 | ForEach-Object { if ($_ -match "Updated|Reasoning:|Blueprint:") { Write-Host "  $_" } }
}

Remove-Item $LJ -Force -ErrorAction SilentlyContinue
Write-Host "`nTipp: sync_model_configs.ps1 -SyncCtx fuer context_length-Sync, -FullSync fuer Komplettlauf." -ForegroundColor DarkGray
Write-Host "Fertig." -ForegroundColor Green

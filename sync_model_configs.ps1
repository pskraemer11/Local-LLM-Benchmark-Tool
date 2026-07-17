#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Synchronises newly downloaded LM Studio models with model_registry.yaml
    and runs the blueprint assembly pipeline.

.DESCRIPTION
    Detects new models (via lms ls --json + config scan), adds them to the
    registry if needed, and runs the blueprint workflow.

    Pipeline flow:
      1. lms ls --json -> model list
      2. registry_tool.py compare -> comparison report
      3. registry_tool.py sync -> full maintenance:
         add + fill-arch + configs + sync-from-configs + sync-ctx + fill-ctx + fmt
      4. classify + assemble + validate (FullSync only)

    What the script does NOT do:
      - No model.yaml creation in Hub (risks HTTP-500 conflict)
      - No Jinja template copying (Gemma-4 only, manual)
      - No orphaned config deletion
      - No manual override of k_cache/v_cache values

.PARAMETER Status
    Show report only (default).
    Displays: LMS models, Registry entries, JSON configs on disk,
    new models (LMS without Registry), orphan configs (no Registry entry),
    Registry entries not in LMS.

.PARAMETER AutoAdd
    Add new models to Registry + sync configs + classify.
    Runs: sync (add + fill-arch + configs + sync-from-configs + sync-ctx + fill-ctx + fmt)
    Then classify.
    Result: models in Registry, JSON configs written, classification up-to-date.

.PARAMETER FullSync
    Full maintenance: AutoAdd + assemble + validate.
    Runs: sync + classify + assemble + validate.
    Recommended after downloading several new models.

.PARAMETER SyncCtx
    Only sync context_length from JSON configs to Registry (registry_tool.py sync-ctx).
    Without add/configs/pipeline.

.PARAMETER FillCtx
    Only fill missing context_length in Registry (registry_tool.py fill-ctx).
    Without add/configs/pipeline.

.PARAMETER FillArch
    Only fill n_layers/hidden_dim from GGUF headers (registry_tool.py fill-arch).
    Without add/configs/pipeline.

.PARAMETER FixNp
    Recompute num_parallel for all entries (registry_tool.py fix-np).

.PARAMETER FixCtx
    Recompute context_length for all entries (registry_tool.py fix-ctx).

.PARAMETER Help
    Show this help.

.EXAMPLE
    PS> .\sync_model_configs.ps1
    PS> .\sync_model_configs.ps1 -Status
    Status report only. No changes.

.EXAMPLE
    PS> .\sync_model_configs.ps1 -AutoAdd
    New LMS models are added to Registry, JSON configs synced, classified.

.EXAMPLE
    PS> .\sync_model_configs.ps1 -FullSync
    Complete sync incl. prompt assembly and validation.

.LINK
    https://github.com/anomalyco/opencode
    registry_tool.py (sync/compare/fix-np/fix-ctx/fill-arch)
    assemble_blueprint.py (classify/assemble/validate)
    model_registry.yaml, blueprint_definitions.yaml
#>
param(
    [switch]$Status,
    [switch]$AutoAdd,
    [switch]$FullSync,
    [switch]$SyncCtx,
    [switch]$FillCtx,
    [switch]$FillArch,
    [switch]$FixNp,
    [switch]$FixCtx,
    [switch]$Help
)

if ($Help -or !($Status -or $AutoAdd -or $FullSync -or $SyncCtx -or $FillCtx -or $FillArch -or $FixNp -or $FixCtx)) {
@"
SYNC-MODEL-CONFIGS: Synchronise LM Studio Models with Registry

USAGE:
  .\sync_model_configs.ps1                       Status report only (default)
  .\sync_model_configs.ps1 -Status               Status report only (default)
  .\sync_model_configs.ps1 -AutoAdd              Add new models + sync configs + classify
  .\sync_model_configs.ps1 -FullSync             Full: sync + classify + assemble + validate
  .\sync_model_configs.ps1 -SyncCtx              Only context_length JSON -> Registry
  .\sync_model_configs.ps1 -FillCtx              Only fill missing context_length
  .\sync_model_configs.ps1 -FillArch             Only fill n_layers/hidden_dim from GGUF headers
  .\sync_model_configs.ps1 -FixNp                Recompute num_parallel for all entries
  .\sync_model_configs.ps1 -FixCtx               Recompute context_length for all entries

PIPELINE (-AutoAdd / -FullSync):
  1. lms ls --json -> model list (Hub-managed)
  2. registry_tool.py compare -> comparison report
  3. registry_tool.py sync -> full pipeline:
     add (new models + GGUF arch data) + fill-arch + configs (VRAM-aware useUnifiedKvCache)
     + sync-from-configs + sync-ctx + fill-ctx + fmt
  4. classify (AutoAdd) / classify + assemble + validate (FullSync)

WHAT THE SCRIPT DOES NOT DO:
  - No model.yaml creation in Hub (risks HTTP-500 conflict)
  - No Jinja template copying (Gemma-4 only, manual)
  - No orphaned config deletion
  - No manual override of k_cache/v_cache
"@
    exit 0
}

$SR = Split-Path -Parent $PSCommandPath
$RT = Join-Path $SR "registry_tool.py"
$RP = Join-Path (Join-Path $SR "doc-git") "model_registry.yaml"
$AS = Join-Path $SR "assemble_blueprint.py"

if (!(Test-Path $RP)) { Write-Error "Registry not found: $RP"; exit 1 }

# Step 1: lms model list
try {
    Write-Host "[1] LMS model list (lms ls --json) ..." -ForegroundColor Cyan
    $c = python -c "import json, subprocess; r=subprocess.run(['lms','ls','--json'],capture_output=True,text=True,timeout=30); print(len(json.loads(r.stdout)))"
    Write-Host "  -> $c models" -ForegroundColor Green
} catch { Write-Warning "lms ls failed: $_"; $c = 0 }

# Step 2: comparison report
Write-Host "[2] Registry <> LMS <> Configs (registry_tool.py compare) ..." -ForegroundColor Cyan
python $RT compare

if ($FixNp) {
    Write-Host "[FIX-NP] Recomputing num_parallel for all entries ..." -ForegroundColor Cyan
    python $RT fix-np
    exit 0
}

if ($FixCtx) {
    Write-Host "[FIX-CTX] Recomputing context_length for all entries ..." -ForegroundColor Cyan
    python $RT fix-ctx
    exit 0
}

if ($FillArch) {
    Write-Host "[FILL-ARCH] Reading n_layers/hidden_dim from GGUF headers ..." -ForegroundColor Cyan
    python $RT fill-arch
    exit 0
}

if ($SyncCtx) {
    Write-Host "[SYNC-CTX] context_length from JSON configs to Registry ..." -ForegroundColor Cyan
    python $RT sync-ctx 2>&1
    exit 0
}

if ($FillCtx) {
    Write-Host "[FILL-CTX] Filling missing context_length in Registry ..." -ForegroundColor Cyan
    python $RT fill-ctx 2>&1
    exit 0
}

if ($AutoAdd -or $FullSync) {
    Write-Host "[3] Full sync (registry_tool.py sync) ..." -ForegroundColor Cyan
    Write-Host "    add + fill-arch + configs + sync-from-configs + sync-ctx + fill-ctx + fmt" -ForegroundColor DarkGray
    python $RT sync 2>&1
}

if ($AutoAdd) {
    Write-Host "[4] Classification ..." -ForegroundColor Cyan
    python $AS classify 2>&1 | ForEach-Object { if ($_ -match "Updated|Reasoning:|Blueprint:") { Write-Host "  $_" } }
}

if ($FullSync) {
    Write-Host "[4] Pipeline: classify + assemble + validate ..." -ForegroundColor Cyan
    python $AS classify 2>&1 | ForEach-Object { if ($_ -match "Updated|Reasoning:|Blueprint:") { Write-Host "  $_" } }
    python $AS assemble 2>&1 | ForEach-Object { if ($_ -match "Summary:|Error|OK]") { Write-Host "  $_" } }
    python $AS validate 2>&1
}

Write-Host "`nTip: sync_model_configs.ps1 -SyncCtx for context_length sync, -FullSync for full run." -ForegroundColor DarkGray
Write-Host "Done." -ForegroundColor Green

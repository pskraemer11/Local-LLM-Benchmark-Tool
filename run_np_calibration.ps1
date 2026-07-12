# run_np_calibration.ps1
# Misst np=1 vs np=4 Laufzeiten für 3 Architekturklassen
# SampleSize=10, TruthfulQA + MathQA, tok/s erfassen
#
# Nutzung: .\run_np_calibration.ps1
# Voraussetzung: LM Studio läuft (lms server), Modelle via lms ls sichtbar

$ScriptDir = "C:\Users\pskra\Python-Projekte\Benchmarks"
$LogFile   = Join-Path $ScriptDir "runs\2026\07\np_calibration_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
$Python    = "python"

# UTF-8 Encoding (siehe Code-Review_2026-07-12.md §7.7.10)
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

Set-Location -LiteralPath $ScriptDir

# ── Modelle & Config-Pfade ──────────────────────────────────────────
# Architekturklassen: Dense, MoE (Standard), MoE (Mamba2), MoE (Linear Attn),
#                     MoE (Banded Sparse), ERNIE (MoE-Ausnahme), Hybrid (MTP)
$Models = @(
    # ── Dense (Referenz) ──
    @{
        Label    = "Dense (Qwen2.5-Coder-14B Q6_K)"
        ModelKey = "qwen/qwen2.5-coder-14b-instruct-q6_k"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\qwen\Qwen2.5-Coder-14B-Instruct-GGUF\qwen2.5-coder-14b-instruct-q6_k.gguf.json"
        DefaultNp = 1               # Dense normal np=1 (LCP-Cache)
        TestNp    = @(1, 4)
    },
    # ── MoE (Mamba2 Hybrid) ──
    @{
        Label    = "MoE-Mamba2 (Granite-4.0-H-Tiny Q8_0)"
        ModelKey = "ibm-granite/granite-4.0-h-tiny-Q8_0"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\ibm-granite\granite-4.0-h-tiny-GGUF\granite-4.0-h-tiny-Q8_0.gguf.json"
        DefaultNp = 4
        TestNp    = @(1, 4)
    },
    # ── ERNIE (MoE-Ausnahme: Shared Experts, heterogen) ──
    @{
        Label    = "MoE-ERNIE (ERNIE-4.5-21B-A3B-PT IQ4_NL)"
        ModelKey = "unsloth/ERNIE-4.5-21B-A3B-PT-IQ4_NL"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\unsloth\ERNIE-4.5-21B-A3B-PT-GGUF\ERNIE-4.5-21B-A3B-PT-IQ4_NL.gguf.json"
        DefaultNp = 1               # ERNIE-Ausnahme np=1
        TestNp    = @(1, 4)
    },
    # ── MoE (Banded Sparse Attention) GPT-OSS MXFP4 ──
    @{
        Label    = "MoE-SparseAttn (GPT-OSS-20b MXFP4)"
        ModelKey = "lmstudio-community/gpt-oss-20b-MXFP4"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\lmstudio-community\gpt-oss-20b-GGUF\gpt-oss-20b-MXFP4.gguf.json"
        DefaultNp = 4
        TestNp    = @(1, 4)
    },
    # ── MoE (Banded Sparse Attention) GPT-OSS Q6_K ──
    @{
        Label    = "MoE-SparseAttn (GPT-OSS-20b Q6_K)"
        ModelKey = "unsloth/gpt-oss-20b-Q6_K"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\unsloth\gpt-oss-20b-GGUF\gpt-oss-20b-Q6_K.gguf.json"
        DefaultNp = 4
        TestNp    = @(1, 4)
    },
    # ── MoE (Linear Attention KDA+SSM+MLA) Kimi-Linear IQ2_S ──
    @{
        Label    = "MoE-LinearAttn (Kimi-Linear-48B IQ2_S)"
        ModelKey = "bartowski/moonshotai_Kimi-Linear-48B-A3B-Instruct-IQ2_S"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\bartowski\moonshotai_Kimi-Linear-48B-A3B-Instruct-GGUF\moonshotai_Kimi-Linear-48B-A3B-Instruct-IQ2_S.gguf.json"
        DefaultNp = 4
        TestNp    = @(1, 4)
    },
    # ── MoE (Gated DeltaNet + Attention) Qwen3.6-28B-REAP IQ3_S ──
    @{
        Label    = "MoE-DeltaNet (Qwen3.6-28B-REAP IQ3_S)"
        ModelKey = "mradermacher/Qwen3.6-28B-REAP.i1-IQ3_S"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\mradermacher\Qwen3.6-28B-REAP-i1-GGUF\Qwen3.6-28B-REAP.i1-IQ3_S.gguf.json"
        DefaultNp = 4
        TestNp    = @(1, 4)
    },
    # ── MoE (Gated DeltaNet + Attention) Qwen3.6-28B-REAP Q3_K_S ──
    @{
        Label    = "MoE-DeltaNet (Qwen3.6-28B-REAP Q3_K_S)"
        ModelKey = "mradermacher/Qwen3.6-28B-REAP.i1-Q3_K_S"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\mradermacher\Qwen3.6-28B-REAP-i1-GGUF\Qwen3.6-28B-REAP.i1-Q3_K_S.gguf.json"
        DefaultNp = 4
        TestNp    = @(1, 4)
    },
    # ── Qwen3.6-27B-MTP (Multi-Token Prediction) ──
    @{
        Label    = "MTP (Qwen3.6-27B-MTP UD-IQ3_XXS)"
        ModelKey = "unsloth/Qwen3.6-27B-UD-IQ3_XXS"
        Config   = "C:\Users\pskra\.lmstudio\.internal\user-concrete-model-default-config\unsloth\Qwen3.6-27B-MTP-GGUF\Qwen3.6-27B-UD-IQ3_XXS.gguf.json"
        DefaultNp = 1
        TestNp    = @(1, 4)
    }
)

$Benchmarks = @(
    "truthfulqa_mc1",
    "minerva_math500"
)

# ── Hilfsfunktionen ──────────────────────────────────────────────────

function Write-Log {
    param([string]$Msg)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Msg"
    Write-Output $line | Tee-Object -FilePath $LogFile -Append
}

function Set-NpInConfig {
    param([string]$ConfigPath, [int]$Np)
    if (-not (Test-Path $ConfigPath)) {
        Write-Log "  FEHLER: Config nicht gefunden: $ConfigPath"
        return $false
    }
    # Backup nur beim ersten Aufruf pro Modell
    $backup = "$ConfigPath.np_calib_bak"
    if (-not (Test-Path $backup)) {
        Copy-Item -Path $ConfigPath -Destination $backup -Force
        Write-Log "  Backup: $backup"
    }
    $json = Get-Content -Path $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $changed = $false
    foreach ($field in $json.load.fields) {
        if ($field.key -eq "llm.load.numParallelSessions") {
            if ($field.value -ne $Np) {
                $field.value = $Np
                $changed = $true
            }
            break
        }
    }
    if (-not $changed) {
        # Feld existiert nicht – anfügen
        $json.load.fields += @{
            key   = "llm.load.numParallelSessions"
            value = $Np
        }
        $changed = $true
    }
    if ($changed) {
        $json | ConvertTo-Json -Depth 10 | Set-Content -Path $ConfigPath -Encoding UTF8
        Write-Log "  Config np -> $Np"
    } else {
        Write-Log "  Config bereits np=$Np"
    }
    return $true
}

function Restore-Config {
    param([string]$ConfigPath)
    $backup = "$ConfigPath.np_calib_bak"
    if (Test-Path $backup) {
        Copy-Item -Path $backup -Destination $ConfigPath -Force
        Remove-Item -Path $backup -Force
        Write-Log "  Config zurückgesetzt (Backup restored)"
    }
}

function Invoke-LmEval {
    param([string]$ModelLabel, [string]$Benchmark, [int]$Np)
    $outputDir = Join-Path $ScriptDir "ergebnisse\np_calib_$(Get-Date -Format 'yyyyMMdd')"
    if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }
    
    $modelKeySafe = ($ModelLabel -replace '[^a-zA-Z0-9]', '_')
    $outputPath = Join-Path $outputDir "${modelKeySafe}_np${Np}_${Benchmark}"
    
        Write-Log "  >>> lm_eval $Benchmark (np=$Np)"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    
    $incPath = if (Test-Path "$ScriptDir\lm_eval_tasks\$Benchmark") { "--include_path", "$ScriptDir\lm_eval_tasks\$Benchmark" } else { @() }
    
    $result = & $Python -m lm_eval `
        --model local-chat-completions `
        --model_args "base_url=http://127.0.0.1:1234/v1/chat/completions,model=local,num_concurrent=1,eos_string=<|endoftext|>,max_tokens=1024,temperature=0.0,top_p=1.0" `
        --tasks $Benchmark `
        --limit 10 `
        --output_path $outputPath `
        --apply_chat_template `
        --log_samples `
        $incPath `
        2>&1
    
    $sw.Stop()
    $duration = $sw.Elapsed.TotalSeconds
    
    # tok/s aus Output parsen
    $tokensPerSec = 0
    foreach ($line in $result) {
        if ($line -match '(\d+\.?\d*)\s*tok/s') {
            $tokensPerSec = [double]$Matches[1]
        }
    }
    
    Write-Log "    Dauer: $([math]::Round($duration,1))s, tok/s: $tokensPerSec"
    return @{
        Benchmark   = $Benchmark
        Np          = $Np
        DurationSec = $duration
        TokPerSec   = $tokensPerSec
    }
}

# ── Hauptschleife ────────────────────────────────────────────────────

Write-Log "=== NP-Kalibrierung gestartet ==="
Write-Log "Modelle: $($Models.Count), Benchmarks: $($Benchmarks -join ', ')"
Write-Log "Log: $LogFile`n"

$results = @()

foreach ($model in $Models) {
    Write-Log "─── $($model.Label) ───"
    
    foreach ($np in $model.TestNp) {
        Write-Log "  Konfiguriere np=$np ..."
        if (-not (Set-NpInConfig -ConfigPath $model.Config -Np $np)) {
            Write-Log "  FEHLER: Config-Update fehlgeschlagen – überspringe np=$np"
            continue
        }
        
        # Modell neu laden (damit Config aktiv wird)
        Write-Log "  lms unload --all ..."
        & lms unload --all 2>&1 | Out-Null
        Start-Sleep -Seconds 3
        
        Write-Log "  lms load $($model.ModelKey) ..."
        & lms load $model.ModelKey --yes 2>&1 | Out-Null
        Start-Sleep -Seconds 10
        
        # Benchmarks
        foreach ($bench in $Benchmarks) {
            $r = Invoke-LmEval -ModelLabel $model.Label -Benchmark $bench -Np $np
            $r.ModelLabel = $model.Label
            $results += $r
        }
    }
    
    # Config zurücksetzen
    Restore-Config -ConfigPath $model.Config
}

# ── Ergebnis-Tabelle ─────────────────────────────────────────────────

Write-Log "`n=== ERGEBNISSE ==="
Write-Log "`nModell | Bench | np=1 tok/s | np=4 tok/s | Faktor"
Write-Log "-------|-------|------------|------------|-------"

$modelGroups = $results | Group-Object ModelLabel
foreach ($group in $modelGroups) {
    $benchGroups = $group.Group | Group-Object Benchmark
    foreach ($bg in $benchGroups) {
        $np1 = ($bg.Group | Where-Object { $_.Np -eq 1 }).TokPerSec
        $np4 = ($bg.Group | Where-Object { $_.Np -eq 4 }).TokPerSec
        $factor = if ($np1 -and $np4 -and $np1 -gt 0) { [math]::Round($np4 / $np1, 2) } else { "n/a" }
        Write-Log "$($group.Name) | $($bg.Name) | $([math]::Round($np1,2)) | $([math]::Round($np4,2)) | $factor"
    }
}

Write-Log "`n=== NP-Kalibrierung abgeschlossen: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Log "Log: $LogFile"

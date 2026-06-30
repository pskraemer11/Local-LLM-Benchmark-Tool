$models = @(
    "google/gemma-4-12b",
    "deepseek-r1-distill-qwen-14b",
    "lfm2.5-8b-a1b",
    "microsoft/phi-4",
    "mistralai/ministral-3-14b-reasoning",
    "openai/gpt-oss-20b",
    "qwen/qwen2.5-coder-14b"
)

foreach ($m in $models) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  Starte: $m" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan

    python benchmark_lmstudio_v18.py --non-interactive --model-key $m --sample-size 5 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[WARN] $m fehlgeschlagen (Exit $LASTEXITCODE), mache weiter..." -ForegroundColor Yellow
    }
}

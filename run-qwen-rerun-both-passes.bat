@echo off
REM Qwen-Nachlauf: Pass 1 (Qwen-Modelle) dann Pass 2 (andere fehlende)
REM Startet beide Benchmarks nacheinander
cd /d C:\Users\pskra\Python-Projekte\Benchmarks

echo [%date% %time%] Starte Pass 1: Qwen-Modelle
python src\run_benchmarks.py --run-spec run.qwen-re-run-pass1.yaml
echo [%date% %time%] Pass 1 fertig, starte Pass 2: Andere Modelle
python src\run_benchmarks.py --run-spec run.qwen-re-run-pass2.yaml
echo [%date% %time%] Beide Passes fertig

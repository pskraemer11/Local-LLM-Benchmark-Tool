@echo off
REM Qwen-Nachlauf: Pass 1 (Qwen-Modelle) dann Pass 2 (andere fehlende)
REM Startet beide Benchmarks nacheinander mit Logging
cd /d C:\Users\pskra\Python-Projekte\Benchmarks

set LOG1=Doku-intern\Terminalausgabe Benchmark-Qwen-Pass1_%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%.log
set ERR1=Doku-intern\Benchmark-Qwen-Pass1_stderr_%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%.log
set LOG2=Doku-intern\Terminalausgabe Benchmark-Qwen-Pass2_%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%.log
set ERR2=Doku-intern\Benchmark-Qwen-Pass2_stderr_%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%.log

echo [%date% %time%] Starte Pass 1: Qwen-Modelle
echo Log: %LOG1%
python src\run_benchmarks.py --run-spec run.qwen-re-run-pass1.yaml > "%LOG1%" 2> "%ERR1%"
echo [%date% %time%] Pass 1 fertig (Exit: %ERRORLEVEL%), starte Pass 2: Andere Modelle
echo Log: %LOG2%
python src\run_benchmarks.py --run-spec run.qwen-re-run-pass2.yaml > "%LOG2%" 2> "%ERR2%"
echo [%date% %time%] Beide Passes fertig (Exit: %ERRORLEVEL%)

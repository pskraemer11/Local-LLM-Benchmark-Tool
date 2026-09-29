#!/usr/bin/env bash
# install_debian.sh
# Installiert Abhaengigkeiten und laedt alle Benchmark-Datensaetze herunter.
# Ausfuehrung: bash install_debian.sh
# Getestet auf Debian 12 / Ubuntu 22.04+
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOWNLOAD_SCRIPT="$REPO_ROOT/download_real_benchmarks.py"
VENV_DIR="$REPO_ROOT/.venv"

echo "============================================================"
echo "  Install-Skript fuer lokale LLM-Benchmarks (Debian/Ubuntu)"
echo "============================================================"

# ─── 1. System-Pakete ───
echo ""
echo "[1/5] System-Pakete aktualisieren und Python sicherstellen..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git curl wget 2>/dev/null

# ─── 2. LM Studio-Pruefung ───
echo ""
echo "[2/5] Pruefe LM Studio..."
if command -v lms &>/dev/null; then
    echo "  [OK] lms gefunden: $(lms --version 2>&1)"
else
    echo "  [WARN] lms nicht im PATH."
    echo "  Installiere LM Studio von: https://lmstudio.ai/"
    echo "  (AppImage oder .deb von der Webseite)"
fi

# ─── 3. Virtual Environment ───
echo ""
echo "[3/5] Erstelle Python virtual environment..."
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  [OK] venv erstellt: $VENV_DIR"
else
    echo "  [OK] venv existiert bereits: $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ─── 4. Python-Pakete installieren ───
echo ""
echo "[4/5] Installiere Python-Abhaengigkeiten..."
PACKAGES=(
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

for pkg in "${PACKAGES[@]}"; do
    echo -n "  Installiere $pkg ... "
    if pip install --quiet "$pkg" 2>/dev/null; then
        echo "OK"
    else
        echo "FEHLGESCHLAGEN"
        echo "  [WARN] $pkg konnte nicht installiert werden."
        echo "         Manuelle Installation: pip install $pkg"
    fi
done

# NLTK Daten herunterladen (für TruthfulQA Tokenisierung)
echo -n "  Lade NLTK-Daten (punkt, punkt_tab) ... "
if python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True)" 2>/dev/null; then
    echo "OK"
else
    echo "FEHLGESCHLAGEN"
    echo "  [WARN] NLTK-Daten fehlen. TruthfulQA kann fehlschlagen."
fi

# ─── 5. Benchmark-Daten herunterladen ───
# DEPRECATED 12.07.2026: download_real_benchmarks.py ist nicht mehr
# in der aktiven Pipeline. Die simple_evals/ JSONL-Dateien sollten
# manuell via evalplus / HuggingFace CLI bezogen werden.
echo ""
echo "[5/5] Benchmark-Datensaetze..."
if [ -f "$DOWNLOAD_SCRIPT" ]; then
    echo "  [INFO] $DOWNLOAD_SCRIPT ist DEPRECATED (12.07.2026)."
    echo "  [INFO] Manuelle Installation empfohlen – siehe Skript-Header."
    echo "  [WARN] Datenformate entsprechen NICHT dem v13-Schema."
else
    echo "  [INFO] Kein Legacy-Skript gefunden. Manuelle Installation erforderlich."
fi

echo ""
echo "============================================================"
echo "  Installation abgeschlossen."
echo ""
echo "  Virtual Environment aktivieren:"
echo "    source .venv/bin/activate"
echo ""
echo "  Virtual Environment aktivieren (falls nicht bereits aktiv):"
echo "    source .venv/bin/activate"
echo ""
echo "  Benchmark starten:"
echo "    python run_benchmarks_v3.py --model <modell> --benchmarks all"
echo "============================================================"

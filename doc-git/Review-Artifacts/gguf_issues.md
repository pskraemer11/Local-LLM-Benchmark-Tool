# GGUF-Issues: model_registry.yaml vs. GGUF-Header

Erzeugt automatisch: 2026-08-06 21:21:28

Source of Truth: die GGUF-Dateien (unveraenderliche Modell-Fakten). Die
Registry wird hier gegen die GGUF-Header (n_layers, hidden_dim,
max_context_length) geprueft.

40 Registry-Eintraege mit GGUF-Datei abgeglichen.
2 Abweichungen:

- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: n_layers Registry=48 vs GGUF=4 (C:\Users\pskra\.lmstudio\models\unsloth\gemma-4-12B-it-qat-GGUF\mtp-gemma-4-12B-it-Q8_0.gguf)
- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: hidden_dim Registry=3840 vs GGUF=1024 (C:\Users\pskra\.lmstudio\models\unsloth\gemma-4-12B-it-qat-GGUF\mtp-gemma-4-12B-it-Q8_0.gguf)

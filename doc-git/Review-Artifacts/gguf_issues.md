# GGUF-Issues: model_registry.yaml vs. GGUF-Header

Generated automatically: 2026-08-11 16:48:09

Source of truth: the GGUF files (immutable model facts). The
registry is checked here against the GGUF headers (n_layers, hidden_dim,
max_context_length).

38 registry entries matched against GGUF files.
2 deviations:

- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: n_layers Registry=48 vs GGUF=4 (C:\Users\pskra\.lmstudio\models\unsloth\gemma-4-12B-it-qat-GGUF\mtp-gemma-4-12B-it-Q8_0.gguf)
- **unsloth/gemma-4-12b-it-qat@q4_k_xl**: hidden_dim Registry=3840 vs GGUF=1024 (C:\Users\pskra\.lmstudio\models\unsloth\gemma-4-12B-it-qat-GGUF\mtp-gemma-4-12B-it-Q8_0.gguf)

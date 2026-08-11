def cmd_fix_np() -> None:
    """Recompute arch classification + num_parallel, remove stale entries.

    Source of Truth: GGUF headers (architecture) + filesystem (deployment).
    LMS is NOT required — the tool is framework-independent.

    - Reads ``expert_count`` from GGUF header for MoE detection.
    - Drops entries whose GGUF file no longer exists on disk.
    - Collapses duplicate entries resolving to the same GGUF file.
    """
    reg = load_registry()

    # ── Build filesystem-based lookup: normalized base -> GGUF path ──
    fs_lookup: dict[str, Path] = {}  # normalized base key -> GGUF path
    for g in _get_all_ggufs():
        if not g.is_file():
            continue
        base = normalize_model_name(g.name).split("@")[0]
        if base not in fs_lookup:
            fs_lookup[base] = g


# Lint-Issues (ruff check . --no-fix)

Erzeugt: 2026-08-11 23:08:10

5 Probleme, Exit-Code 1

F841 Local variable `reg` is assigned to but never used
  --> temp_func.py:11:5
   |
 9 |     - Collapses duplicate entries resolving to the same GGUF file.
10 |     """
11 |     reg = load_registry()
   |     ^^^
12 |
13 |     # ÔöÇÔöÇ Build filesystem-based lookup: normalized base -> GGUF path ÔöÇÔöÇ
   |
help: Remove assignment to unused variable `reg`

F821 Undefined name `load_registry`
  --> temp_func.py:11:11
   |
 9 |     - Collapses duplicate entries resolving to the same GGUF file.
10 |     """
11 |     reg = load_registry()
   |           ^^^^^^^^^^^^^
12 |
13 |     # ÔöÇÔöÇ Build filesystem-based lookup: normalized base -> GGUF path ÔöÇÔöÇ
   |

F821 Undefined name `Path`
  --> temp_func.py:14:26
   |
13 |     # ÔöÇÔöÇ Build filesystem-based lookup: normalized base -> GGUF path ÔöÇÔöÇ
14 |     fs_lookup: dict[str, Path] = {}  # normalized base key -> GGUF path
   |                          ^^^^
15 |     for g in _get_all_ggufs():
16 |         if not g.is_file():
   |

F821 Undefined name `_get_all_ggufs`
  --> temp_func.py:15:14
   |
13 |     # ÔöÇÔöÇ Build filesystem-based lookup: normalized base -> GGUF path ÔöÇÔöÇ
14 |     fs_lookup: dict[str, Path] = {}  # normalized base key -> GGUF path
15 |     for g in _get_all_ggufs():
   |              ^^^^^^^^^^^^^^
16 |         if not g.is_file():
17 |             continue
   |

F821 Undefined name `normalize_model_name`
  --> temp_func.py:18:16
   |
16 |         if not g.is_file():
17 |             continue
18 |         base = normalize_model_name(g.name).split("@")[0]
   |                ^^^^^^^^^^^^^^^^^^^^
19 |         if base not in fs_lookup:
20 |             fs_lookup[base] = g
   |

Found 5 errors.
No fixes available (1 hidden fix can be enabled with the `--unsafe-fixes` option).


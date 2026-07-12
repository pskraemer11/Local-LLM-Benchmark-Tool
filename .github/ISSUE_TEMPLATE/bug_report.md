---
name: Bug report
about: Create a report to help us improve
title: ''
labels: bug
assignees: ''
---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Run command `python run_benchmarks_v13.py ...` with these args
2. Wait for benchmark `XYZ` to start
3. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Error output**
```
Paste the full Python traceback here. If the error is from
LM Studio (e.g. "Channel Error" or "Cannot combine structured
output"), also paste the relevant lines from
~/.lmstudio/server-logs/2026-MM/*.log
```

**Environment**
  - OS: [e.g. Windows 11, Debian 12]
  - Python: [output of `python --version`]
  - LM Studio version: [output of `lms --version`]
  - GPU + VRAM: [e.g. RTX 5070 Ti 16GB]
  - Model + Quant: [e.g. qwen3-30b-a3b-instruct-2507@Q3_K_S]
  - Branch: [output of `git branch --show-current`]

**Screenshots**
If applicable, add screenshots to help explain your problem.

**Additional context**
- Does the error happen for ALL models or just specific ones?
- Is this a regression (worked before, broken now) or new?
- Have you run `pytest tests/` locally? If so, do the dependency
  tests pass (`tests/test_dependencies.py`)?

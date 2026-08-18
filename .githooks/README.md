# Git Hooks

The repository uses versioned Git hooks through `core.hooksPath=.githooks`.

- `pre-commit`: staged whitespace, file-type, secret, Ruff, Python syntax and
  focused registry checks.
- `commit-msg`: non-empty conventional commit subject, 72-character limit and
  high-confidence secret patterns.
- `pre-push`: complete `pre_review_checks.ps1` run without skip switches plus
  the blocking focused mypy scope used by CI. Its review artifacts are
  temporary because the commit already exists when pre-push runs.

The extensionless files are Git hook entry points. They delegate to the
PowerShell helpers in this directory for Windows compatibility.

Activation in this clone:

```powershell
git config core.hooksPath .githooks
```

The hooks are intentionally not bypassed by the normal workflow. Use
`--no-verify` only for a documented emergency, then run the skipped checks
manually before pushing.

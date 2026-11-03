# Git Hooks

The repository uses versioned Git hooks through `core.hooksPath=.githooks`.

- `pre-commit`: commit author/committer identity and added staged text for
  prohibited email domains; added text is also checked for concrete Windows
  user-profile paths. It then runs whitespace, file-type, secret, Ruff, Python
  syntax and focused registry checks. Diagnostics never print matches.
- `commit-msg`: prohibited email-domain check, non-empty conventional commit
  subject, 72-character limit and high-confidence secret patterns.
- `pre-push`: checks outgoing author/committer metadata and commit messages for
  prohibited email domains, and added text for domains and profile paths in
  every outgoing commit (including merge-resolution diffs), then runs the
  complete pytest suite. It subsequently runs `pre_review_checks.ps1` with
  `-SkipPytest` to avoid a duplicate suite run, plus `-NoArtifacts` and
  `-NoTranscript`, and finally the blocking focused mypy scope used by CI.
  Its review artifacts are temporary because the commit already exists when
  pre-push runs.

The extensionless files are Git hook entry points. They delegate to the
PowerShell helpers in this directory for Windows compatibility.

Activation in this clone:

```powershell
git config core.hooksPath .githooks
```

The hooks are intentionally not bypassed by the normal workflow. Use
`--no-verify` only for a documented emergency, then run the skipped checks
manually before pushing.

The privacy gate blocks concrete `C:\Users\<profile>` paths in added text and
addresses using the `online.de`, `e-mail.de`, or `posteo.de` domains in commit
identities, commit messages, or added text. Portable variables such as `$HOME`
and explicit placeholders are allowed. CI runs the same history-aware check over
each base-to-head range. Push checks inspect only commits newly reachable through
the refs being pushed; they do not rewrite or audit already-published history.

## Bring-Schuld zum Projekt "automatisierter Benchmark-Abgleich"

- `post-commit`: Nach jedem Commit auf `main` in diesem Repository wird der Submodul-Pointer im
  Projekt `automatisierter Benchmark-Abgleich` (`external/benchmarks`) auf den neuen `main`-Stand
  gehoben und dort committet. Das Verbraucherprojekt laedt die gemeinsame Identitaets- und
  Inventarlogik (`src/model_identity.py`, `src/benchmark_config.py` und Nachbarn) in gepinnter Form
  und muss nichts selbst nachziehen.
- Der Hook ist nie blockierend: Fehler werden nach `%LOCALAPPDATA%\OpenAI\Codex\benchmark-abgleich-submodule.log`
  protokolliert, der Commit laeuft weiter. Ohne Verbraucherprojekt, auf einem anderen Branch oder
  bei bereits aktuellem Pointer passiert nichts.
- Der Pfad zum Verbraucherprojekt ist ueber die Umgebungsvariable `BENCHMARK_ABGLEICH_REPO` anpassbar.
- Hinweis: `data/model_registry.yaml` ist im Arbeitsbaum des Verbraucherprojekts weiterhin nicht
  enthalten, weil die Datei konkrete Nutzerpfade enthaelt und damit vom Privacy-Gate nicht
  versioniert werden darf. Der Code laedt sie optional zur Laufzeit; fuer `get_quant()` wirkt dann
  der Quantisierungs-Fallback.

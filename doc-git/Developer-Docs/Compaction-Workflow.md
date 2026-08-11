# Compaction & Changelog Workflow

## Overview

Two complementary documentation processes prevent context loss and maintain project history:

1. **Compaction** — Session-level context preservation (narrative, decisions, next moves)
2. **Changelog** — File-level change tracking (technical, granular, reference)

## Trigger Matrix (Event-Based)

| Event | Compaction | Changelog |
|-------|-----------|-----------|
| `git commit` / `git push` | ✅ Create | ✅ Update |
| Architecture decision / Bug root cause | ✅ Create | ✅ If files changed |
| ~20-30 messages threshold | ✅ Create | ✅ If substantive |
| ≥2x per active day | ✅ Create | — |
| `/compaction` command | ✅ Create | — |
| Short routine session (< 10 msgs) | ❌ | — |

## Compaction Format

**File:** `Doku-intern/Chatverlauf OpenCode LLM Benchmark+Compaction_Jun-Aug_2026.md`

```
=============== Compaction DD.MM.YYYY / HH:MM ================
## Objective
- (Current) ...
- (Completed) ...

## Important Details
- **Key Decision:** Rationale
- **Bug Found:** Root cause + fix

## Work State
### Completed / Active / Blocked

## Next Move
1. ...

## Relevant Files
- `path/file`: Change summary
```

## Changelog Format

**File:** `CHANGELOG.md`

```
## <Title> (DD.MM.YYYY)

| Date | File | Change |
|------|------|--------|
| DD.MM. | `path/file` | **type:** Description. See Compaction DD.MM.YYYY |
```

## Overlap Resolution

| CHANGELOG | Compaction |
|-----------|-----------|
| File paths | Session narrative |
| Parameter changes | Why decisions were made |
| Technical details | What is blocked |
| Command references | Next moves |

**Rule:** CHANGELOG = *what* changed. Compaction = *why* and *what's next*. Link, don't duplicate.

## Automation

### Compaction Detection
- Agent monitors conversation token count
- At ~80% of model context window: announce and create compaction
- User can request `/compaction` at any time

### Changelog on Commit/Push
- Pre-commit hook: remind if substantive changes lack CHANGELOG entry
- Pre-push hook: verify CHANGELOG updated since last push
- Not blocking — advisory only (CHANGELOG can be updated retroactively)

## File Locations

- Skill: `~/.agents/skills/compaction/SKILL.md`
- Compaction output: `Doku-intern/Chatverlauf*.md`
- Changelog: `CHANGELOG.md` (project root)
- Hooks: `scripts/hooks/`

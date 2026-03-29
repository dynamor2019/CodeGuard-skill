// Policy: Do not modify directly. Explain reason before edits. Last confirm reason: Align skill with low-blocking lock model and user-approved unlock flow

---
name: codeguard-skill
description: Guide Codex through CodeGuard's local version protection and feature indexing workflow with low interruption for beginners. Use when the user wants token-efficient indexed editing, explicit success confirmation, and safe lock diagnostics/unlock by consent.
---

# CodeGuard

Use `python scripts/codeguard.py ...` as the single official project-local workflow.
Treat `python scripts/codeguard-cli.py ...` as a compatibility alias layer.
Use `python cli/codeguard_cli.py ...` only when the user explicitly needs a global launcher.

## Product Intent (Must Follow)

CodeGuard exists to help beginners understand project structure and reduce token usage by indexed targeting.
CodeGuard is not a hard lock system.

## Core Rules

1. Never declare success based on tests/lint/runtime checks alone; require explicit user confirmation.
2. Persist success only with `confirm`.
3. Use `snapshot` only when the user explicitly marks a milestone as important.
4. Files over 200 lines require a feature index before edit/backup/confirm/snapshot.
5. Before creating/updating a required feature index, ask user authorization.
6. Keep feature labels short, human-readable, and token-efficient.
7. Prefer index-guided narrow reads over broad scans.
8. Do not write failure states into permanent records.
9. Keep edits minimal and feature-scoped; avoid full-file rewrites without approval.
10. For JSON/YAML/TOML and similar files, use sidecar indexes (`<file>.codeguard-index.json`).
11. Use `doctor` for metadata drift; avoid manual `index.json` edits unless necessary.
12. Lock contention must be low-friction: diagnose quickly, do not stall workflows.

## Lock Model (Low-Blocking)

1. Lock file existence is normal; lock ownership is what matters.
2. On lock-related failures, first run `python scripts/codeguard.py lock-status`.
3. Do not wait long on lock contention; use short timeout (`--lock-timeout`, default low).
4. Unlock is allowed when the developer consents.
5. Prefer stale-lock cleanup over forceful unlocking of active locks.

## Token-Efficient Mode

Use this mode by default in medium/large projects:

1. Read budget:
   - First read only the indexed target block (about 40 lines).
   - If unresolved, expand once (about 120 lines).
   - If still unresolved, read one directly related dependency file.
2. Scope budget:
   - Deep-read at most 3 files per round unless broad audit is requested.
3. Edit budget:
   - Prefer targeted patches; avoid full-file rewrites without approval.
4. Validation budget:
   - Validate touched files first; avoid repo-wide checks unless requested.
5. Reporting budget:
   - Keep reports short and action-focused.

## Feature Index Format

For large files, place the index near the top using the file's comment style.
For non-comment-friendly files, maintain a sidecar index.

Inline example:

```python
# [CodeGuard Feature Index]
# - Request parsing -> line 42
# - Snapshot write path -> line 118
# - Rollback validation -> line 203
# [/CodeGuard Feature Index]
```

Sidecar example (`config.json.codeguard-index.json`):

```json
{
  "file": "config.json",
  "updated_at": "2026-03-10T12:00:00",
  "line_count": 420,
  "file_hash": "...",
  "entries": [
    {"feature": "Model routing", "line": 35},
    {"feature": "Retry policy", "line": 96}
  ]
}
```

## Editing Workflow

When the user asks to edit a file:

1. Check whether the file is over 200 lines.
2. If over 200 lines, run `show-index` or `validate-index`.
3. If required index is missing/invalid, ask authorization before updating it.
4. Update index after approval.
5. Run `backup` before approved edits.
6. Apply minimal, feature-scoped changes.
7. Ask the user whether outcome is successful.
8. Run `confirm` only after explicit user confirmation.
9. Refresh index entries for touched large files after confirmed success.
10. Use `snapshot` only when user marks milestone as important.
11. If command fails due to lock contention: run `lock-status` first; then `unlock --yes` only with user consent.

## Observability and Recovery

- `python scripts/codeguard.py status <file>`: file health summary.
- `python scripts/codeguard.py status <file> --json`: machine-readable status.
- `python scripts/codeguard.py list <file>`: latest retained snapshot info.
- `python scripts/codeguard.py doctor`: metadata/index/snapshot integrity scan.
- `python scripts/codeguard.py doctor --repair`: safe metadata repair.
- `python scripts/codeguard.py batch validate-index <files...>`: batch validation.
- `python scripts/codeguard.py batch backup <files...>`: batch backup.
- `python scripts/codeguard.py lock-status`: lock diagnostics and next actions.
- `python scripts/codeguard.py unlock --yes`: clear stale lock after explicit consent.
- Add `--lock-timeout <seconds>` when custom wait behavior is needed.

## Command Reference

| Command | Purpose |
| --- | --- |
| `python scripts/codeguard.py validate-index <file>` | Validate feature index and over-200-lines rule |
| `python scripts/codeguard.py backup <file>` | Create pre-modification backup |
| `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` | Persist user-confirmed success |
| `python scripts/codeguard.py snapshot <file> "<feature>" "<reason>"` | Create manual important snapshot |
| `python scripts/codeguard.py status <file>` | One-command health view |
| `python scripts/codeguard.py doctor [--repair]` | Diagnose or repair metadata consistency |
| `python scripts/codeguard.py lock-status` | Diagnose lock state quickly |
| `python scripts/codeguard.py unlock --yes` | User-approved stale lock cleanup |
| `python scripts/codeguard.py rollback <file> --version N` | Restore a previous snapshot |

## Project Files

- `.codeguard/index.json`: snapshot history, accepted state, and index freshness metadata.
- `.codeguard/index.lock`: lock file for safe concurrent operations.
- `.codeguard/versions/`: important milestone snapshots.
- `.codeguard/temp/`: pre-modification backups.
- `.codeguard/records/modifications.md`: user-confirmed success records.

Ignore `.codeguard/` in VCS unless user explicitly asks to commit it.

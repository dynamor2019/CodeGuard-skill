// Policy: Do not modify directly. Explain reason before edits. Last confirm reason: Align skill instructions with new automation flags

﻿---
name: codeguard-skill
description: Guide Codex through CodeGuard's local version protection and feature indexing workflow. Use when the user wants to protect completed code, work without Git or network access, require mandatory feature indexes for files over 200 lines, confirm success only after the user verbally approves it, create manual milestone snapshots, or roll back to a project-local snapshot.
---

# CodeGuard

Use `python scripts/codeguard.py ...` as the single official project-local workflow.
Treat `python scripts/codeguard-cli.py ...` as a compatibility alias layer.
Use `python cli/codeguard_cli.py ...` only when the user explicitly needs a global launcher.

## Core Rules

1. Treat tests, lint, and runtime checks as evidence only. Do not call a change successful unless the user explicitly says it succeeded.
2. Record a permanent success only with `confirm`. `confirm` updates the accepted current state and writes the success record.
3. Use `snapshot` only when the user explicitly marks a milestone as important.
4. Require a feature index for every file over 200 lines before editing, backing up, confirming, or snapshotting that file.
5. Before generating or updating a required feature index, stop and ask for user authorization.
6. Keep feature labels short and readable. Use a brief feature phrase, not a paragraph, function list, or change log.
7. Use the feature index to target the relevant code block. Do not re-read or rewrite unrelated large sections when the index already identifies the needed area.
8. Keep failure states out of the permanent record. If the user does not confirm success, do not call `confirm` and do not create a milestone snapshot.
9. Snapshot retention is latest-only per file. A new confirmed/snapshot state replaces older CodeGuard snapshots for that file.
10. Modification record retention is latest-only. `modifications.md` stores only the most recently confirmed success.
9. For file types that cannot safely host comments (for example JSON/YAML/TOML), use sidecar index files (`<file>.codeguard-index.json`) instead of writing inline blocks.
10. For metadata incidents or drift, run `doctor` before manual cleanup. Prefer automatic safe repair over ad-hoc edits to `index.json`.
11. Treat token efficiency as a first-class objective: prefer index-guided narrow reads over broad file scans.
12. Run index refresh/update for touched large files at the end of a successful cycle (after user confirmation), not repeatedly during intermediate failed attempts.

## Token-Efficient Mode

Use this mode by default in medium/large projects:

1. Read budget:
   - First read only the indexed target block ±40 lines.
   - If unresolved, expand once to ±120 lines.
   - If still unresolved, read one directly related dependency file.
2. Scope budget:
   - Deep-read at most 3 files per round unless the user asks for broad audit.
3. Edit budget:
   - Prefer minimal patch edits; do not rewrite entire files without explicit user approval.
4. Validation budget:
   - Validate exactly the touched files first; do not run repository-wide checks unless requested.
5. Reporting budget:
   - Keep progress/final reports concise and action-focused.

## Feature Index Format

For large files, place the index near the top of the file using the file's comment style.
For non-comment-friendly files, maintain a sidecar index file.

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

Rules for entries:

- Use `- <feature label> -> line <number>` (inline) or `{"feature": "...", "line": N}` (sidecar).
- Point to the start line of the code block that implements that feature.
- Describe a user-meaningful feature block, not just a single function name.
- Keep labels short enough to scan quickly.
- Sort entries by ascending line number.

## Editing Workflow

When the user asks to edit a file:

1. Check whether the file is over 200 lines.
2. If the file is over 200 lines, inspect the current index with `show-index` or `validate-index`.
3. If the index is missing or invalid, stop and ask for authorization before generating or updating it.
4. After approval, update the index with `python scripts/codeguard.py index <file> --entry "Feature:Line" ...`.
5. Create a pre-modification backup with `python scripts/codeguard.py backup <file>` before making the approved edit.
6. Make the requested change by targeting the indexed feature block instead of reworking the entire file.
7. Ask the user whether the result actually succeeded.
8. Run `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` only after the user explicitly confirms success.
9. After confirmation, refresh/update index entries for touched large files so next rounds can locate code faster with fewer tokens.
10. Run `python scripts/codeguard.py snapshot <file> "<feature>" "<reason>"` only when the user explicitly marks an important milestone.
11. If the user says the change failed, do not confirm it. Offer inspection, further fixes, or `rollback`.

## Observability and Recovery

Use these commands proactively during troubleshooting and bulk edits:

- `python scripts/codeguard.py status <file>`: one-shot health view (protection marker, accepted state, index health, latest snapshot, rollback readiness).\n- `python scripts/codeguard.py status <file> --json`: machine-readable file health output for scripts and CI checks. JSON payload now includes `schema_version`, `report_type`, `generated_at`, and `index_summary` (`required`/`missing`/`stale`) for automation decisions.
- `python scripts/codeguard.py list <file>`: latest retained snapshot and accepted state summary.
- `python scripts/codeguard.py doctor`: project-wide metadata and snapshot/index integrity scan.
- `python scripts/codeguard.py doctor --repair`: safe metadata repair (schema normalization and `last_version` mismatch fix).\n- `python scripts/codeguard.py doctor --json`: machine-readable project health report for automation/integration.
- `python scripts/codeguard.py batch validate-index <file1> <file2> ...`: batch validation.
- `python scripts/codeguard.py batch backup <file1> <file2> ...`: batch backup.
- `python scripts/codeguard.py batch status <file1> <file2> ...`: batch status checks.

## Protect Completed Code

When the user says a feature is complete and should be protected:

1. Choose a short, stable feature name.
2. If the file is over 200 lines, make sure the feature index already exists or ask permission to create/update it first.
3. Run `python scripts/codeguard.py add <file> "<feature>"`.
4. Explain that this creates the initial important snapshot and protection marker.

## Rollback Rules

Use rollback only after explicit approval because it overwrites the current file state.

- `python scripts/codeguard.py rollback <file> --version N`
- `python scripts/codeguard.py rollback <file> --feature "<feature>"`
- Add `--yes` only when approval is already explicit or the user asked for a scripted flow.

Explain that rollback also creates a `.rollback-backup.<timestamp>.bak` file next to the target file.

## Command Reference

| Command | Purpose |
| --- | --- |
| `python scripts/codeguard.py init` | Create `.codeguard/` state in the current project |
| `python scripts/codeguard.py add <file> "<feature>"` | Add or refresh a protection marker and create the initial important snapshot |
| `python scripts/codeguard.py index <file> --entry "Feature:Line"` | Create or update the feature index (inline or sidecar) |
| `python scripts/codeguard.py show-index <file>` | Show the current feature index |
| `python scripts/codeguard.py validate-index <file>` | Validate the current feature index and the over-200-lines rule |
| `python scripts/codeguard.py backup <file>` | Create a pre-modification backup |
| `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` | Record a user-confirmed success without creating a milestone snapshot |
| `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true --refresh-index [files...]` | After successful confirm, refresh index entries for the confirmed file and optional extra files |
| `python scripts/codeguard.py snapshot <file> "<feature>" "<reason>"` | Create a user-marked important snapshot |
| `python scripts/codeguard.py list <file>` | Show the latest retained important snapshot plus accepted-state metadata |
| `python scripts/codeguard.py status <file>` | Show protection/index/snapshot/rollback status in one command |
| `python scripts/codeguard.py doctor [--repair]` | Diagnose or repair metadata/snapshot consistency |
| `python scripts/codeguard.py batch <action> <files...>` | Run validate-index, backup, or status in batch mode |
| `python scripts/codeguard.py rollback <file> --version N` | Restore a previous important snapshot |

## Project Files

Store project-local state here:

- `.codeguard/index.json`: snapshot history, accepted current state, protected features, and index freshness metadata.
- `.codeguard/index.lock`: lock file used for safe concurrent index writes.
- `.codeguard/versions/`: important milestone snapshots.
- `.codeguard/temp/`: pre-modification backups.
- `.codeguard/records/modifications.md`: user-confirmed success records only.

Ignore `.codeguard/` in version control unless the user explicitly wants the metadata committed.

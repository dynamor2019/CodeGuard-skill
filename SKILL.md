---
name: codeguard-skill
description: Guide Codex through CodeGuard's local version protection and feature indexing workflow. Use when the user wants to protect completed code, work without Git or network access, require mandatory feature indexes for files over 200 lines, confirm success only after the user verbally approves it, create manual milestone snapshots, or roll back to a project-local snapshot.
---

# CodeGuard

Use `python scripts/codeguard.py ...` as the single official project-local workflow.
Treat `python scripts/codeguard-cli.py ...` as a compatibility alias layer.
Use `python cli/codeguard_cli.py ...` only when the user explicitly needs a global launcher.

## Core Rules

1. Treat tests, lint, and runtime checks as evidence only. Do not call a change successful unless the user explicitly says it succeeded.
2. Record a permanent success only with `confirm`. `confirm` updates the accepted current state and writes the success record, but it does not create a new snapshot.
3. Create a snapshot only when the user explicitly marks the current state as important. Use `snapshot` for that milestone.
4. Require a feature index for every file over 200 lines before editing, backing up, confirming, or snapshotting that file.
5. Before generating or updating a required feature index, stop and ask for user authorization.
6. Keep feature labels short and readable. Use a brief feature phrase, not a paragraph, function list, or change log.
7. Use the feature index to target the relevant code block. Do not re-read or rewrite unrelated large sections when the index already identifies the needed area.
8. Keep failure states out of the permanent record. If the user does not confirm success, do not call `confirm` and do not create a milestone snapshot.

## Feature Index Format

For large files, place the index near the top of the file using the file's comment style.

Example:

```python
# [CodeGuard Feature Index]
# - Request parsing -> line 42
# - Snapshot write path -> line 118
# - Rollback validation -> line 203
# [/CodeGuard Feature Index]
```

Rules for entries:

- Use `- <feature label> -> line <number>`.
- Point to the start line of the code block that implements that feature.
- Describe a user-meaningful feature block, not just a single function name.
- Keep labels short enough to scan quickly.
- Sort entries by ascending line number.

## Editing Workflow

When the user asks to edit a file:

1. Check whether the file is over 200 lines.
2. If the file is over 200 lines, inspect the current index with `show-index` or `validate-index`.
3. If the index is missing, stale, or incomplete, stop and ask for authorization before generating or updating it.
4. After approval, update the index with `python scripts/codeguard.py index <file> --entry "Feature:Line" ...`.
5. Create a pre-modification backup with `python scripts/codeguard.py backup <file>` before making the approved edit.
6. Make the requested change by targeting the indexed feature block instead of reworking the entire file.
7. Ask the user whether the result actually succeeded.
8. Run `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` only after the user explicitly confirms success.
9. If the user says the state is important, run `python scripts/codeguard.py snapshot <file> "<feature>" "<reason>"`.
10. If the user says the change failed, do not confirm it. Offer inspection, further fixes, or `rollback`.

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
| `python scripts/codeguard.py index <file> --entry "Feature:Line"` | Create or update the feature index |
| `python scripts/codeguard.py show-index <file>` | Show the current feature index |
| `python scripts/codeguard.py validate-index <file>` | Validate the current feature index and the over-200-lines rule |
| `python scripts/codeguard.py backup <file>` | Create a pre-modification backup |
| `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` | Record a user-confirmed success without creating a milestone snapshot |
| `python scripts/codeguard.py snapshot <file> "<feature>" "<reason>"` | Create a user-marked important snapshot |
| `python scripts/codeguard.py list <file>` | List important snapshots for a file |
| `python scripts/codeguard.py rollback <file> --version N` | Restore a previous important snapshot |

## Project Files

Store project-local state here:

- `.codeguard/index.json`: snapshot history and accepted current-state metadata keyed by project-relative file path
- `.codeguard/versions/`: important milestone snapshots
- `.codeguard/temp/`: pre-modification backups
- `.codeguard/records/modifications.md`: user-confirmed success records only

Ignore `.codeguard/` in version control unless the user explicitly wants the metadata committed.

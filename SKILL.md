---
name: codeguard-skill
description: Protect completed or sensitive code from accidental edits by requiring explicit approval before modifying protected regions, creating project-local snapshots and backups, and recording only successful modifications. Use when the user wants to protect a finished feature, add or inspect CodeGuard markers, confirm safe edits to protected code, or rollback a protected file.
---

# CodeGuard

Use the project-local workflow by default. Prefer `python scripts/codeguard.py ...` for repository work. `python scripts/codeguard-cli.py ...` is a compatibility command surface that now delegates to the same project-local snapshot model. Use `python cli/codeguard_cli.py ...` only when the user explicitly asks to install or inspect the legacy global CLI.

## Detect Protection

Treat these patterns as protected:

- `// Feature Protection: ... [Completed]`
- `// Feature Protection: ... [Verified]`
- `// Feature Protection: ... [Stable]`
- `# Feature Protection: ... [Completed|Verified|Stable]`
- `/* Feature Protection: ... */`
- `[CodeGuard Protection]`

Treat `[Development]`, `[To Optimize]`, and `[Temporarily Disabled]` as editable states, but still suggest a backup before editing.

## Required Workflow Before Editing Protected Code

When the requested change overlaps a protected region, follow this sequence:

1. Inspect existing snapshots with `python scripts/codeguard.py list <file>`.
2. Stop and ask whether the author or owner approved the edit.
3. Refuse to modify the protected region if approval is not confirmed.
4. Create a pre-edit backup with `python scripts/codeguard.py backup <file>` after approval is confirmed.
5. Make the requested change.
6. Ask whether the feature now works as intended.
7. Run `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` only after the user confirms success.
8. Skip the permanent record if the user says the feature is still broken, and offer `python scripts/codeguard.py rollback <file> --version N`.

Do not claim approval, successful verification, or implementation status unless the user explicitly confirms it.

## Add Protection To Completed Code

When the user says a feature is complete or asks to protect it:

1. Choose a short, stable feature name.
2. Run `python scripts/codeguard.py add <file> "<feature>"`.
3. Confirm that the file now has a protection block and a snapshot in `.codeguard/versions/`.
4. Avoid stacking duplicate protection headers. If the file is already protected, treat the operation as a snapshot refresh.

## Rollback Rules

Use rollback only after explicit approval because it overwrites the current file state.

- `python scripts/codeguard.py rollback <file> --version N`
- `python scripts/codeguard.py rollback <file> --feature "<feature>"`
- Add `--yes` only in scripted or test flows where approval already exists.

Explain that rollback also stores the current state as a `.rollback-backup.<timestamp>.bak` file next to the target file.

## Commands

| Command | Purpose |
| --- | --- |
| `python scripts/codeguard.py init` | Create the `.codeguard/` workspace in the current project |
| `python scripts/codeguard.py add <file> "<feature>"` | Add or refresh a protection marker and create a snapshot |
| `python scripts/codeguard.py backup <file>` | Create a pre-modification backup for an approved edit |
| `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` | Promote the current file to a new snapshot and write a permanent record |
| `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" false` | Leave the temp backup in place and skip the permanent record |
| `python scripts/codeguard.py list <file>` | Show snapshot history for a file |
| `python scripts/codeguard.py rollback <file> --version N` | Restore a previous snapshot |

## Project Files

Store project-local state here:

- `.codeguard/index.json`: snapshot metadata keyed by project-relative file path
- `.codeguard/versions/`: immutable snapshot backups
- `.codeguard/temp/`: pre-modification backups
- `.codeguard/records/modifications.md`: permanent success-only records

Ignore `.codeguard/` in version control unless the user explicitly wants the metadata committed.

## Safety Rules

- Prefer project-relative reasoning. Same basenames in different directories must be treated as different files.
- Record only successful modifications in the permanent record.
- Preserve the temp backup when the user says a change failed.
- Warn before batch edits that would touch protected and unprotected regions together.
- Suggest protection for verified, high-risk, or business-critical code, but do not force it without user intent.

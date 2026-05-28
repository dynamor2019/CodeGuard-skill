---
name: codeguard-skill
description: Low-friction local backup and version protection for CodeGuard. Auto-backup before edits, with optional feature indexing and milestone snapshots. Use when you need safe file edits with rollback capability.
---

# CodeGuard

Use `python scripts/codeguard.py ...` as the single official project-local workflow.

## Product Intent

CodeGuard protects beginners by auto-backing up files before every edit, so mistakes are always reversible.
It does NOT block, slow down, or add extra steps to the normal editing workflow.
The backup is invisible — it just works, and you only interact with it when you need to recover.

## Core Rules

1. **Run `guard` before editing important or complex files.** It creates a pre-edit backup and detects encoding. For trivial typo fixes, skipping is fine — the risk is low.
2. **Never inject markers or comments into source files by default.** All metadata lives in `.codeguard/`. Explicit marker injection is opt-in: use `add` (without `--no-marker`) or `confirm --add-marker`.
3. **For files over 200 lines, use the feature index as the primary navigation tool.** Target the specific feature section (~40 lines around the indexed line) instead of reading the entire file. If an index is missing, generate one — it's the key to token-efficient editing on large files.
4. **Hash drift during development is normal.** Sync the baseline silently and continue — it's not a failure.
5. **Use `confirm` only for explicit milestones.** Not every edit needs confirmation. A backup is enough for routine work.
6. **Lock contention must resolve fast.** Default timeout is under 1 second. Diagnose stale locks quickly, never stall workflows.

## Daily Workflow

This is the standard workflow for every edit:

```
# Step 1: Guard the file (backup + encoding detection + index status)
python scripts/codeguard.py guard <file>

# Step 2: If file is >200 lines, check the index
#   - guard says "index: 8 entries" → use show-index to navigate
#   - guard says "index: MISSING" → generate one:
python scripts/codeguard.py index <file> --auto

# Step 3: Read only the target section (~40 lines around the feature line)
# Step 4: Apply the minimal edit

# Step 5: If things went wrong → undo
python scripts/codeguard.py undo <file>

# Step 6: Done. Backup is in .codeguard/temp/ if needed later.
```

## When Things Go Wrong

```
# Quick undo: restore from the most recent guard backup
python scripts/codeguard.py undo <file>
python scripts/codeguard.py undo <file> --list    # see all undo points
python scripts/codeguard.py undo <file> --yes     # skip confirmation

# Quick health check on a file
python scripts/codeguard.py status <file>

# List available snapshot versions
python scripts/codeguard.py list <file>

# Rollback to a specific snapshot
python scripts/codeguard.py rollback <file> --version N

# Check everything
python scripts/codeguard.py doctor
python scripts/codeguard.py doctor --repair

# Diagnose lock issues
python scripts/codeguard.py lock-status
python scripts/codeguard.py unlock --yes
```

## Milestone Workflow (Important Changes Only)

Use this when marking a confirmed success or important checkpoint:

```
# 1. Guard and edit as usual
python scripts/codeguard.py guard <file> --feature "<name>" --reason "<why>" --tier strict

# 2. Edit the file

# 3. Confirm the milestone (creates snapshot + record)
python scripts/codeguard.py confirm <file> "<name>" "<reason>" true
```

## Feature Index (Large File Navigation)

**Files over 200 lines MUST have a feature index for efficient editing.** The index maps key functions/sections to line numbers, enabling ~40-line targeted reads instead of reading the entire file. Without an index, every edit on a large file burns tokens reading code that isn't relevant to the change.

The `guard` command reports index status for files over 200 lines:
- `index: 8 entries` — use `show-index` to navigate, target ~40-line reads
- `index: MISSING` — run `index --auto` before editing

```
# Auto-generate an index (up to 8 entries, sampled across the file)
python scripts/codeguard.py index <file> --auto

# Manual entries for precision (recommended for critical files)
python scripts/codeguard.py index <file> --entry "Request parsing:42" --entry "Auth flow:156"

# Show current index for navigation
python scripts/codeguard.py show-index <file>

# Check if index is stale (hash changed since last index update)
python scripts/codeguard.py validate-index <file>
```

### How to Use the Index When Editing

When `guard` reports an index is available:

1. **First read**: `show-index` to see the feature map, then read only the relevant section (~40 lines around the target line number).
2. **If the edit crosses feature boundaries**: expand to ~120 lines spanning both features.
3. **If you need context from another file**: read one directly related dependency.
4. **After editing**: refresh the index if line numbers shifted.

This cuts token consumption on large files by ~85% compared to full-file reads.

## Lock Model

- Lock files are normal — they prevent concurrent index corruption.
- Default lock timeout is 0.8 seconds — never blocks for long.
- If a lock is stale (no active process), clean it: `python scripts/codeguard.py unlock --yes`
- Never force-unlock an occupied lock unless you're certain the other process is dead.

## Token-Efficient Reading

When working with indexed files in large projects:

1. **First read**: target the index block and the specific feature section (~40 lines around the target line).
2. **If unresolved**: expand the read window (~120 lines).
3. **If still unresolved**: read one directly related dependency file.
4. **Deep-read at most 3 files per round** unless a broad audit is explicitly requested.
5. **Prefer targeted patches** over full-file rewrites.

## Token Compression Mode (Caveman)

CodeGuard includes a Caveman-style output compression system that reduces response tokens without losing technical accuracy. Use this when you want terse, action-focused responses.

### Compression Levels

| Level | Behavior | Use Case |
| --- | --- | --- |
| **lite** | Drop filler/pleasantries at sentence edges. Keep articles and full sentences. Professional but tight. | When you want brevity without losing polish. |
| **full** (default) | Drop articles, filler, hedging. Fragments OK. Short synonyms. Technical terms exact. | Daily development work. Best balance of speed and clarity. |
| **ultra** | Full + drop articles, be-verbs, arrows for causality (->). Abbreviate aggressively. One word when enough. | Max token savings on long sessions. |

### Compression Rules (Full/Ultra)

When operating in compressed mode:

**Drop:**
- Articles: a, an, the
- Filler: just, really, basically, actually, simply, very, quite, rather
- Hedging: maybe, perhaps, I think, it seems like, in my opinion
- Pleasantries: sure, certainly, of course, happy to

**Keep exact:**
- Code blocks and inline code (never modified)
- Technical terms, function names, file paths
- Error messages and stack traces
- Security warnings and irreversible action confirmations

**Style:**
- Fragments are OK (not full sentences)
- Use short synonyms (e.g., "can" not "be able to")
- Pattern: [thing] [action] [reason]. [next step].

**Auto-clarity carve-out:** Automatically drop compression and use full prose for:
- Security warnings and vulnerability reports
- Irreversible actions (force push, database drops, production deploys)
- Multi-step sequences where clarity prevents mistakes
- When the user is confused or asks for normal mode

### Compressing Files

Use the `compress` command to shrink verbose prose files. **Only works on prose formats** (.md, .txt, .rst, .adoc). Code files (.py, .js, etc.) are rejected — compressing code would corrupt syntax.

```bash
# Preview compressed output
python scripts/codeguard.py compress CLAUDE.md --level full

# Compress in-place (creates guard-style backup with encoding metadata)
python scripts/codeguard.py compress CLAUDE.md --level full --in-place
```

This is especially useful for:
- Compressing CLAUDE.md / AGENTS.md files to reduce per-session token burn
- Shrinking verbose documentation before attaching as context
- Reducing skill file size without losing technical content

### How to Activate

Compression mode is activated by the skill itself when the user requests it, or when working in token-constrained contexts. Say "stop caveman" or "normal mode" to disable.

## Feature Index Format

For large files, place the index near the top using the file's comment style.
For non-comment-friendly files (JSON, YAML, TOML, etc.), maintain a sidecar index (`<file>.codeguard-index.json`).

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

## Command Reference

| Command | Purpose |
| --- | --- |
| `python scripts/codeguard.py init` | Initialize CodeGuard in a project |
| `python scripts/codeguard.py guard <file> --feature "..." --reason "..."` | Pre-edit backup + encoding detection |
| `python scripts/codeguard.py guard <file> --tier lite` | Minimal guard: backup only, no snapshot |
| `python scripts/codeguard.py guard <file> --tier standard` | Standard guard: backup + encoding detection (default) |
| `python scripts/codeguard.py guard <file> --tier strict` | Strict guard: backup + encoding + snapshot |
| `python scripts/codeguard.py guard <file> --json` | Machine-readable guard output |
| `python scripts/codeguard.py undo <file>` | Restore from most recent guard backup (quick undo) |
| `python scripts/codeguard.py undo <file> --list` | List available undo points |
| `python scripts/codeguard.py backup <file>` | Pre-modification backup (legacy, use guard instead) |
| `python scripts/codeguard.py backup <file> --strict-conflict` | Fail on hash drift for release/security checks |
| `python scripts/codeguard.py sync-current <file>` | Sync current file state as development baseline |
| `python scripts/codeguard.py confirm <file> "<feature>" "<reason>" true` | Record user-confirmed milestone (optional) |
| `python scripts/codeguard.py confirm <file> ... --add-marker` | Same + inject CodeGuard marker into source file |
| `python scripts/codeguard.py snapshot <file> "<feature>" "<reason>"` | Manual important snapshot |
| `python scripts/codeguard.py rollback <file> --version N` | Restore a previous snapshot |
| `python scripts/codeguard.py list <file>` | List snapshot versions for a file |
| `python scripts/codeguard.py status <file>` | One-command file health view |
| `python scripts/codeguard.py status <file> --json` | Machine-readable status |
| `python scripts/codeguard.py doctor` | Diagnose metadata/index/snapshot integrity |
| `python scripts/codeguard.py doctor --repair` | Safe auto-repair of metadata issues |
| `python scripts/codeguard.py lock-status` | Diagnose lock state |
| `python scripts/codeguard.py unlock --yes` | Clean stale lock |
| `python scripts/codeguard.py add <file> "<feature>"` | Add protection marker + create initial snapshot |
| `python scripts/codeguard.py add <file> "<feature>" --no-marker` | Same but skip marker injection |
| `python scripts/codeguard.py index <file> --auto` | Auto-generate feature index (up to 8 entries) |
| `python scripts/codeguard.py index <file> --entry "Label:42"` | Manual index entry |
| `python scripts/codeguard.py show-index <file>` | Display current feature index |
| `python scripts/codeguard.py validate-index <file>` | Validate feature index |
| `python scripts/codeguard.py compress <file> --level full` | Preview compressed prose output |
| `python scripts/codeguard.py compress <file> --in-place` | Compress file in-place (creates backup) |
| `python scripts/codeguard.py token-tips` | Show token-saving guidance and diagnostics |
| `python scripts/codeguard.py batch backup <files...>` | Batch backup multiple files |
| `python scripts/codeguard.py batch validate-index <files...>` | Batch validate indexes |
| `python scripts/codeguard.py batch index <files...> --auto` | Batch auto-generate indexes |
| `python scripts/codeguard.py schema [status\|doctor\|batch]` | Show JSON schema metadata |

## Project Files

- `.codeguard/index.json`: snapshot history, accepted state, index metadata.
- `.codeguard/index.lock`: lock file for safe concurrent operations.
- `.codeguard/versions/`: milestone snapshots.
- `.codeguard/temp/`: pre-modification backups (auto-created by guard).
- `.codeguard/records/modifications.md`: user-confirmed success records.

Ignore `.codeguard/` in VCS unless explicitly asked to commit it.

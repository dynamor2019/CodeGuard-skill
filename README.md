# CodeGuard Skill

CodeGuard helps AI-assisted coding workflows avoid accidental edits to completed or sensitive code. It adds lightweight protection markers, stores project-local snapshots in `.codeguard/`, requires explicit approval before protected edits, and records only successful modifications.

## Canonical Entry Points

- Skill definition: `SKILL.md`
- Codex UI metadata: `agents/openai.yaml`
- Project-local workflow: `scripts/codeguard_v2.py`
- Compatibility wrapper: `scripts/codeguard-v2.py`
- Legacy repository CLI: `scripts/codeguard-cli.py`

## Quick Start

Requires Python 3.10 or newer.

```bash
# Initialize project-local state
python scripts/codeguard_v2.py init

# Protect a completed file or feature
python scripts/codeguard_v2.py add src/auth.js "User Authentication"

# Inspect snapshots before editing protected code
python scripts/codeguard_v2.py list src/auth.js

# Create an approved pre-edit backup
python scripts/codeguard_v2.py backup src/auth.js

# Confirm a successful modification
python scripts/codeguard_v2.py confirm src/auth.js "User Authentication" "Fix token refresh bug" true

# Roll back to an earlier snapshot
python scripts/codeguard_v2.py rollback src/auth.js --version 1
```

## Install Into An IDE

Use the shared installer to copy the canonical skill bundle into a local IDE skills folder.

```bash
# Auto-detect supported IDE skill folders
python scripts/install_bundle.py

# Install to a specific skills directory
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry

# Also install the legacy global CLI launcher
python scripts/install_bundle.py --install-cli
```

Supported auto-detect targets currently include Trae, Trae CN, Cursor, and VS Code style `skills/` folders.

## Command Model

- `scripts/codeguard_v2.py` is the canonical project-local implementation.
- `scripts/codeguard-v2.py` is a thin filename-compatible wrapper around the same core.
- `scripts/codeguard-cli.py` keeps older command names like `lock`, `record`, and `status`, but now writes snapshots and confirmations through the same project-local core.
- `cli/codeguard_cli.py` is the legacy global launcher for editor integrations that expect a `codeguard` executable.

## Repository Layout

```text
codeguard-skill/
|- SKILL.md
|- agents/openai.yaml
|- scripts/codeguard_v2.py
|- scripts/codeguard-v2.py
|- scripts/codeguard-cli.py
|- scripts/install_bundle.py
|- cli/codeguard_cli.py
`- .trae/skills/codeguard-skill.json
```

## Notes

- The default workflow is project-local. Snapshot data lives in `.codeguard/` inside the working project.
- The global CLI remains available for older integrations, but new automation should prefer `scripts/codeguard_v2.py`.
- `.codeguard/` and generated backup files should normally stay out of version control.

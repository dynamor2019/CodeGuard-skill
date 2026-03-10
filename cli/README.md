# CodeGuard Global CLI

This folder contains the legacy global `codeguard` launcher. It can still be useful for older editor integrations, but the preferred repository workflow is the project-local snapshot tool in `scripts/codeguard_v2.py`.

## Install

Requires Python 3.10 or newer.

```bash
# Install the skill bundle into detected IDE skill folders
python install.py

# Install the bundle and the global CLI launcher
python install.py --install-cli
```

On Windows the launcher is installed into `%USERPROFILE%\.codeguard\bin`. On macOS and Linux it is installed into `~/.local/bin`.

## Global CLI Commands

```bash
codeguard add src/auth.js userAuth
codeguard check src/auth.js
codeguard analyze src/app.js
codeguard index src/app.js
codeguard status
```

## Preferred Alternative

For repository work, use:

```bash
python ../scripts/codeguard_v2.py add src/auth.js "User Authentication"
python ../scripts/codeguard_v2.py backup src/auth.js
python ../scripts/codeguard_v2.py confirm src/auth.js "User Authentication" "Fix token refresh bug" true
```

If you still need the older repository-local command surface, `../scripts/codeguard-cli.py` now shares the same snapshot core and supports commands such as `add`, `backup`, `record`, `confirm`, `list`, and `rollback`.

# CodeGuard Global CLI

This folder contains the legacy global `codeguard` launcher. It can still be useful for older editor integrations, but the preferred repository workflow is the project-local snapshot tool in `scripts/codeguard.py`.

这个目录包含旧版全局 `codeguard` 启动器。它仍然适合旧编辑器集成，但仓库内推荐的工作方式已经统一为 `scripts/codeguard.py`。

## Install

Requires Python 3.10 or newer.

需要 Python 3.10 或更高版本。

```bash
# Install the skill bundle into detected IDE skill folders
# 安装技能包到检测到的 IDE 技能目录
python install.py

# Install the bundle and the global CLI launcher
# 同时安装技能包和全局 CLI 启动器
python install.py --install-cli
```

On Windows the launcher is installed into `%USERPROFILE%\.codeguard\bin`. On macOS and Linux it is installed into `~/.local/bin`.

在 Windows 上，启动器会安装到 `%USERPROFILE%\.codeguard\bin`。在 macOS 和 Linux 上，会安装到 `~/.local/bin`。

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

对于仓库内开发，推荐使用：

```bash
python ../scripts/codeguard.py add src/auth.js "User Authentication"
python ../scripts/codeguard.py backup src/auth.js
python ../scripts/codeguard.py confirm src/auth.js "User Authentication" "Fix token refresh bug" true
```

If you still need the older repository-local command surface, `../scripts/codeguard-cli.py` now shares the same snapshot core and supports commands such as `add`, `backup`, `record`, `confirm`, `list`, and `rollback`.

如果你仍然需要旧的仓库内命令面，`../scripts/codeguard-cli.py` 现在也复用了同一套快照核心，支持 `add`、`backup`、`record`、`confirm`、`list` 和 `rollback` 等命令。

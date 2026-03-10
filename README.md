# CodeGuard Skill

CodeGuard helps AI-assisted coding workflows avoid accidental edits to completed or sensitive code. It adds lightweight protection markers, stores project-local snapshots in `.codeguard/`, requires explicit approval before protected edits, and records only successful modifications.

CodeGuard 用来保护已经完成或敏感的代码，避免在 AI 辅助编码流程中被误改。它会添加轻量级保护标记，在项目本地的 `.codeguard/` 中保存快照，在修改受保护代码前要求明确确认，并且只记录成功的修改结果。

## Canonical Entry Points

核心入口如下：

- Skill definition: `SKILL.md`
- 技能定义文件：`SKILL.md`
- Codex UI metadata: `agents/openai.yaml`
- Codex 界面元数据：`agents/openai.yaml`
- Project-local workflow: `scripts/codeguard.py`
- 项目内主命令：`scripts/codeguard.py`
- Legacy repository CLI: `scripts/codeguard-cli.py`
- 兼容旧命令面：`scripts/codeguard-cli.py`

## Quick Start

Requires Python 3.10 or newer.

需要 Python 3.10 或更高版本。

```bash
# Show the installed CodeGuard version
# 查看当前 CodeGuard 版本
python scripts/codeguard.py --version

# Initialize project-local state
# 初始化项目本地状态目录
python scripts/codeguard.py init

# Protect a completed file or feature
# 为已完成文件或功能加保护标记
python scripts/codeguard.py add src/auth.js "User Authentication"

# Inspect snapshots before editing protected code
# 修改受保护代码前查看历史快照
python scripts/codeguard.py list src/auth.js

# Create an approved pre-edit backup
# 在获批后创建修改前备份
python scripts/codeguard.py backup src/auth.js

# Confirm a successful modification
# 确认修改成功并写入正式记录
python scripts/codeguard.py confirm src/auth.js "User Authentication" "Fix token refresh bug" true

# Roll back to an earlier snapshot
# 回滚到较早版本的快照
python scripts/codeguard.py rollback src/auth.js --version 1
```

## Install Into An IDE

Use the shared installer to copy the canonical skill bundle into a local IDE skills folder.

使用共享安装脚本可以把标准技能包复制到本地 IDE 的 `skills` 目录中。

```bash
# Auto-detect supported IDE skill folders
# 自动检测支持的 IDE 技能目录
python scripts/install_bundle.py

# Install to a specific skills directory
# 安装到指定的 skills 目录
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry

# Also install the legacy global CLI launcher
# 同时安装旧版全局 CLI 启动器
python scripts/install_bundle.py --install-cli
```

Supported auto-detect targets currently include Trae, Trae CN, Cursor, and VS Code style `skills/` folders.

当前支持自动检测的目标包括 Trae、Trae CN、Cursor，以及 VS Code 风格的 `skills/` 目录。

## Command Model

- `scripts/codeguard.py` is the single official project-local implementation.
- `scripts/codeguard.py` 是唯一官方的项目内实现。
- `scripts/codeguard-cli.py` keeps older command names like `lock`, `record`, and `status`, but now writes snapshots and confirmations through the same project-local core.
- `scripts/codeguard-cli.py` 保留了 `lock`、`record`、`status` 等旧命令名，但底层已经复用同一套项目内核心逻辑。
- `cli/codeguard_cli.py` is the legacy global launcher for editor integrations that expect a `codeguard` executable.
- `cli/codeguard_cli.py` 是给旧编辑器集成使用的全局启动器，适用于仍然要求 `codeguard` 可执行命令的场景。

## Repository Layout

```text
codeguard-skill/
|- SKILL.md
|- agents/openai.yaml
|- scripts/codeguard.py
|- scripts/codeguard-cli.py
|- scripts/install_bundle.py
|- cli/codeguard_cli.py
`- .trae/skills/codeguard-skill.json
```

## Notes

- The default workflow is project-local. Snapshot data lives in `.codeguard/` inside the working project.
- 默认工作方式是项目内模式，快照数据保存在当前项目的 `.codeguard/` 目录里。
- The global CLI remains available for older integrations, but new automation should prefer `scripts/codeguard.py`.
- 全局 CLI 仍然保留给旧集成使用，但新的自动化和新文档都应优先使用 `scripts/codeguard.py`。
- `.codeguard/` and generated backup files should normally stay out of version control.
- `.codeguard/` 和自动生成的备份文件通常不应提交到版本控制。

# CodeGuard Skill

CodeGuard is a local, AI-friendly version protection workflow for vibe-coding beginners.
It is not a Git replacement. It is a lightweight project-local layer that helps AI and humans work more safely when Git feels too heavy, network access is unavailable, or the goal is to reduce token waste during iterative coding.

CodeGuard solves two problems at the same time:

- Protect accepted work with local backups, confirmations, and important snapshots.
- Reduce token waste on large files by forcing a short feature index at the top of files over 200 lines.

中文说明：

CodeGuard 是一个面向 vibe coding 初学者的本地版本保护工作流。
它不是 Git 的替代品，而是在 Git 门槛较高、网络条件不稳定、或者你更想先把项目在本地稳住的情况下，为 AI 协作编程提供一层更轻量的保护。

它同时解决两个问题：

- 用本地备份、成功确认和重要快照保护已经验证过的成果。
- 对超过 200 行的大文件强制建立顶部功能索引，让 AI 可以精准定位目标代码块，减少无效上下文和 token 浪费。

## Why It Exists

Most AI coding tools still waste context in large files. They either read too much or compress everything together, which often mixes useful and useless context.

CodeGuard takes a different path:

- Only record success after the user explicitly says the result worked.
- Only create milestone snapshots when the user explicitly marks the current state as important.
- For large files, make AI maintain a simple feature index so it can jump directly to the relevant block instead of rereading the whole file.

为什么要做这个：

现在很多 AI 编程工具在处理大文件时，仍然会浪费大量上下文。要么整文件通读，要么把有用和没用的信息一起压缩。

CodeGuard 的思路不同：

- 只有用户明确口头确认“这次改动成功了”，才记录为成功结果。
- 只有用户明确说“这个版本很重要”，才创建重要快照。
- 对大文件强制建立简洁的功能索引，让 AI 可以直接跳到相关代码块，而不是反复通读整个文件。

## Core Rules

1. Success means user confirmation. Tests passing is not enough.
2. Important versions are manual snapshots. `confirm` does not create a snapshot.
3. Files over 200 lines must have a feature index before editing, backup, confirm, or snapshot.
4. AI must ask for user authorization before generating or updating a required feature index.
5. Feature labels must stay short, readable, and human-oriented.
6. Failed states do not become permanent records.

核心规则：

1. 成功只以用户确认作为准绳，测试通过不等于成功。
2. 重要版本必须由用户手动标记，`confirm` 不会自动创建快照。
3. 超过 200 行的文件，在编辑、备份、确认或快照之前必须有功能索引。
4. 当大文件缺少索引或索引需要更新时，AI 必须先征得用户授权，才能生成或更新索引。
5. 功能标签必须简短、清晰、以人能快速扫描理解为准。
6. 失败状态不会进入永久记录。

## Feature Index Format

For files over 200 lines, CodeGuard requires a feature index near the top of the file.
The index describes feature blocks, not just function names.

Example:

```python
# [CodeGuard Feature Index]
# - Request parsing -> line 42
# - Snapshot write path -> line 118
# - Rollback validation -> line 203
# [/CodeGuard Feature Index]
```

Guidelines:

- Use one short feature phrase per entry.
- Point to the start line of the code block that implements that feature.
- A feature block may span multiple functions.
- Keep entries sorted by ascending line number.
- Avoid labels that read like documentation paragraphs.

功能索引格式：

对于超过 200 行的文件，CodeGuard 要求在文件顶部附近维护一个功能索引。
这里索引的不是函数名，而是“实现某个单一功能的代码块”。

示例：

```python
# [CodeGuard Feature Index]
# - Request parsing -> line 42
# - Snapshot write path -> line 118
# - Rollback validation -> line 203
# [/CodeGuard Feature Index]
```

约束：

- 每一项都用一句很短的功能短语。
- 行号指向该功能代码块的起始行。
- 一个功能块可以跨越多个函数。
- 条目必须按起始行升序排列。
- 不要把标签写成一大段说明文。

## Recommended Workflow

1. Protect a completed feature with `add`.
2. Before editing, create a pre-modification backup with `backup`.
3. If the file is large, inspect or update the feature index first.
4. Make the change.
5. Ask the user whether the change really succeeded.
6. If the user says yes, run `confirm`.
7. If the user says the current state is important, run `snapshot`.
8. If the change goes wrong, use `rollback`.

推荐工作流：

1. 当某个功能完成并需要保护时，用 `add`。
2. 真正修改前，先用 `backup` 创建修改前备份。
3. 如果是大文件，先检查或更新功能索引。
4. 再进行修改。
5. 修改后必须问用户这次结果是否真正成功。
6. 用户确认成功后，再执行 `confirm`。
7. 如果用户说这个状态很重要，再执行 `snapshot`。
8. 如果后续改乱了，就用 `rollback` 快速恢复。

## Commands

```bash
# Show the installed version
python scripts/codeguard.py --version

# Initialize project-local state
python scripts/codeguard.py init

# Protect a completed file or feature and create the initial important snapshot
python scripts/codeguard.py add src/auth.py "User Authentication"

# Create or update a feature index after user approval
python scripts/codeguard.py index src/auth.py --entry "Request parsing:42" --entry "Token refresh:118"

# Inspect the current feature index
python scripts/codeguard.py show-index src/auth.py

# Validate the feature index and the >200-lines rule
python scripts/codeguard.py validate-index src/auth.py

# Create a pre-modification backup
python scripts/codeguard.py backup src/auth.py

# Record a user-confirmed successful change without creating a snapshot
python scripts/codeguard.py confirm src/auth.py "User Authentication" "Fix token refresh bug" true

# Manually mark the current state as an important version
python scripts/codeguard.py snapshot src/auth.py "User Authentication" "Stable release candidate"

# Roll back to an important snapshot
python scripts/codeguard.py rollback src/auth.py --version 1
```

## Official Entry Points

There is one official project-local implementation:

- `scripts/codeguard.py`

Compatibility layers:

- `scripts/codeguard-cli.py` is a compatibility wrapper around the same local workflow.
- `cli/codeguard_cli.py` is a global launcher that forwards commands to the local project script.

官方入口说明：

真正的官方项目内实现只有一个：

- `scripts/codeguard.py`

兼容层说明：

- `scripts/codeguard-cli.py` 只是对同一套本地工作流的兼容包装。
- `cli/codeguard_cli.py` 只是把全局命令转发到项目内脚本的启动器。

## Project Files

- `.codeguard/index.json`: snapshot history and accepted current state
- `.codeguard/versions/`: important version snapshots
- `.codeguard/temp/`: pre-modification backups
- `.codeguard/records/modifications.md`: success-only permanent records

项目内状态目录：

- `.codeguard/index.json`：快照历史和当前已接受状态
- `.codeguard/versions/`：重要版本快照
- `.codeguard/temp/`：修改前备份
- `.codeguard/records/modifications.md`：只记录成功结果的永久记录

## Install Into An IDE

```bash
# Auto-detect supported IDE skill folders
python scripts/install_bundle.py

# Install into a specific skills directory
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry

# Also install the global launcher
python scripts/install_bundle.py --install-cli
```

支持安装到本地 IDE 技能目录：

```bash
# 自动检测支持的 IDE 技能目录
python scripts/install_bundle.py

# 安装到指定技能目录
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry

# 同时安装全局启动器
python scripts/install_bundle.py --install-cli
```

## Notes

- CodeGuard is local-first and works without network access.
- It is especially useful when Git is too much friction for the current user or environment.
- `.codeguard/` and generated backup files should usually stay out of version control.

补充说明：

- CodeGuard 是本地优先的，不依赖网络。
- 当用户暂时不想碰 Git，或者网络环境不稳定时，它尤其有用。
- `.codeguard/` 和自动生成的备份文件通常不应提交到版本控制。

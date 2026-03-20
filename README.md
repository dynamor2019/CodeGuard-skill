# CodeGuard

Local version protection and feature indexing for AI-assisted coding.

CodeGuard is built for vibe-coding beginners who want a safer workflow before Git becomes second nature.
It is not a Git replacement. It is a local-first layer for protecting accepted work, guiding AI edits in large files, and reducing token waste during iterative coding.

CodeGuard solves a very practical problem:

- AI can change code quickly, but it can also disturb code that already works.
- Git is powerful, but for many beginners it still has learning cost, workflow cost, and sometimes network dependence.
- Large files waste context because AI often rereads too much or compresses useful and useless information together.

CodeGuard takes a simpler path:

- Record success only after the user explicitly says the result worked.
- Create milestone snapshots only when the user manually marks the current state as important.
- Force a short feature index for files over 200 lines so AI can jump directly to the right code block instead of rereading the whole file.

## 中文说明

CodeGuard 是一个面向 vibe coding 初学者的本地版本保护与功能索引工具。
它不是 Git 的替代品，而是一层更轻量、更适合 AI 协作编程的本地工作流：先保护已经验证成功的成果，再让 AI 在清晰边界内继续修改代码。

它想解决的是一个非常现实的问题：

- AI 改代码很快，但也很容易把已经能工作的部分一起改乱。
- Git 很强大，但对很多初学者来说，依然有学习门槛、操作门槛，甚至还有网络和同步层面的现实限制。
- 大文件特别浪费上下文，AI 往往不是读太多，就是把有用和没用的信息一起压缩。

CodeGuard 的做法更直接：

- 只有用户明确确认“这次真的成功了”，才把结果记录为成功。
- 只有用户明确说“这个版本很重要”，才创建快照。
- 对超过 200 行的大文件，强制建立简短的功能索引，让 AI 可以直接定位相关代码块，而不是反复通读整个文件。
## Reliability Improvements (v1.4.0)

Recent updates focused on real-world recovery and observability:

- Atomic state writes now include fsync + replace and an index lock file (`.codeguard/index.lock`) to reduce interruption/concurrency corruption risk.
- `doctor` command added for metadata consistency checks, snapshot file validation, optional safe repair (`--repair`), and machine-readable output (`--json`).
- Sidecar feature index support added for file types that are not safe for inline comments (for example JSON/YAML/TOML): `<file>.codeguard-index.json`.
- Batch command added for repetitive workflows:
  - `python scripts/codeguard.py batch validate-index <files...>`
  - `python scripts/codeguard.py batch backup <files...>`
  - `python scripts/codeguard.py batch status <files...>`
- Richer file-level observability via `status` and enhanced `list` output.
- Feature-index validation now includes semantic drift hints using per-entry signatures (not only line-range checks).
- Windows console output now prefers UTF-8 to reduce troubleshooting noise from encoding display issues.

## Why CodeGuard Exists

Many AI coding tools still optimize around "compress more context."
CodeGuard is based on a different idea:

For large files, the better move is often not compression. It is precise navigation.

If AI already knows where the relevant feature block starts, it does not need to pull the whole file back into context every time. That is where the feature index matters. It saves tokens, reduces drift, and keeps edits more targeted.

Just as importantly, CodeGuard separates three things that are often mixed together:

- `tested`
- `user-confirmed`
- `important milestone`

Those are not the same state, and CodeGuard treats them differently.

## Core Model

1. Tests are evidence, not truth.
   A change is only considered successful after the user explicitly confirms it.
2. `confirm` records accepted success.
   It updates the accepted current state, writes a permanent success record, and creates an auto snapshot.
   It also updates a header policy note that blocks direct edits without a documented reason.
3. `snapshot` records an important milestone.
   You can still create manual milestones for additional business checkpoints.
4. Large files need feature indexes.
   If a file is over 200 lines, it must have a feature index before editing, backup, confirm, or snapshot.
5. Feature indexes require user authorization when they need to be created or updated.
6. Feature labels stay short.
   The index should improve readability, not turn the file header into documentation sludge.

## 核心规则

1. 测试只是证据，不是真相。
   只有用户明确确认成功，才算真正成功。
2. `confirm` 负责记录“用户确认成功”的结果。
   它会更新当前已接受状态、写入永久成功记录，并自动创建一个快照。
   同时会更新文件头策略注释：禁止直接修改，修改前必须说明原因。
3. `snapshot` 负责记录“重要里程碑版本”。
   你仍然可以手动创建额外里程碑，用于业务节点留档。
4. 大文件必须有功能索引。
   超过 200 行的文件，在编辑、备份、确认或快照之前都必须先有功能索引。
5. 当索引需要新建或更新时，必须先得到用户授权。
6. 功能标签必须简短。
   索引应该提升可读性，而不是把文件头部变成一大片难读说明文。
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

Rules:

- Use `- <feature label> -> line <number>`.
- Point to the start line of the feature block.
- A feature block can span multiple functions.
- Keep labels short and scan-friendly.
- Keep entries sorted by ascending line number.
- Do not use a single unified comment style across languages.
  Use file-specific comment syntax for inline indexes:
  `.py/.sh/.rb/.php` -> `# ...`, `.js/.ts/.go/.rs` -> `// ...`,
  `.c/.cpp/.h/.java/.cs/.css` -> `/* ... */`, `.html/.xaml/.xml` -> `<!-- ... -->`.
  For non-comment-friendly files (for example `.json/.yaml/.toml/.ini/.env/.properties`), use sidecar JSON index files.

## 功能索引格式

对于超过 200 行的文件，CodeGuard 要求在文件顶部附近维护一个功能索引。
这里索引的不是函数名列表，而是“某个单一功能对应的代码块”。

示例：

```python
# [CodeGuard Feature Index]
# - Request parsing -> line 42
# - Snapshot write path -> line 118
# - Rollback validation -> line 203
# [/CodeGuard Feature Index]
```

规则：

- 使用 `- <功能说明> -> line <起始行号>`。
- 行号指向该功能代码块的起始位置。
- 一个功能块可以跨越多个函数。
- 标签要短、要清楚、要方便快速扫读。
- 条目必须按起始行升序排列。
- 不要在所有语言里使用同一种统一注释格式。
  内联索引必须按文件类型使用对应注释：
  `.py/.sh/.rb/.php` 使用 `# ...`，
  `.js/.ts/.go/.rs` 使用 `// ...`，
  `.c/.cpp/.h/.java/.cs/.css` 使用 `/* ... */`，
  `.html/.xaml/.xml` 使用 `<!-- ... -->`。
  对于不适合内联注释的文件（如 `.json/.yaml/.toml/.ini/.env/.properties`），必须使用 sidecar JSON 索引文件。
## Recommended Workflow

1. Use `add` when a completed feature should become protected.
2. If the file is large, inspect the feature index first.
3. If the large-file index is missing or stale, ask for user authorization before updating it.
4. Run `backup` before the approved edit.
5. Make the change by targeting the indexed feature block.
6. Ask the user whether the result actually succeeded.
7. Run `confirm` only after explicit user confirmation.
8. `confirm` will auto-create a snapshot and update a header policy note that requires reasons for future edits.
9. Use `rollback` when a later edit damages a previously protected state.

## 推荐工作流

1. 当某个完成的功能需要保护时，使用 `add`。
2. 如果文件很大，先检查功能索引。
3. 如果大文件缺少索引或索引已经过期，必须先征得用户授权再更新。
4. 在获批修改前，先执行 `backup`。
5. 修改时尽量直接定位到索引对应的功能代码块。
6. 修改完成后，必须问用户这次结果是否真的成功。
7. 只有在用户明确确认后，才执行 `confirm`。
8. `confirm` 会自动创建快照，并在文件头写入“修改需说明原因”的策略注释。
9. 如果后续改乱了，使用 `rollback` 回到之前的重要状态。
## Commands

```bash
# Show the installed version
python scripts/codeguard.py --version

# Initialize project-local state
python scripts/codeguard.py init

# Protect a completed feature and create the initial important snapshot
python scripts/codeguard.py add src/auth.py "User Authentication"

# Create or update a feature index after user approval
python scripts/codeguard.py index src/auth.py --entry "Request parsing:42" --entry "Token refresh:118"

# Show the current feature index
python scripts/codeguard.py show-index src/auth.py

# Validate the index and the over-200-lines rule
python scripts/codeguard.py validate-index src/auth.py

# Create a pre-modification backup
python scripts/codeguard.py backup src/auth.py

# Record a user-confirmed success (auto snapshot is created)
python scripts/codeguard.py confirm src/auth.py "User Authentication" "Fix token refresh bug" true

# Manually mark the current state as an important milestone
python scripts/codeguard.py snapshot src/auth.py "User Authentication" "Stable release candidate"

# Roll back to an important snapshot
python scripts/codeguard.py rollback src/auth.py --version 1

# Show one-file health (marker, accepted state, index, rollback readiness)
python scripts/codeguard.py status src/auth.py
python scripts/codeguard.py status src/auth.py --json  # includes schema metadata

# Diagnose project metadata and snapshot/index consistency
python scripts/codeguard.py doctor

# Apply safe metadata repairs
python scripts/codeguard.py doctor --repair

# Batch operations for multi-file workflows
python scripts/codeguard.py batch validate-index src/a.py src/b.py
python scripts/codeguard.py batch backup src/a.py src/b.py
python scripts/codeguard.py batch status src/a.py src/b.py
python scripts/codeguard.py batch status src/a.py src/b.py --json  # includes schema metadata + per-file results
python scripts/codeguard.py batch status src/a.py src/b.py --fail-fast

# Show stable JSON schema metadata for integrations
python scripts/codeguard.py schema all
python scripts/codeguard.py schema doctor --json-compact
```

## Official Entry Points

There is one official project-local implementation:

- `scripts/codeguard.py`

Compatibility layers:

- `scripts/codeguard-cli.py` is a compatibility wrapper around the same workflow.
- `cli/codeguard_cli.py` is a global launcher that forwards commands to the local project script.

## 官方入口

真正的官方项目内实现只有一个：

- `scripts/codeguard.py`

兼容层说明：

- `scripts/codeguard-cli.py` 是同一套工作流的兼容包装。
- `cli/codeguard_cli.py` 是把全局命令转发到项目内脚本的启动器。
## Project Files

- `.codeguard/index.json`: snapshot history and accepted current state
- `.codeguard/versions/`: important version snapshots
- `.codeguard/temp/`: pre-modification backups
- `.codeguard/records/modifications.md`: success-only permanent records

## 项目内状态目录

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

## 安装到 IDE 技能目录

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
- It is especially useful when Git still feels too heavy for the current user or environment.
- `.codeguard/` and generated backup files should usually stay out of version control.

## 补充说明

- CodeGuard 是本地优先的，不依赖网络。
- 当 Git 对当前用户来说还太重、太复杂时，它尤其有用。
- `.codeguard/` 和自动生成的备份文件通常不应提交到版本控制。

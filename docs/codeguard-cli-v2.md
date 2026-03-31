# CodeGuard CLI v2 设计草案

## 1. 目标
- 日常只记 1-2 个主命令。
- 保留审计链完整。
- 兼容旧命令，渐进迁移。

## 2. 新命令设计

## 2.1 主命令

### `codeguard guard`
用途：执行预校验、备份、编码保护检查、事务登记（pending）。

参数：
- `files...` 必填，可多文件
- `--tier {lite|standard|strict|auto}` 默认 `auto`
- `--feature <name>` 必填
- `--reason <text>` 必填
- `--mode {human|agent}` 默认 `human`
- `--allow-partial` 可选
- `--lock-timeout <seconds>` 默认 `0.8`

输出：
- 成功：`OK tx=<id> state=pending files=<n>`
- 失败：统一错误 JSON

### `codeguard commit`
用途：用户审批后，批量持久化 confirm（confirmed）。

参数：
- `--tx <id>` 必填
- `--approve {true|false}` 必填
- `--refresh-index [files...]` 可选
- `--snapshot-on-confirm` 可选（Strict 默认 true）

输出：
- 成功：`OK tx=<id> state=confirmed`
- 需确认：`PENDING tx=<id>`
- 失败：统一错误 JSON

## 2.2 高级命令
- `codeguard doctor [--repair|--json]`
- `codeguard doctor lock [--json]`
- `codeguard unlock --tx <id> --yes [--force]`
- `codeguard rollback <file> --version <n>`
- `codeguard snapshot <file> "<feature>" "<reason>"`
- `codeguard schema [all|tx|doctor|guard|commit]`

## 3. 旧命令兼容策略

| 旧命令 | v2 映射 | 兼容周期 |
| --- | --- | --- |
| `validate-index <file>` | `guard <file> --phase validate` | 1 个小版本 |
| `backup <file>` | `guard <file> --phase backup` | 1 个小版本 |
| `confirm <file> ...` | `commit --single <file> ...` | 1 个小版本 |
| `snapshot ...` | 保持不变 | 长期 |

兼容行为：
- 旧命令执行时打印一次迁移提示，不中断。
- `--json` 输出新增 `deprecated=true` 字段。

## 4. 返回码规范

| Code | 含义 | 重试 |
| --- | --- | --- |
| `0` | success | - |
| `10` | pending confirmation | 否 |
| `11` | expired transaction | 否 |
| `20` | lock occupied | 是 |
| `21` | lock timeout | 是 |
| `30` | encoding mismatch (auto-rolled back) | 否 |
| `31` | line-ending mismatch (auto-rolled back) | 否 |
| `40` | index invalid/missing | 视场景 |
| `50` | conflict detected | 否 |
| `90` | internal error | 视场景 |

## 5. 批处理事务边界
- 同一 `tx` 内文件必须满足：
  - 相同 tier
  - 相同 feature/reason
  - 预检全部通过
- 默认 all-or-nothing。
- `--allow-partial` 时记录失败列表并要求二次确认。

## 6. 失败回滚策略
- guard 阶段任何一步失败：
  - 立即回滚当前文件到 pre backup
  - 标记事务失败，不写 confirmed 审计记录
- commit 阶段失败：
  - 不写半条 confirmed
  - 可重试最多 3 次
  - 超过阈值后标记 expired

## 7. Agent 模式协议

输入：

```json
{
  "mode": "agent",
  "files": ["src/a.py", "src/b.py"],
  "tier": "auto",
  "feature": "discount-rule",
  "reason": "fix branch"
}
```

输出：

```json
{
  "status": "need_confirm",
  "tx_id": "TX-20260331-001",
  "summary": "2 files guarded under standard tier",
  "next_action": "codeguard commit --tx TX-20260331-001 --approve true"
}
```

## 8. 迁移公告文案（可直接发布）

> CodeGuard 已升级到 v2 命令体系。  
> 日常请优先使用 `codeguard guard` 和 `codeguard commit`。  
> 旧命令仍可在过渡期使用，但会显示迁移提示。  
> 本次升级不会降低审计与回滚能力，并新增异步确认与更稳健的锁诊断。


# CodeGuard v2 现状诊断与改造设计

## 1) 现状诊断：价值-成本矩阵

| 项 | 价值 | 成本 | 结论 |
| --- | --- | --- | --- |
| 可追溯（confirm/snapshot） | 高 | 中 | 必须保留，流程应压缩 |
| 可回滚（backup/rollback） | 高 | 中 | 必须保留，需提升锁可靠性 |
| 掌控感（显式确认） | 中 | 中 | 保留，但改成异步批量确认 |
| 每次都跑全流程 | 中 | 高 | 本末倒置，应改风险分层 |
| 多轮问答确认 | 低 | 高 | 本末倒置，应合并为单确认点 |
| 锁冲突处理靠人工 | 中 | 高 | 本末倒置，应加 doctor/unlock 自动诊断 |
| 全量详细日志 | 中 | 高 | 保留审计，改摘要输出 |

## 2) 三个最关键失衡点（按影响排序）

1. 全局强制重流程导致“小改也重审批”
- 影响：吞吐下降、上下文消耗高、用户绕开工具概率上升。
- 最小修复：上线 Lite/Standard/Strict 三档，默认 Lite，命中风险再自动升档。

2. confirm 阻塞主开发路径
- 影响：编辑后无法连续开发测试，打断流。
- 最小修复：改为异步 `pending -> approved -> confirmed`，允许最后批量 commit。

3. 锁处理缺少工程化“快诊断+快恢复”
- 影响：偶发锁死放大为流程停机。
- 最小修复：`doctor lock` + 有界重试 + 退避 + 超时 + 安全 unlock，失败自动回滚。

## 3) 每个失衡点的最小改动修复方案

### 3.1 分层治理
- 新增统一入口：`codeguard guard`
- `--tier auto` 默认：根据文件路径、diff 行数、关键字自动分层
- 保留原命令兼容，不强制立刻迁移

### 3.2 异步确认
- 新增事务记录 `.codeguard/tx/<tx_id>.json`
- `guard` 阶段只做校验+备份+编辑登记，状态为 `pending`
- `commit --tx <id> --approve true` 才写入永久审计链

### 3.3 锁治理
- 所有写操作统一进入 `with lock_context(...)`
- 重试 3 次，指数退避（200ms, 400ms, 800ms）+ 抖动
- 超时后输出可执行命令：`codeguard doctor lock` / `codeguard unlock --tx <id> --yes`

## 4) 不建议做的反模式
- 反模式 1：任何改动都走 Strict。
- 反模式 2：用超长人工确认文案代替结构化状态。
- 反模式 3：锁冲突后直接 `--force` 清锁不检查占用者。
- 反模式 4：为省 token 删除审计字段（会破坏追溯链）。
- 反模式 5：编辑器/脚本默认转换编码再“事后补救”。

## 5) 文件锁死（Windows）工程方案

### 5.1 可能根因清单
- 句柄未释放（异常路径没 close）
- 并发写入（多进程/多 agent 同时写 index）
- 编辑器占用（保存时短暂独占）
- 杀毒/索引器占用（实时扫描）
- 网络盘/同步盘延迟导致锁状态漂移

### 5.2 命令级防护
- 重试：最多 3 次
- 退避：指数退避 + 随机抖动
- 超时：单次锁等待 <= 1.2s，超时直接失败并给下一步命令
- 失败回滚：若写入链任一步失败，自动恢复 `pre-modification` 备份

### 5.3 Python 实现建议
- 文件操作必须 `with open(...)`，确保句柄释放
- 写入后 `flush()` + `os.fsync()`
- 用 `tempfile` + `os.replace()` 做原子替换
- 异常分类：
  - `LockTimeoutError`
  - `EncodingMismatchError`
  - `AtomicWriteError`
  - `ConflictError`

### 5.4 doctor/unlock 子命令设计

伪代码：

```python
def doctor_lock(project):
    st = inspect_lock(project)
    if st.occupied:
        return E_LOCK_OCCUPIED, "Lock held by active process"
    if st.stale:
        return E_LOCK_STALE, "Stale lock can be cleaned"
    return E_OK, "No lock risk"

def unlock(project, tx_id=None, force=False):
    st = inspect_lock(project)
    if st.occupied and not force:
        return E_LOCK_OCCUPIED, "Use --force only with explicit approval"
    backup_index(project)
    remove_lock_file(project)
    verify_lock_removed(project)
    return E_OK, "Unlocked"
```

错误码建议：
- `E000` success
- `E101` lock occupied
- `E102` stale lock
- `E103` lock timeout
- `E201` encoding mismatch
- `E202` line-ending mismatch
- `E301` tx conflict
- `E302` tx expired
- `E901` unknown internal error

## 6) 降低 Token 开销（30%-50%）

### 6.1 可本地缓存
- 文件静态信息：`line_count`, `encoding`, `bom`, `line_ending`
- 最近一次有效 index 校验摘要
- 同一事务内的 `feature/reason/tier`

### 6.2 可合并步骤
- `validate + backup` 合并进 `guard`
- `approve + confirm` 合并进 `commit --approve true`
- 批处理多个文件共享一次上下文头

### 6.3 日志改摘要
- 默认只返回：状态、tx_id、文件数、失败文件、下一步
- 详细日志写本地 JSON，不在每轮对话展开

### 6.4 短响应模板
- 成功：
  - `OK tx={tx_id} files={n} tier={tier} next=continue_dev`
- 失败：
  - `FAIL code={error_code} reason={message} hint={hint}`
- 需确认：
  - `PENDING tx={tx_id} files={n} action=run: codeguard commit --tx {tx_id} --approve true`

## 7) 异步 confirm 机制

状态机：
- `pending` -> `approved` -> `confirmed`
- `pending` -> `expired`
- `approved` -> `pending`（发生冲突需重新审批）

最小数据结构：

```json
{
  "tx_id": "TX-20260331-001",
  "files": ["src/a.py", "src/b.py"],
  "tier": "standard",
  "feature": "price-rule",
  "reason": "fix discount branch",
  "state": "pending",
  "pre_hash_map": {},
  "post_hash_map": {},
  "created_at": "2026-03-31T10:00:00+08:00",
  "expires_at": "2026-04-01T10:00:00+08:00"
}
```

用户提示语模板：
- `已进入待确认：tx={tx_id}，你可以继续开发；完成后执行 commit 批量确认。`
- `事务已过期：tx={tx_id}，请重新 guard 或执行 rollback。`

失败补救：
- 优先重试 confirm
- 失败后回滚受影响文件
- 标记事务 `expired` 并保留失败原因

## 8) Encoding Guard 优化

### 8.1 检测策略
- 先读原始二进制头判断 BOM
- 再按 UTF-8/UTF-16/GBK 顺序探测可解码性
- 行尾统计 CRLF/LF 比例并记录 dominant

### 8.2 常见踩坑
- 编辑器自动 UTF-8 化
- Git `autocrlf` 偷改行尾
- Python `open(..., encoding='utf-8')` 覆盖原编码

### 8.3 自动校验与回滚
- edit 前：写入 `.codeguard/tx/<id>.meta.json`
- edit 后：重算编码/BOM/行尾
- mismatch：立刻回滚 temp 备份并返回 `E201/E202`

### 8.4 白名单机制（误报控制）
- 允许显式白名单路径在严格审计下变更编码：
  - `docs/generated/**`
  - `*.min.js`
- 白名单变更必须附带 `--allow-encoding-change --reason "..."`

## 9) 风险驱动政策草案（替代全局强制）

政策正文：
- 默认 Lite。
- 核心模块和高风险改动自动 Strict。
- 小改动不应被重流程阻塞。
- 人工可一票升级，且必须记录原因。

示例：
1. 修文案（README typo） -> Lite
2. 改业务逻辑（订单折扣分支） -> Standard
3. 重构核心模块（结算引擎） -> Strict

## 10) 高频错误文案（示例 10 条）

1. `E101`：文件被占用。关闭占用进程后重试，先执行 `codeguard doctor lock`。  
2. `E102`：发现陈旧锁。可执行 `codeguard unlock --yes` 清理。  
3. `E103`：锁等待超时。稍后重试，或排查并发写入。  
4. `E201`：编码发生变化，已自动回滚。请关闭编辑器自动转码。  
5. `E202`：行尾风格变化，已自动回滚。请固定 CRLF/LF。  
6. `E301`：确认冲突，文件已变化。请重新审批或重新 guard。  
7. `E302`：事务过期。请重新创建事务。  
8. `E401`：索引缺失且文件超过阈值。请先补索引或降范围修改。  
9. `E501`：备份失败。检查磁盘空间和权限后重试。  
10. `E901`：内部错误。保留 tx_id 并执行 `codeguard doctor --json`。

统一格式：

```json
{
  "error_code": "E201",
  "message": "Encoding changed unexpectedly",
  "hint": "Disable editor auto-encoding conversion and retry",
  "retryable": false
}
```

最短排障手册：
1. 先看 `error_code`。
2. 如果是锁问题，运行 `codeguard doctor lock`。
3. 如果是编码问题，检查编辑器编码与行尾设置。
4. 如果是事务冲突，重新 guard 并重新审批。


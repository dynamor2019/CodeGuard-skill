# CodeGuard 迁移指南（v1 -> v2）

## 1. 迁移目标
- 将“全局强制重流程”改为“风险驱动分层”。
- 将“同步 confirm 阻塞”改为“异步批量确认”。
- 保持审计链和回滚能力不下降。

## 2. 命令映射

| v1 | v2 |
| --- | --- |
| `validate-index <file>` | `guard <file> --phase validate` |
| `backup <file>` | `guard <file> --phase backup` |
| `confirm <file> "<feature>" "<reason>" true` | `commit --single <file> --feature "<feature>" --reason "<reason>" --approve true` |
| `snapshot <file> ...` | `snapshot <file> ...` |
| `lock-status` | `doctor lock` |

## 3. 推荐迁移步骤（两周）

1. 第 1-3 天：启用兼容模式
- 保留旧命令可用。
- 所有新任务优先使用 `guard/commit`。

2. 第 4-10 天：默认 `--tier auto`
- 记录自动升档命中率。
- 关注锁冲突与编码回滚告警。

3. 第 11-14 天：收敛策略
- 高频低风险任务固定 Lite。
- 核心模块固定 Strict。
- 关闭团队内不再使用的旧命令快捷脚本。

## 4. 配置示例

```yaml
codeguard:
  default_tier: auto
  pending_ttl_hours: 24
  lock_timeout_seconds: 0.8
  retry:
    attempts: 3
    backoff_ms: [200, 400, 800]
  encoding_guard: strict
  core_paths:
    - src/core/**
    - src/security/**
    - scripts/codeguard.py
```

## 5. 风险与回退
- 如果 v2 在高峰期阻塞率上升：
  - 暂时将默认层级降为 Lite
  - 严格模式仅限核心目录
- 如果出现审计缺口：
  - 立即恢复强制 `commit --approve true`
  - 禁止 `--allow-partial`

## 6. 常见迁移问题

1. 问：是否必须一次性改造全部脚本？  
答：不需要。兼容层支持渐进替换，优先改 CI 和模板命令。

2. 问：异步确认会不会降低安全？  
答：不会。`pending` 不是成功态，只有 `confirmed` 才写入永久审计。

3. 问：为什么还保留 snapshot？  
答：用于业务里程碑，不和每次确认绑定，减少日常摩擦。

## 7. 开发者公告（短版）

> 从今天起，CodeGuard 默认采用风险驱动。  
> 小改动走 Lite，大改动自动升档。  
> 先开发再批量确认，不再每次编辑都被 confirm 阻塞。  
> 审计和回滚机制保持不变。


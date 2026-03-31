# Global Agent Rules (CodeGuard v2 Draft)

## 0. Policy
- Default policy is risk-driven governance, not global heavy governance.
- Use the lightest level that can still keep full audit traceability.
- Human can escalate any task to a stricter level at any time.

## 1. Risk-Driven Governance

### 1.1 Governance Tiers

| Tier | Trigger Conditions (Scope/Risk/File Type) | Required Commands | Skippable Steps | Typical Cases |
| --- | --- | --- | --- | --- |
| Lite | Small change (`<=30` lines), low-risk, non-core files (docs/config copy/UI text) | `codeguard guard <file> --tier lite` | Manual `snapshot`; interactive multi-round confirm | Fix copy text, log wording, comments |
| Standard | Medium change (`31-200` lines) or normal business logic in non-core modules | `codeguard guard <file> --tier standard` | Manual lock troubleshooting if guard succeeds; separate `validate-index` and `backup` | Add branch logic, API param adjustment |
| Strict | Core module/security/payment/auth/data pipeline; or large change (`>200` lines) | `codeguard guard <file> --tier strict` + `codeguard snapshot <file> ...` on milestone | None except user-explicit bypass | Core refactor, transaction rules, auth flow |

### 1.2 Auto Escalation Rule
- If any condition is hit, auto-upgrade from Lite to Standard or Strict:
  - touches core path (`src/core/**`, `src/security/**`, `src/payment/**`, `scripts/codeguard.py`)
  - diff lines `>30`
  - file contains high-risk keywords (`auth`, `permission`, `crypto`, `rollback`, `migration`)
  - lock conflict retries exceed threshold (`>=3`)
  - encoding guard reports mismatch once

### 1.3 One-Vote Escalation
- Any reviewer/user can issue: `codeguard guard <file> --tier strict --reason "<why>"`.
- Escalation reason must be written into audit metadata.

## 2. Command Set (Reduced Cognitive Load)

### 2.1 Main Commands
- Daily flow (remember 1 command): `codeguard guard <files...> [--tier lite|standard|strict]`
- Post-dev async batch confirm: `codeguard commit --tx <tx_id> --approve true`

### 2.2 Advanced Commands (On Demand)
- Health check: `codeguard doctor [--repair]`
- Lock diagnosis/recovery: `codeguard doctor lock [--json]`, `codeguard unlock --tx <tx_id> --yes`
- Rollback: `codeguard rollback <file> --version <n>`
- Milestone snapshot: `codeguard snapshot <file> "<feature>" "<reason>"`

### 2.3 Legacy Compatibility
- Keep old commands as aliases for one minor version:
  - `validate-index` -> `guard --phase validate`
  - `backup` -> `guard --phase backup`
  - `confirm` -> `commit --single`
  - `snapshot` unchanged

## 3. Encoding Guard (Mandatory)
- Detect and record `encoding`, `bom`, `line_ending` before edit.
- Preserve all three during write; no implicit conversion.
- Re-verify after write. If mismatch exists:
  - auto rollback current file from temp backup
  - return non-zero with clear error code
  - mark operation as `failed_not_confirmed`

Detection baseline:
- UTF-8 BOM: first bytes `EF BB BF`
- UTF-16 LE/BE BOM: `FF FE` / `FE FF`
- UTF-32 BOM: `FF FE 00 00` / `00 00 FE FF`
- GBK heuristic: UTF-8 decode fails and GBK decode succeeds with low replacement ratio
- Line endings:
  - CRLF count (`\r\n`)
  - LF-only count (`(?<!\r)\n`)
  - preserve dominant style

## 4. Async Confirm (Non-Blocking)

### 4.1 States
- `pending`: guarded and edited, waiting explicit approval
- `approved`: user approved, waiting persistence
- `confirmed`: persisted to audit chain
- `expired`: exceeded timeout and locked from direct confirm

### 4.2 Minimal Record Fields
- `tx_id`, `file`, `pre_hash`, `post_hash`
- `tier`, `feature`, `reason`
- `state`, `created_at`, `expires_at`
- `operator`, `approved_by`, `confirmed_at`

### 4.3 Timeout and Conflict
- default pending timeout: `24h` (configurable)
- conflict if file hash changed after approval but before confirm:
  - block confirm
  - require re-approve or rollback

### 4.4 Recovery Path
- if confirm fails:
  - `doctor lock` -> release stale lock if safe
  - verify file hash against `post_hash`
  - retry confirm up to 3 times with backoff
  - if still fails, rollback to `pre_hash` snapshot and mark `expired`

## 5. AI Agent Friendly Mode

### 5.1 Protocol
- Input:
  - `mode=agent`
  - `files=[...]`
  - `tier=lite|standard|strict|auto`
  - `intent`, `feature`, `reason`
- Output (short JSON):
  - `status=ok|need_confirm|failed`
  - `tx_id`
  - `summary`
  - `next_action`

### 5.2 Batch Transaction Boundary
- One transaction can include multiple files only if:
  - same feature and risk tier
  - all pre-checks pass
- Partial failure policy:
  - default all-or-nothing rollback
  - optional `--allow-partial` records failed files explicitly

### 5.3 Minimal Confirmation Point
- Only 1 human confirmation required per transaction:
  - `approve tx` then batch `commit`
- Keep full per-file audit rows under same `tx_id`.

## 6. Error UX (10-Second Understandability)
- Unified error shape:
  - `error_code`
  - `message`
  - `hint`
  - `retryable` (`true/false`)
- Message must answer:
  - what happened
  - why likely happened
  - what to do next (one command)

## 7. Examples

### 7.1 Fix Copy Text (Lite)
`codeguard guard docs/README.md --tier lite --feature "copy-fix" --reason "typo"`

### 7.2 Business Logic Change (Standard)
`codeguard guard src/orders/service.py --tier standard --feature "price-rule" --reason "discount condition"`

### 7.3 Core Refactor (Strict)
`codeguard guard src/core/engine.py --tier strict --feature "engine-refactor" --reason "module split"`


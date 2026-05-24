# Global Agent Rules (CodeGuard v2)

## 0. Policy
- Default policy is risk-driven governance, not global heavy governance.
- Use the lightest level that can still keep full audit traceability.
- Human can escalate any task to a stricter level at any time.
- Hash drift during active development should create an unconfirmed development baseline, not block the task.

## 1. Risk-Driven Governance

### 1.1 Governance Tiers (Implemented)

| Tier | Trigger Conditions | Command | Effect |
| --- | --- | --- | --- |
| Lite | Small change (<=30 lines), low-risk, non-core files | `guard <file> --tier lite` | Backup + encoding detection |
| Standard | Medium change or normal business logic | `guard <file> --tier standard` | Backup + encoding detection + baseline tracking |
| Strict | Core module/security/auth; large change (>200 lines) | `guard <file> --tier strict` | Backup + encoding detection + milestone snapshot |

### 1.2 Auto Escalation Rules (Guidance)
- Consider upgrading to strict when:
  - Touching core paths (`src/core/**`, `src/security/**`, `src/payment/**`, `scripts/codeguard.py`)
  - Diff lines > 200
  - File contains high-risk keywords (`auth`, `permission`, `crypto`, `rollback`, `migration`)
  - Lock conflict retries exceed threshold (>=3)

### 1.3 One-Vote Escalation
- Any reviewer/user can escalate: `guard <file> --tier strict --reason "<why>"`.
- Escalation reason is recorded in backup metadata.

## 2. Command Set (Implemented)

### 2.1 Daily Commands
- Pre-edit guard: `codeguard guard <file> [--tier lite|standard|strict] [--feature "..."] [--reason "..."]`
- Confirm milestone: `codeguard confirm <file> "<feature>" "<reason>" true`
- Milestone snapshot: `codeguard snapshot <file> "<feature>" "<reason>"`

### 2.2 Recovery Commands
- Health check: `codeguard doctor [--repair]`
- File status: `codeguard status <file> [--json]`
- Lock diagnosis: `codeguard lock-status [--json]`
- Stale lock cleanup: `codeguard unlock --yes`
- Rollback: `codeguard rollback <file> --version <n>`
- Development baseline sync: `codeguard sync-current <file> --feature "pre_<task>" --reason "<why>"`

### 2.3 Feature Index Commands
- Auto-generate: `codeguard index <file> --auto`
- Show: `codeguard show-index <file>`
- Validate: `codeguard validate-index <file>`
- Batch: `codeguard batch [validate-index|backup|status|index] <files...> [--auto]`

### 2.4 Token Efficiency Commands
- Compress prose files: `codeguard compress <file> [--level lite|full|ultra] [--in-place]`
- Token diagnostics: `codeguard token-tips [--json]`

## 3. Encoding Guard (Implemented)

The `guard` command automatically detects and records before edit:
- Encoding (UTF-8, UTF-8 BOM, UTF-16 LE/BE, UTF-32, GBK)
- BOM presence
- Line ending style (LF vs CRLF)

Encoding metadata is stored as `<backup>.encoding.json` alongside the backup. On rollback, the backup is restored byte-for-byte via `shutil.copy2`, which preserves the original encoding. The `compress --in-place` command uses `write_text_preserving` to maintain encoding on modified files.

Detection baseline:
- UTF-8 BOM: first bytes `EF BB BF`
- UTF-16 LE/BE BOM: `FF FE` / `FE FF`
- UTF-32 BOM: `FF FE 00 00` / `00 00 FE FF`
- GBK heuristic: UTF-8 decode fails and GBK decode succeeds
- Line endings: CRLF vs LF-only count, dominant style preserved

Note: Post-edit encoding re-verification with auto-rollback is planned but not yet implemented.

## 4. Token Compression (Implemented)

CodeGuard includes Caveman-style token compression via the `compress` command and `token-tips` diagnostics. **Compress only works on prose files** (.md, .txt, .rst, .adoc) — code files are rejected to prevent syntax corruption. Three compression levels:
- **lite**: Drop filler at edges, keep articles and full sentences
- **full**: Drop articles, filler, hedging. Fragments OK. Short synonyms.
- **ultra**: Full + drop be-verbs, arrows for causality, aggressive abbreviation

Compression preserves: fenced code blocks, inline code, technical terms, error messages, security warnings. In-place compression uses the guard backup pipeline (encoding metadata saved alongside backup).

## 5. Planned Features (Not Yet Implemented)

### 5.1 Async Confirm (Planned)
- States: `pending`, `approved`, `confirmed`, `expired`
- Pending timeout: 24h (configurable)
- Conflict detection: block confirm if hash changed after approval
- Recovery: verify hash, retry up to 3 times, rollback to pre_hash if needed

### 5.2 AI Agent Friendly Mode (Planned)
- Input protocol: `mode=agent`, `files=[...]`, `tier=auto|lite|standard|strict`, `intent`, `feature`, `reason`
- Output: short JSON with `status`, `tx_id`, `summary`, `next_action`
- Batch transaction boundary: same feature + tier, all-or-nothing rollback, optional `--allow-partial`
- Single human confirmation per transaction

### 5.3 Unified Error Shape (Planned)
- `error_code`, `message`, `hint`, `retryable` (true/false)
- Message answers: what happened, why, what to do next (one command)

## 6. Error UX (Design Guideline)

Error output SHOULD answer three questions. Current implementation is partially compliant:
- What happened (most commands)
- Why it likely happened (lock timeouts, conflicts, doctor reports)
- What to do next (lock-status suggestions, doctor hints)

Full `{error_code, message, hint, retryable}` shaping is planned (see section 5.3).

## 7. Examples

### 7.1 Fix Typo in Docs (Lite)
```
python scripts/codeguard.py guard docs/README.md --tier lite --feature "typo-fix" --reason "fix spelling"
# edit file
```

### 7.2 Business Logic Change (Standard)
```
python scripts/codeguard.py guard src/orders/service.py --tier standard --feature "price-rule" --reason "update discount condition"
# edit file
# optionally confirm if important milestone:
python scripts/codeguard.py confirm src/orders/service.py "price-rule" "update discount condition" true
```

### 7.3 Core Security Refactor (Strict)
```
python scripts/codeguard.py guard src/core/auth.py --tier strict --feature "auth-refactor" --reason "token validation rewrite"
# edit file
python scripts/codeguard.py confirm src/core/auth.py "auth-refactor" "token validation rewrite" true
```

### 7.4 Compress Verbose Docs
```
# Preview compression
python scripts/codeguard.py compress CLAUDE.md --level full
# Apply compression (creates guard-style backup)
python scripts/codeguard.py compress CLAUDE.md --level full --in-place
```

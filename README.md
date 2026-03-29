// Policy: Do not modify directly. Explain reason before edits. Last confirm reason: Document refresh-index and status index_summary

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

## 涓枃璇存槑

CodeGuard 鏄竴涓潰鍚?vibe coding 鍒濆鑰呯殑鏈湴鐗堟湰淇濇姢涓庡姛鑳界储寮曞伐鍏枫€?
瀹冧笉鏄?Git 鐨勬浛浠ｅ搧锛岃€屾槸涓€灞傛洿杞婚噺銆佹洿閫傚悎 AI 鍗忎綔缂栫▼鐨勬湰鍦板伐浣滄祦锛氬厛淇濇姢宸茬粡楠岃瘉鎴愬姛鐨勬垚鏋滐紝鍐嶈 AI 鍦ㄦ竻鏅拌竟鐣屽唴缁х画淇敼浠ｇ爜銆?

瀹冩兂瑙ｅ喅鐨勬槸涓€涓潪甯哥幇瀹炵殑闂锛?

- AI 鏀逛唬鐮佸緢蹇紝浣嗕篃寰堝鏄撴妸宸茬粡鑳藉伐浣滅殑閮ㄥ垎涓€璧锋敼涔便€?
- Git 寰堝己澶э紝浣嗗寰堝鍒濆鑰呮潵璇达紝渚濈劧鏈夊涔犻棬妲涖€佹搷浣滈棬妲涳紝鐢氳嚦杩樻湁缃戠粶鍜屽悓姝ュ眰闈㈢殑鐜板疄闄愬埗銆?
- 澶ф枃浠剁壒鍒氮璐逛笂涓嬫枃锛孉I 寰€寰€涓嶆槸璇诲お澶氾紝灏辨槸鎶婃湁鐢ㄥ拰娌＄敤鐨勪俊鎭竴璧峰帇缂┿€?

CodeGuard 鐨勫仛娉曟洿鐩存帴锛?

- 鍙湁鐢ㄦ埛鏄庣‘纭鈥滆繖娆＄湡鐨勬垚鍔熶簡鈥濓紝鎵嶆妸缁撴灉璁板綍涓烘垚鍔熴€?
- 鍙湁鐢ㄦ埛鏄庣‘璇粹€滆繖涓増鏈緢閲嶈鈥濓紝鎵嶅垱寤哄揩鐓с€?
- 瀵硅秴杩?200 琛岀殑澶ф枃浠讹紝寮哄埗寤虹珛绠€鐭殑鍔熻兘绱㈠紩锛岃 AI 鍙互鐩存帴瀹氫綅鐩稿叧浠ｇ爜鍧楋紝鑰屼笉鏄弽澶嶉€氳鏁翠釜鏂囦欢銆?
## Reliability Improvements (v1.4.0)

Recent updates focused on real-world recovery and observability:

- Atomic state writes now include fsync + replace and an index lock file (`.codeguard/index.lock`) to reduce interruption/concurrency corruption risk.
- Lock behavior is now low-interruption by default: fast fail on contention (default `--lock-timeout 0.8`) with human-readable next steps instead of long blocking.
- New lock diagnostics and lightweight recovery controls:
  - `python scripts/codeguard.py lock-status` (`--json` supported)
  - `python scripts/codeguard.py unlock --yes` (stale lock cleanup)
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
   It updates the accepted current state, writes a permanent success record.
   It also updates a header policy note that blocks direct edits without a documented reason.
3. `snapshot` records an important milestone.
   You can still create manual milestones for additional business checkpoints.
4. CodeGuard retention is latest-only.
   For each file, only the latest confirmed/snapshot state is retained in CodeGuard storage.
   `modifications.md` also keeps only the latest confirmed record.
5. Large files need feature indexes.
   If a file is over 200 lines, it must have a feature index before editing, backup, confirm, or snapshot.
5. Feature indexes require user authorization when they need to be created or updated.
6. Feature labels stay short.
   The index should improve readability, not turn the file header into documentation sludge.

## 鏍稿績瑙勫垯

1. 娴嬭瘯鍙槸璇佹嵁锛屼笉鏄湡鐩搞€?   鍙湁鐢ㄦ埛鏄庣‘纭鎴愬姛锛屾墠绠楃湡姝ｆ垚鍔熴€?2. `confirm` 璐熻矗璁板綍鈥滅敤鎴风‘璁ゆ垚鍔熲€濈殑缁撴灉銆?   瀹冧細鏇存柊褰撳墠宸叉帴鍙楃姸鎬併€佸啓鍏ユ案涔呮垚鍔熻褰曪紝骞惰嚜鍔ㄥ垱寤轰竴涓揩鐓с€?   鍚屾椂浼氭洿鏂版枃浠跺ご绛栫暐娉ㄩ噴锛氱姝㈢洿鎺ヤ慨鏀癸紝淇敼鍓嶅繀椤昏鏄庡師鍥犮€?3. `snapshot` 璐熻矗璁板綍鈥滈噸瑕侀噷绋嬬鐗堟湰鈥濄€?   浣犱粛鐒跺彲浠ユ墜鍔ㄥ垱寤洪澶栭噷绋嬬锛岀敤浜庝笟鍔¤妭鐐圭暀妗ｃ€?4. 澶ф枃浠跺繀椤绘湁鍔熻兘绱㈠紩銆?
   瓒呰繃 200 琛岀殑鏂囦欢锛屽湪缂栬緫銆佸浠姐€佺‘璁ゆ垨蹇収涔嬪墠閮藉繀椤诲厛鏈夊姛鑳界储寮曘€?
5. 褰撶储寮曢渶瑕佹柊寤烘垨鏇存柊鏃讹紝蹇呴』鍏堝緱鍒扮敤鎴锋巿鏉冦€?
6. 鍔熻兘鏍囩蹇呴』绠€鐭€?
   绱㈠紩搴旇鎻愬崌鍙鎬э紝鑰屼笉鏄妸鏂囦欢澶撮儴鍙樻垚涓€澶х墖闅捐璇存槑鏂囥€?
7. 当前中文段若与英文规则冲突，以英文规则为准：
   `confirm` 仅记录用户确认成功；`snapshot` 仅在用户明确标记重要里程碑时使用。
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
  `.c/.cpp/.h/.java/.cs/.css` -> `/* ... */`, `.html/.xaml/.xml/.csproj` -> `<!-- ... -->`.
  For non-comment-friendly files (for example `.json/.yaml/.toml/.ini/.env/.properties`), use sidecar JSON index files.

## 鍔熻兘绱㈠紩鏍煎紡

瀵逛簬瓒呰繃 200 琛岀殑鏂囦欢锛孋odeGuard 瑕佹眰鍦ㄦ枃浠堕《閮ㄩ檮杩戠淮鎶や竴涓姛鑳界储寮曘€?
杩欓噷绱㈠紩鐨勪笉鏄嚱鏁板悕鍒楄〃锛岃€屾槸鈥滄煇涓崟涓€鍔熻兘瀵瑰簲鐨勪唬鐮佸潡鈥濄€?

绀轰緥锛?

```python
# [CodeGuard Feature Index]
# - Request parsing -> line 42
# - Snapshot write path -> line 118
# - Rollback validation -> line 203
# [/CodeGuard Feature Index]
```

瑙勫垯锛?
- 浣跨敤 `- <鍔熻兘璇存槑> -> line <璧峰琛屽彿>`銆?- 琛屽彿鎸囧悜璇ュ姛鑳戒唬鐮佸潡鐨勮捣濮嬩綅缃€?- 涓€涓姛鑳藉潡鍙互璺ㄨ秺澶氫釜鍑芥暟銆?- 鏍囩瑕佺煭銆佽娓呮銆佽鏂逛究蹇€熸壂璇汇€?- 鏉＄洰蹇呴』鎸夎捣濮嬭鍗囧簭鎺掑垪銆?- 涓嶈鍦ㄦ墍鏈夎瑷€閲屼娇鐢ㄥ悓涓€绉嶇粺涓€娉ㄩ噴鏍煎紡銆?  鍐呰仈绱㈠紩蹇呴』鎸夋枃浠剁被鍨嬩娇鐢ㄥ搴旀敞閲婏細
  `.py/.sh/.rb/.php` 浣跨敤 `# ...`锛?  `.js/.ts/.go/.rs` 浣跨敤 `// ...`锛?  `.c/.cpp/.h/.java/.cs/.css` 浣跨敤 `/* ... */`锛?  `.html/.xaml/.xml/.csproj` 浣跨敤 `<!-- ... -->`銆?  瀵逛簬涓嶉€傚悎鍐呰仈娉ㄩ噴鐨勬枃浠讹紙濡?`.json/.yaml/.toml/.ini/.env/.properties`锛夛紝蹇呴』浣跨敤 sidecar JSON 绱㈠紩鏂囦欢銆?## Recommended Workflow

1. Use `add` when a completed feature should become protected.
2. If the file is large, inspect the feature index first.
3. If the large-file index is missing or stale, ask for user authorization before updating it.
4. Run `backup` before the approved edit.
5. Make the change by targeting the indexed feature block.
6. Ask the user whether the result actually succeeded.
7. Run `confirm` only after explicit user confirmation.
8. `confirm` records a user-confirmed success only; use `snapshot` only when the user marks a milestone as important.
9. Use `rollback` when a later edit damages a previously protected state.

## 鎺ㄨ崘宸ヤ綔娴?

1. 褰撴煇涓畬鎴愮殑鍔熻兘闇€瑕佷繚鎶ゆ椂锛屼娇鐢?`add`銆?
2. 濡傛灉鏂囦欢寰堝ぇ锛屽厛妫€鏌ュ姛鑳界储寮曘€?
3. 濡傛灉澶ф枃浠剁己灏戠储寮曟垨绱㈠紩宸茬粡杩囨湡锛屽繀椤诲厛寰佸緱鐢ㄦ埛鎺堟潈鍐嶆洿鏂般€?
4. 鍦ㄨ幏鎵逛慨鏀瑰墠锛屽厛鎵ц `backup`銆?
5. 淇敼鏃跺敖閲忕洿鎺ュ畾浣嶅埌绱㈠紩瀵瑰簲鐨勫姛鑳戒唬鐮佸潡銆?
6. 淇敼瀹屾垚鍚庯紝蹇呴』闂敤鎴疯繖娆＄粨鏋滄槸鍚︾湡鐨勬垚鍔熴€?7. 鍙湁鍦ㄧ敤鎴锋槑纭‘璁ゅ悗锛屾墠鎵ц `confirm`銆?8. `confirm` 浼氳嚜鍔ㄥ垱寤哄揩鐓э紝骞跺湪鏂囦欢澶村啓鍏モ€滀慨鏀归渶璇存槑鍘熷洜鈥濈殑绛栫暐娉ㄩ噴銆?9. 濡傛灉鍚庣画鏀逛贡浜嗭紝浣跨敤 `rollback` 鍥炲埌涔嬪墠鐨勯噸瑕佺姸鎬併€?## Commands

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
python scripts/codeguard.py validate-index src/auth.py --lock-timeout 1.2

# Create a pre-modification backup
python scripts/codeguard.py backup src/auth.py
python scripts/codeguard.py backup src/auth.py --lock-timeout 0.8

# Record a user-confirmed success
python scripts/codeguard.py confirm src/auth.py "User Authentication" "Fix token refresh bug" true

# Record success and refresh indexes in one step (defaults to current file if no FILE is passed)
python scripts/codeguard.py confirm src/auth.py "User Authentication" "Fix token refresh bug" true --refresh-index src/auth.py src/store.py

# Manually mark the current state as an important milestone
python scripts/codeguard.py snapshot src/auth.py "User Authentication" "Stable release candidate"

# Roll back to the latest retained important snapshot
python scripts/codeguard.py rollback src/auth.py --version 1

# Show one-file health (marker, accepted state, index, rollback readiness)
python scripts/codeguard.py status src/auth.py
python scripts/codeguard.py status src/auth.py --json  # includes schema metadata + index_summary(required/missing/stale)

# Diagnose project metadata and snapshot/index consistency
python scripts/codeguard.py doctor

# Apply safe metadata repairs
python scripts/codeguard.py doctor --repair

# Batch operations for multi-file workflows
python scripts/codeguard.py batch validate-index src/a.py src/b.py
python scripts/codeguard.py batch backup src/a.py src/b.py
python scripts/codeguard.py batch status src/a.py src/b.py
python scripts/codeguard.py batch index src/a.py src/b.py --auto
python scripts/codeguard.py batch status src/a.py src/b.py --json  # includes schema metadata + per-file results
python scripts/codeguard.py batch status src/a.py src/b.py --fail-fast

# Lock diagnostics and controlled unlock
python scripts/codeguard.py lock-status
python scripts/codeguard.py lock-status --json --json-compact
python scripts/codeguard.py unlock --yes

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

## 瀹樻柟鍏ュ彛

鐪熸鐨勫畼鏂归」鐩唴瀹炵幇鍙湁涓€涓細

- `scripts/codeguard.py`

鍏煎灞傝鏄庯細

- `scripts/codeguard-cli.py` 鏄悓涓€濂楀伐浣滄祦鐨勫吋瀹瑰寘瑁呫€?
- `cli/codeguard_cli.py` 鏄妸鍏ㄥ眬鍛戒护杞彂鍒伴」鐩唴鑴氭湰鐨勫惎鍔ㄥ櫒銆?
## Project Files

- `.codeguard/index.json`: snapshot history and accepted current state
- `.codeguard/versions/`: important version snapshots
- `.codeguard/temp/`: pre-modification backups
- `.codeguard/records/modifications.md`: success-only permanent records

## 椤圭洰鍐呯姸鎬佺洰褰?

- `.codeguard/index.json`锛氬揩鐓у巻鍙插拰褰撳墠宸叉帴鍙楃姸鎬?
- `.codeguard/versions/`锛氶噸瑕佺増鏈揩鐓?
- `.codeguard/temp/`锛氫慨鏀瑰墠澶囦唤
- `.codeguard/records/modifications.md`锛氬彧璁板綍鎴愬姛缁撴灉鐨勬案涔呰褰?
## Install Into An IDE

```bash
# Auto-detect supported IDE skill folders
python scripts/install_bundle.py

# Install into a specific skills directory
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry

# Also install the global launcher
python scripts/install_bundle.py --install-cli
```

## 瀹夎鍒?IDE 鎶€鑳界洰褰?

```bash
# 鑷姩妫€娴嬫敮鎸佺殑 IDE 鎶€鑳界洰褰?
python scripts/install_bundle.py

# 瀹夎鍒版寚瀹氭妧鑳界洰褰?
python scripts/install_bundle.py --target "%USERPROFILE%\\.trae\\skills" --trae-registry

# 鍚屾椂瀹夎鍏ㄥ眬鍚姩鍣?
python scripts/install_bundle.py --install-cli
```

## Notes

- CodeGuard is local-first and works without network access.
- It is especially useful when Git still feels too heavy for the current user or environment.
- `.codeguard/` and generated backup files should usually stay out of version control.

## 琛ュ厖璇存槑

- CodeGuard 鏄湰鍦颁紭鍏堢殑锛屼笉渚濊禆缃戠粶銆?
- 褰?Git 瀵瑰綋鍓嶇敤鎴锋潵璇磋繕澶噸銆佸お澶嶆潅鏃讹紝瀹冨挨鍏舵湁鐢ㄣ€?
- `.codeguard/` 鍜岃嚜鍔ㄧ敓鎴愮殑澶囦唤鏂囦欢閫氬父涓嶅簲鎻愪氦鍒扮増鏈帶鍒躲€?

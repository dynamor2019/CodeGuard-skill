# CodeGuard Global Launcher

This folder contains the global `codeguard` launcher.
It is not a second implementation. Its job is to forward project commands to the local official script at `scripts/codeguard.py`.

杩欎釜鐩綍鍖呭惈鍏ㄥ眬 `codeguard` 鍚姩鍣ㄣ€?瀹冧笉鏄浜屽瀹炵幇锛屽畠鐨勪綔鐢ㄥ彧鏄妸椤圭洰鍛戒护杞彂缁欓」鐩唴鐨勫畼鏂硅剼鏈?`scripts/codeguard.py`銆?
## Install

Requires Python 3.10 or newer.

闇€瑕?Python 3.10 鎴栨洿楂樼増鏈€?
```bash
# Install the skill bundle into detected IDE skill folders
python install.py

# Install the bundle and the global launcher
python install.py --install-cli
```

```bash
# 瀹夎鎶€鑳藉寘鍒版娴嬪埌鐨?IDE 鎶€鑳界洰褰?python install.py

# 鍚屾椂瀹夎鎶€鑳藉寘鍜屽叏灞€鍚姩鍣?python install.py --install-cli
```

On Windows the launcher is installed into `%USERPROFILE%\.codeguard\bin`.
On macOS and Linux it is installed into `~/.local/bin`.

鍦?Windows 涓婏紝鍚姩鍣ㄤ細瀹夎鍒?`%USERPROFILE%\.codeguard\bin`銆?鍦?macOS 鍜?Linux 涓婏紝浼氬畨瑁呭埌 `~/.local/bin`銆?
## Supported Commands

Global command:

- `codeguard status` (supports `--json`)
- `codeguard doctor` (supports `--json`)

Forwarded project-local commands:

- `codeguard init`
- `codeguard add`
- `codeguard index`
- `codeguard show-index`
- `codeguard validate-index`
- `codeguard backup`
- `codeguard confirm`
- `codeguard snapshot`
- `codeguard rollback`
- `codeguard list`
- `codeguard status` (supports `--json`)
- `codeguard doctor` (supports `--json`)
- `codeguard batch` (supports `--json` and `--fail-fast`)

鏀寔鐨勫懡浠わ細

鍏ㄥ眬鍛戒护锛?
- `codeguard status` (supports `--json`)

浼氳浆鍙戝埌椤圭洰鍐呭畼鏂硅剼鏈殑鍛戒护锛?
- `codeguard init`
- `codeguard add`
- `codeguard index`
- `codeguard show-index`
- `codeguard validate-index`
- `codeguard backup`
- `codeguard confirm`
- `codeguard snapshot`
- `codeguard rollback`
- `codeguard list`
- `codeguard status` (supports `--json`)
- `codeguard doctor` (supports `--json`)
- `codeguard batch` (supports `--json` and `--fail-fast`)

## Notes

- Run the launcher inside a project that already contains the CodeGuard bundle.
- For files over 200 lines, create or update the feature index only after the user authorizes it.
- Success still depends on explicit user confirmation, not on tests alone.

琛ュ厖璇存槑锛?
- 璇峰湪宸茬粡鍖呭惈 CodeGuard 鎶€鑳藉寘鐨勯」鐩唴浣跨敤杩欎釜鍚姩鍣ㄣ€?- 瀵硅秴杩?200 琛岀殑鏂囦欢锛屽彧鏈夊湪鐢ㄦ埛鎺堟潈鍚庢墠鑳藉垱寤烘垨鏇存柊鍔熻兘绱㈠紩銆?- 鎴愬姛浠嶇劧鍙互鐢ㄦ埛鏄庣‘纭浣滀负鍑嗙怀锛屼笉鑳戒粎闈犳祴璇曠粨鏋滃垽鏂€?


- `codeguard schema` (supports `--json-compact`)

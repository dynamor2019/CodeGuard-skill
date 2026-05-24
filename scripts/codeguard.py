# [CodeGuard Feature Index]
# - get_comment_format -> line 99
# - release_handle_lock -> line 342
# - get_storage_suffix -> line 637
# - has_protection_marker -> line 835
# - get_feature_index -> line 1147
# - create_snapshot_record -> line 1584
# - refresh_feature_indexes -> line 2023
# - main -> line 3098
# [/CodeGuard Feature Index]

#!/usr/bin/env python3
"""Project-local feature indexing, confirmation, and snapshot workflow for CodeGuard."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

VERSION = "1.4.0"

CODEGUARD_DIR = Path(".codeguard")
VERSIONS_DIR = CODEGUARD_DIR / "versions"
TEMP_DIR = CODEGUARD_DIR / "temp"
RECORDS_DIR = CODEGUARD_DIR / "records"
INDEX_FILE = CODEGUARD_DIR / "index.json"
LOCK_FILE = CODEGUARD_DIR / "index.lock"
MODIFICATIONS_FILE = RECORDS_DIR / "modifications.md"

DEFAULT_INDEX_THRESHOLD = 200
FEATURE_INDEX_START = "[CodeGuard Feature Index]"
FEATURE_INDEX_END = "[/CodeGuard Feature Index]"
FEATURE_INDEX_ENTRY = re.compile(r"^- (?P<label>.+?) -> line (?P<line>\d+)$")
SIDECAR_INDEX_SUFFIX = ".codeguard-index.json"
INDEX_STATE_SOURCE_INLINE = "inline"
INDEX_STATE_SOURCE_SIDECAR = "sidecar"
JSON_SCHEMA_VERSION = "1.0"
AUTO_INDEX_MAX_ENTRIES = 8
DEFAULT_LOCK_TIMEOUT_SECONDS = 0.8
LOCK_RETRY_INTERVAL_SECONDS = 0.05
ACTIVE_LOCK_TIMEOUT_SECONDS = DEFAULT_LOCK_TIMEOUT_SECONDS

COMMENT_FORMATS = {
    ".js": {"start": "//", "end": ""},
    ".ts": {"start": "//", "end": ""},
    ".jsx": {"start": "//", "end": ""},
    ".tsx": {"start": "//", "end": ""},
    ".java": {"start": "/*", "end": "*/"},
    ".c": {"start": "/*", "end": "*/"},
    ".cpp": {"start": "/*", "end": "*/"},
    ".h": {"start": "/*", "end": "*/"},
    ".cs": {"start": "/*", "end": "*/"},
    ".py": {"start": "#", "end": ""},
    ".sh": {"start": "#", "end": ""},
    ".php": {"start": "#", "end": ""},
    ".rb": {"start": "#", "end": ""},
    ".go": {"start": "//", "end": ""},
    ".rs": {"start": "//", "end": ""},
    ".html": {"start": "<!--", "end": "-->"},
    ".xaml": {"start": "<!--", "end": "-->"},
    ".xml": {"start": "<!--", "end": "-->"},
    ".csproj": {"start": "<!--", "end": "-->"},
    ".css": {"start": "/*", "end": "*/"},
}
SIDECAR_INDEX_EXTENSIONS = {
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".env",
    ".properties",
}

PROTECTION_MARKER = "[CodeGuard Protection]"
MODIFICATION_POLICY_PREFIX = "Policy:"
COMMENT_PREFIX_PATTERN = r"(?://|#|/\*+|\*|<!--)"
LEGACY_PROTECTION_PATTERNS = (
    re.compile(re.escape(PROTECTION_MARKER)),
    re.compile(
        rf"(?m)^\s*{COMMENT_PREFIX_PATTERN}\s*Feature Protection:\s*.+\[(Completed|Verified|Stable)\]"
    ),
    re.compile(rf"(?m)^\s*{COMMENT_PREFIX_PATTERN}\s*Feature Protection Mark\b"),
    re.compile(rf"(?m)^\s*{COMMENT_PREFIX_PATTERN}\s*Status:\s*(Completed|Verified|Stable)\b"),
)


def get_comment_format(file_path: str | Path) -> dict[str, str]:
    ext = Path(file_path).suffix.lower()
    return COMMENT_FORMATS.get(ext, {"start": "//", "end": ""})


def describe_inline_comment_syntax(file_path: str | Path) -> str:
    comment = get_comment_format(file_path)
    if comment["end"]:
        return f"{comment['start']} ... {comment['end']}"
    return f"{comment['start']} ..."


def get_index_mode(file_path: str | Path) -> str:
    return INDEX_STATE_SOURCE_INLINE if can_embed_inline_index(file_path) else INDEX_STATE_SOURCE_SIDECAR


def describe_index_format(file_path: str | Path, project_path: str | Path = ".") -> str:
    if can_embed_inline_index(file_path):
        return f"inline comments ({describe_inline_comment_syntax(file_path)})"

    sidecar = get_sidecar_index_path(file_path, project_path)
    return f"sidecar JSON ({sidecar.name})"


def build_json_payload(report_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    base = {
        "schema_version": JSON_SCHEMA_VERSION,
        "report_type": report_type,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    base.update(payload)
    return base


def emit_json(payload: dict[str, Any], *, compact: bool = False) -> None:
    if compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_schema_payload(report_type: str) -> dict[str, Any]:
    schema_map: dict[str, dict[str, Any]] = {
        "status": {
            "required_fields": [
                "schema_version",
                "report_type",
                "generated_at",
                "ok",
                "file_key",
                "index_valid",
                "snapshots",
            ],
            "notes": "File-level health report.",
        },
        "doctor": {
            "required_fields": [
                "schema_version",
                "report_type",
                "generated_at",
                "project",
                "healthy",
                "errors",
                "warnings",
            ],
            "notes": "Project-level metadata and snapshot/index consistency report.",
        },
        "batch": {
            "required_fields": [
                "schema_version",
                "report_type",
                "generated_at",
                "action",
                "ok",
                "fail_fast",
                "stopped_early",
                "result_count",
                "results",
            ],
            "notes": "Batch execution report across files.",
        },
    }

    if report_type == "all":
        return build_json_payload(
            "schema",
            {
                "target": "all",
                "schemas": schema_map,
            },
        )

    selected = schema_map[report_type]
    return build_json_payload(
        "schema",
        {
            "target": report_type,
            "schema": selected,
        },
    )


def show_schema(report_type: str = "all", *, compact: bool = False) -> None:
    emit_json(build_schema_payload(report_type), compact=compact)


def normalize_project_path(project_path: str | Path = ".") -> Path:
    return Path(project_path).expanduser().resolve()


def resolve_file_path(file_path: str | Path, project_path: str | Path = ".") -> Path:
    raw = Path(file_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    return (normalize_project_path(project_path) / raw).resolve()


def default_index_data() -> dict[str, Any]:
    return {
        "versions": {},
        "last_version": {},
        "current_state": {},
        "protected_features": {},
        "index_state": {},
    }


def normalize_index_data(data: Any) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    normalized = default_index_data()
    if not isinstance(data, dict):
        issues.append("root is not an object")
        return normalized, issues

    for key in normalized:
        value = data.get(key)
        if isinstance(value, dict):
            normalized[key] = value
        elif value is None:
            issues.append(f"missing key: {key}")
        else:
            issues.append(f"invalid type for {key}, expected object")

    for file_key, versions in list(normalized["versions"].items()):
        if not isinstance(versions, list):
            issues.append(f"versions[{file_key}] is not a list")
            normalized["versions"][file_key] = []
            continue

        repaired_versions: list[dict[str, Any]] = []
        for item in versions:
            if isinstance(item, dict):
                repaired_versions.append(item)
            else:
                issues.append(f"versions[{file_key}] contains non-object entries")
        normalized["versions"][file_key] = repaired_versions

    for file_key, versions in normalized["versions"].items():
        max_version = 0
        for snapshot in versions:
            try:
                max_version = max(max_version, int(snapshot.get("version", 0)))
            except (TypeError, ValueError):
                issues.append(f"versions[{file_key}] has invalid version field")

        stored_last = normalized["last_version"].get(file_key, 0)
        try:
            stored_last_int = int(stored_last)
        except (TypeError, ValueError):
            stored_last_int = 0
            issues.append(f"last_version[{file_key}] is invalid")

        if max_version != stored_last_int:
            normalized["last_version"][file_key] = max_version
            issues.append(f"last_version[{file_key}] repaired to {max_version}")

    for file_key, feature_value in list(normalized["protected_features"].items()):
        if isinstance(feature_value, list):
            normalized["protected_features"][file_key] = [str(item) for item in feature_value if str(item).strip()]
        elif isinstance(feature_value, str):
            normalized["protected_features"][file_key] = [feature_value]
            issues.append(f"protected_features[{file_key}] converted from string to list")
        else:
            normalized["protected_features"][file_key] = []
            issues.append(f"protected_features[{file_key}] reset to []")

    return normalized, issues


@contextmanager
def index_lock(project_path: str | Path = ".", timeout_seconds: float | None = None):
    project_root = normalize_project_path(project_path)
    lock_path = project_root / LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    effective_timeout = ACTIVE_LOCK_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds

    with lock_path.open("a+", encoding="utf-8") as handle:
        started = time.time()
        acquired = False
        while not acquired:
            try:
                try_acquire_handle_lock(handle)
                acquired = True
            except OSError:
                waited = time.time() - started
                if waited >= effective_timeout:
                    status = inspect_lock_state(project_root)
                    raise TimeoutError(
                        build_lock_timeout_message(
                            project_root=project_root,
                            lock_status=status,
                            waited_seconds=waited,
                            timeout_seconds=effective_timeout,
                        )
                    )
                time.sleep(LOCK_RETRY_INTERVAL_SECONDS)

        try:
            yield
        finally:
            release_handle_lock(handle)


def set_active_lock_timeout(timeout_seconds: float) -> None:
    if timeout_seconds < 0:
        raise ValueError("lock timeout must be >= 0")
    global ACTIVE_LOCK_TIMEOUT_SECONDS
    ACTIVE_LOCK_TIMEOUT_SECONDS = timeout_seconds


def try_acquire_handle_lock(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def release_handle_lock(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def lock_path_for_project(project_path: str | Path = ".") -> Path:
    project_root = normalize_project_path(project_path)
    return project_root / LOCK_FILE


def inspect_lock_state(project_path: str | Path = ".") -> dict[str, Any]:
    project_root = normalize_project_path(project_path)
    lock_path = lock_path_for_project(project_root)
    lock_exists = lock_path.exists()
    last_modified: str | None = None
    if lock_exists:
        try:
            last_modified = dt.datetime.fromtimestamp(lock_path.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            last_modified = None

    can_acquire = True
    occupied = False
    probe_error: str | None = None
    if lock_exists:
        with lock_path.open("a+", encoding="utf-8") as handle:
            try:
                try_acquire_handle_lock(handle)
            except OSError as exc:
                can_acquire = False
                occupied = True
                probe_error = exc.__class__.__name__
            else:
                release_handle_lock(handle)

    suspected_stale = lock_exists and can_acquire
    if occupied:
        state_text = "occupied"
        possible_causes = [
            "并发进程：另一个 CodeGuard 正在写入索引。",
            "误判可能较低：文件锁探测显示当前不可抢占。",
        ]
    elif suspected_stale:
        state_text = "stale_or_idle"
        possible_causes = [
            "上次异常退出：遗留 lock 文件但当前并未被占用。",
            "误判：某些工具可能创建了 lock 文件但未持有锁。",
        ]
    elif lock_exists:
        state_text = "idle"
        possible_causes = ["lock 文件存在，但当前可立即获取。"]
    else:
        state_text = "absent"
        possible_causes = ["未发现 lock 文件。"]

    return {
        "project": project_root.as_posix(),
        "lock_path": lock_path.as_posix(),
        "lock_exists": lock_exists,
        "last_modified": last_modified,
        "can_acquire_immediately": can_acquire,
        "occupied": occupied,
        "suspected_stale": suspected_stale,
        "state": state_text,
        "probe_error": probe_error,
        "possible_causes": possible_causes,
        "suggested_commands": [
            "python scripts/codeguard.py lock-status --json",
            "python scripts/codeguard.py unlock --yes",
            "python scripts/codeguard.py unlock --force --yes",
        ],
    }


def build_lock_timeout_message(
    *,
    project_root: Path,
    lock_status: dict[str, Any],
    waited_seconds: float,
    timeout_seconds: float,
) -> str:
    lock_path = lock_status["lock_path"]
    state = lock_status["state"]
    occupied = lock_status["occupied"]
    stale = lock_status["suspected_stale"]
    if occupied:
        status_line = (
            f"当前状态：另一个 CodeGuard 正在运行（state={state}, occupied=true），"
            f"等待 {waited_seconds:.2f}s 后仍未拿到锁。"
        )
    elif stale:
        status_line = (
            f"当前状态：检测到疑似陈旧锁（state={state}, occupied=false），"
            f"等待 {waited_seconds:.2f}s 后未继续。"
        )
    else:
        status_line = (
            f"当前状态：锁不可用（state={state}），等待 {waited_seconds:.2f}s 后未继续。"
        )
    suggest_line = (
        "推荐命令："
        f"python scripts/codeguard.py lock-status --project \"{project_root.as_posix()}\"；"
        "若确认是陈旧锁，可执行 python scripts/codeguard.py unlock --yes"
    )
    risk_line = (
        f"风险说明：强制解锁可能导致并发写入损坏，请仅在确认无其它进程占用时使用 --force --yes "
        f"(lock_path={lock_path}, timeout={timeout_seconds:.2f}s)。"
    )
    return "\n".join([status_line, suggest_line, risk_line])


def show_lock_status(
    project_path: str | Path = ".",
    *,
    json_output: bool = False,
    json_compact: bool = False,
) -> bool:
    status = inspect_lock_state(project_path)
    if json_output:
        emit_json(build_json_payload("lock-status", status), compact=json_compact)
        return True

    print("CodeGuard 锁状态")
    print(f"  lock_path: {status['lock_path']}")
    print(f"  lock_exists: {'yes' if status['lock_exists'] else 'no'}")
    print(f"  last_modified: {status['last_modified'] or 'n/a'}")
    print(f"  can_acquire_immediately: {'yes' if status['can_acquire_immediately'] else 'no'}")
    print(f"  state: {status['state']}")
    print("  possible_causes:")
    for cause in status["possible_causes"]:
        print(f"    - {cause}")
    print("  next_steps:")
    for command in status["suggested_commands"][:2]:
        print(f"    - {command}")
    return True


def unlock_lock_file(
    project_path: str | Path = ".",
    *,
    assume_yes: bool = False,
    force: bool = False,
) -> bool:
    project_root = normalize_project_path(project_path)
    status = inspect_lock_state(project_root)
    lock_path = Path(status["lock_path"])
    if not status["lock_exists"]:
        print(f"lock 文件不存在，无需清理: {lock_path.as_posix()}")
        return True

    if status["occupied"]:
        print("当前状态：检测到锁正在被占用（occupied=true）。")
        print("推荐命令：先执行 python scripts/codeguard.py lock-status --json 查看详情。")
        print("风险说明：占用中强制解锁可能造成 index.json 写入冲突。")
        if not force:
            print("默认拒绝解锁。若你明确接受风险，请使用 --force --yes。")
            return False
        if not assume_yes:
            print("检测到占用时，必须同时提供 --force --yes 才允许继续。")
            return False
    else:
        print("当前状态：lock 文件存在但未被占用，属于可清理的疑似陈旧锁。")
        print("推荐命令：python scripts/codeguard.py unlock --yes")
        print("风险说明：清理后下次命令会自动重建 lock 文件。")
        if not assume_yes:
            answer = input("输入 YES 确认清理陈旧锁: ").strip()
            if answer != "YES":
                print("已取消解锁。")
                return False

    try:
        lock_path.unlink()
    except OSError as exc:
        print(f"清理失败: {exc}")
        return False

    print(f"已清理 lock 文件: {lock_path.as_posix()}")
    return True


def init_codeguard(project_path: str | Path = ".", quiet: bool = False) -> str:
    project_root = normalize_project_path(project_path)
    for path in (CODEGUARD_DIR, VERSIONS_DIR, TEMP_DIR, RECORDS_DIR):
        (project_root / path).mkdir(parents=True, exist_ok=True)

    index_path = project_root / INDEX_FILE
    if not index_path.exists():
        write_json(index_path, default_index_data())

    if not quiet:
        print(f"CodeGuard initialized at: {(project_root / CODEGUARD_DIR).as_posix()}")
    return str(project_root / CODEGUARD_DIR)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_index(project_path: str | Path = ".", *, repair: bool = False) -> dict[str, Any]:
    project_root = normalize_project_path(project_path)
    init_codeguard(project_root, quiet=True)
    index_path = project_root / INDEX_FILE

    with index_lock(project_root):
        try:
            raw = read_json(index_path)
            normalized, issues = normalize_index_data(raw)
        except json.JSONDecodeError:
            broken_dir = project_root / CODEGUARD_DIR / "broken"
            broken_dir.mkdir(parents=True, exist_ok=True)
            backup = broken_dir / f"index.corrupted.{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            shutil.copy2(index_path, backup)
            normalized = default_index_data()
            issues = ["index.json was corrupted and reset"]

        if repair and issues:
            write_json(index_path, normalized)
        return normalized


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def save_index(project_path: str | Path, index: dict[str, Any]) -> None:
    project_root = normalize_project_path(project_path)
    with index_lock(project_root):
        normalized, _ = normalize_index_data(index)
        write_json(project_root / INDEX_FILE, normalized)


def mutate_index(
    project_path: str | Path,
    mutation: Callable[[dict[str, Any]], Any],
    *,
    repair: bool = True,
) -> Any:
    project_root = normalize_project_path(project_path)
    init_codeguard(project_root, quiet=True)
    index_path = project_root / INDEX_FILE

    with index_lock(project_root):
        try:
            raw = read_json(index_path)
        except json.JSONDecodeError:
            raw = default_index_data()
        normalized, _ = normalize_index_data(raw)
        result = mutation(normalized)
        if repair:
            normalized, _ = normalize_index_data(normalized)
        write_json(index_path, normalized)
        return result


def calculate_hash(file_path: str | Path) -> str | None:
    target = Path(file_path)
    if not target.exists():
        return None

    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_file_key(file_path: str | Path, project_path: str | Path = ".") -> str:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    try:
        return target.relative_to(project_root).as_posix()
    except ValueError:
        return target.as_posix()


def get_storage_suffix(file_path: str | Path, project_path: str | Path = ".") -> str:
    file_key = get_file_key(file_path, project_path)
    return hashlib.sha256(file_key.encode("utf-8")).hexdigest()[:12]


def next_version(file_path: str | Path, project_path: str | Path = ".") -> int:
    index = load_index(project_path)
    file_key = get_file_key(file_path, project_path)
    return index["last_version"].get(file_key, 0) + 1


def can_embed_inline_index(file_path: str | Path) -> bool:
    ext = Path(file_path).suffix.lower()
    return ext in COMMENT_FORMATS and ext not in SIDECAR_INDEX_EXTENSIONS


def get_sidecar_index_path(file_path: str | Path, project_path: str | Path = ".") -> Path:
    target = resolve_file_path(file_path, project_path)
    return target.with_name(target.name + SIDECAR_INDEX_SUFFIX)


def read_sidecar_index(file_path: str | Path, project_path: str | Path = ".") -> dict[str, Any] | None:
    sidecar = get_sidecar_index_path(file_path, project_path)
    if not sidecar.exists():
        return None
    try:
        with sidecar.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        payload["entries"] = []
        return payload
    normalized_entries: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        label = str(item.get("feature", "")).strip()
        try:
            line_number = int(item.get("line", 0))
        except (TypeError, ValueError):
            continue
        if label and line_number > 0:
            normalized_entries.append({"feature": label, "line": line_number})
    payload["entries"] = normalized_entries
    return payload


def write_sidecar_index(
    file_path: str | Path,
    entries: list[tuple[str, int]],
    project_path: str | Path = ".",
) -> Path:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    sidecar = get_sidecar_index_path(target, project_root)
    payload = {
        "file": get_file_key(target, project_root),
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "line_count": count_code_lines(target, project_root),
        "file_hash": calculate_hash(target),
        "entries": [{"feature": label, "line": line_number} for label, line_number in entries],
    }
    write_json(sidecar, payload)
    return sidecar


def upsert_index_state(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    entries: list[tuple[str, int]] | None = None,
) -> None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    file_key = get_file_key(target, project_root)
    source = INDEX_STATE_SOURCE_INLINE if can_embed_inline_index(target) else INDEX_STATE_SOURCE_SIDECAR
    lines = read_text(target).splitlines()
    resolved_entries = entries if entries is not None else get_feature_index(target, project_root)

    def mutation(index: dict[str, Any]) -> None:
        index["index_state"][file_key] = {
            "source": source,
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "file_hash": calculate_hash(target),
            "line_count": count_code_lines(target, project_root),
            "entry_signatures": build_entry_signatures(lines, resolved_entries),
        }

    mutate_index(project_root, mutation)


def get_index_state(file_path: str | Path, project_path: str | Path = ".") -> dict[str, Any] | None:
    index = load_index(project_path)
    return index["index_state"].get(get_file_key(file_path, project_path))


def read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, content: str, *, bom: bool = False) -> None:
    encoding = "utf-8-sig" if bom else "utf-8"
    path.write_text(content, encoding=encoding, newline="\n")


def detect_file_encoding(file_path: Path) -> dict[str, Any]:
    """Detect file encoding, BOM, and line ending style. Returns a metadata dict."""
    with file_path.open("rb") as handle:
        raw = handle.read()

    result: dict[str, Any] = {
        "encoding": "utf-8",
        "bom": False,
        "line_ending": "\n",
        "byte_size": len(raw),
    }

    if not raw:
        return result

    # BOM detection
    if raw[:3] == b"\xef\xbb\xbf":
        result["bom"] = True
        result["encoding"] = "utf-8"
    elif raw[:2] == b"\xff\xfe":
        result["encoding"] = "utf-16-le"
        result["bom"] = True
    elif raw[:2] == b"\xfe\xff":
        result["encoding"] = "utf-16-be"
        result["bom"] = True
    elif raw[:4] == b"\xff\xfe\x00\x00":
        result["encoding"] = "utf-32-le"
        result["bom"] = True
    elif raw[:4] == b"\x00\x00\xfe\xff":
        result["encoding"] = "utf-32-be"
        result["bom"] = True
    else:
        # Heuristic: try UTF-8 decode; if it fails, check GBK
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                decoded = raw.decode("gbk")
                if "�" not in decoded[:1024]:
                    result["encoding"] = "gbk"
            except (UnicodeDecodeError, LookupError):
                pass

    # Line ending detection
    crlf_count = raw.count(b"\r\n")
    lf_only = len(re.findall(rb"(?<!\r)\n", raw))
    if crlf_count > lf_only:
        result["line_ending"] = "\r\n"

    return result


def read_text_preserving(path: Path) -> tuple[str, dict[str, Any]]:
    """Read file content while detecting encoding metadata. Returns (content, metadata)."""
    meta = detect_file_encoding(path)
    encoding = meta["encoding"]
    if encoding == "utf-8" and meta["bom"]:
        encoding = "utf-8-sig"
    try:
        content = path.read_text(encoding=encoding)
    except (UnicodeDecodeError, LookupError):
        content = path.read_text(encoding="utf-8", errors="replace")
        meta["encoding"] = "utf-8"
    return content, meta


def write_text_preserving(path: Path, content: str, meta: dict[str, Any]) -> None:
    """Write file content while preserving encoding/line-ending metadata."""
    encoding = meta.get("encoding", "utf-8")
    line_ending = meta.get("line_ending", "\n")
    if encoding == "utf-8" and meta.get("bom"):
        encoding = "utf-8-sig"
    if line_ending != "\n":
        content = content.replace("\n", line_ending)
    try:
        path.write_text(content, encoding=encoding, newline="")
    except (UnicodeEncodeError, LookupError):
        path.write_text(content, encoding="utf-8", newline="")


def has_codeguard_marker(content: str) -> bool:
    return PROTECTION_MARKER in content


def has_protection_marker(content: str) -> bool:
    return any(pattern.search(content) for pattern in LEGACY_PROTECTION_PATTERNS)


def render_marker(file_path: str | Path, feature_name: str, version: int) -> str:
    comment = get_comment_format(file_path)
    start = comment["start"]
    end = f" {comment['end']}" if comment["end"] else ""
    protected_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    marker_lines = [
        f"{start} {PROTECTION_MARKER}{end}",
        f"{start} Feature: {feature_name}{end}",
        f"{start} Version: {version}{end}",
        f"{start} Protected: {protected_at}{end}",
        f"{start} {MODIFICATION_POLICY_PREFIX} Do not modify directly. Explain reason before edits.{end}",
        "",
    ]
    return "\n".join(marker_lines)


def format_comment_line(file_path: str | Path, payload: str) -> str:
    comment = get_comment_format(file_path)
    start = comment["start"]
    end = f" {comment['end']}" if comment["end"] else ""
    return f"{start} {payload}{end}"


def apply_confirm_policy_note(file_path: str | Path, reason: str) -> bool:
    target = resolve_file_path(file_path)
    content = read_text(target)

    reason_text = normalize_signature_text(reason)
    if len(reason_text) > 120:
        reason_text = reason_text[:117] + "..."

    policy_payload = (
        f"{MODIFICATION_POLICY_PREFIX} Do not modify directly. "
        f"Explain reason before edits. Last confirm reason: {reason_text}"
    )

    if not has_codeguard_marker(content):
        # Fallback for files where previous edits replaced the full file and removed the marker.
        # Avoid inserting a new header into large inline-index files because it can invalidate index line references.
        if is_index_required(target) and can_embed_inline_index(target):
            return False
        header = format_comment_line(target, policy_payload)
        lines = content.splitlines()
        prefix_len = leading_preamble_length(lines)
        preamble = lines[:prefix_len]
        body = lines[prefix_len:]

        merged: list[str] = []
        if preamble:
            merged.extend(preamble)
            merged.append("")
        merged.append(header)
        if body:
            merged.append("")
            merged.extend(body)
        write_text(target, "\n".join(merged).rstrip("\n") + "\n")
        return True

    lines = content.splitlines()
    marker_line = None
    for idx, line in enumerate(lines):
        if PROTECTION_MARKER in line:
            marker_line = idx
            break
    if marker_line is None:
        return False

    search_end = min(len(lines), marker_line + 12)
    replaced = False
    for idx in range(marker_line + 1, search_end):
        payload = normalize_index_payload(lines[idx], target)
        if not payload:
            continue
        if payload.startswith(MODIFICATION_POLICY_PREFIX):
            lines[idx] = format_comment_line(target, policy_payload)
            replaced = True
            break

    if not replaced:
        for idx in range(marker_line + 1, search_end):
            if "=" * 10 in lines[idx]:
                lines[idx] = format_comment_line(target, policy_payload)
                replaced = True
                break

    if not replaced:
        for idx in range(marker_line + 1, search_end):
            payload = normalize_index_payload(lines[idx], target)
            if not payload:
                continue
            if payload.startswith("Protected:"):
                lines[idx] = format_comment_line(target, f"{payload} | {policy_payload}")
                replaced = True
                break

    if not replaced:
        return False

    trailing_newline = "\n" if content.endswith("\n") else ""
    write_text(target, "\n".join(lines) + trailing_newline)
    return True


def update_marker_metadata(
    file_path: str | Path,
    feature_name: str,
    version: int,
) -> None:
    target = resolve_file_path(file_path)
    content = read_text(target)
    lines = content.splitlines()
    protected_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    marker_seen = False
    updated_lines: list[str] = []

    for line in lines:
        current = line
        if PROTECTION_MARKER in line:
            marker_seen = True
        elif marker_seen and "Feature:" in line:
            current = re.sub(r"(Feature:\s*).*$", rf"\1{feature_name}", current, count=1)
        elif marker_seen and "Version:" in line:
            current = re.sub(r"(Version:\s*)\d+", rf"\g<1>{version}", current, count=1)
        elif marker_seen and "Protected:" in line:
            current = re.sub(r"(Protected:\s*).*$", rf"\1{protected_at}", current, count=1)
            marker_seen = False

        updated_lines.append(current)

    trailing_newline = "\n" if content.endswith("\n") else ""
    write_text(target, "\n".join(updated_lines) + trailing_newline)


def ensure_protection_marker(
    file_path: str | Path,
    feature_name: str,
    version: int,
) -> bool:
    target = resolve_file_path(file_path)
    content = read_text(target)
    if has_codeguard_marker(content):
        update_marker_metadata(target, feature_name, version)
        return False
    if has_protection_marker(content):
        return False

    marker = render_marker(target, feature_name, version)
    lines = content.splitlines()
    prefix_len = leading_preamble_length(lines)
    preamble = lines[:prefix_len]
    body = lines[prefix_len:]

    merged: list[str] = []
    if preamble:
        merged.extend(preamble)
        merged.append("")
    merged.extend(marker.splitlines())
    if body:
        merged.append("")
        merged.extend(body)
    write_text(target, "\n".join(merged).rstrip("\n") + "\n")
    return True


def normalize_index_payload(line: str, file_path: str | Path) -> str | None:
    comment = get_comment_format(file_path)
    payload = line.strip()
    start = comment["start"]
    end = comment["end"]

    if not payload.startswith(start):
        return None

    payload = payload[len(start) :].strip()
    if end:
        if not payload.endswith(end):
            return None
        payload = payload[: -len(end)].strip()
    return payload


def normalize_signature_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def line_signature(lines: list[str], line_number: int) -> str:
    if line_number < 1 or line_number > len(lines):
        return ""
    chunk = lines[line_number - 1 : min(len(lines), line_number + 2)]
    normalized = "\n".join(normalize_signature_text(item) for item in chunk)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def build_entry_signatures(lines: list[str], entries: list[tuple[str, int]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for label, line_number in entries:
        payload.append(
            {
                "feature": label,
                "line": line_number,
                "signature": line_signature(lines, line_number),
            }
        )
    return payload


def detect_signature_drift(
    lines: list[str],
    entries: list[tuple[str, int]],
    stored_signatures: list[dict[str, Any]],
) -> list[str]:
    if not stored_signatures:
        return []

    warnings: list[str] = []
    signature_map: dict[tuple[str, int], str] = {}
    for item in stored_signatures:
        if not isinstance(item, dict):
            continue
        label = str(item.get("feature", "")).strip()
        try:
            line_number = int(item.get("line", 0))
        except (TypeError, ValueError):
            continue
        signature = str(item.get("signature", "")).strip()
        if label and line_number > 0 and signature:
            signature_map[(label, line_number)] = signature

    for label, line_number in entries:
        stored = signature_map.get((label, line_number))
        if not stored:
            continue
        current = line_signature(lines, line_number)
        if current == stored:
            continue

        nearby_match = False
        for delta in range(-20, 21):
            probe = line_number + delta
            if probe < 1 or probe > len(lines):
                continue
            if line_signature(lines, probe) == stored:
                nearby_match = True
                break

        if nearby_match:
            warnings.append(
                f'Feature entry "{label}" appears to have moved near line {line_number}; index may be stale.'
            )
        else:
            warnings.append(
                f'Feature entry "{label}" semantic signature changed at line {line_number}; index may be stale.'
            )
    return warnings


def leading_preamble_length(lines: list[str]) -> int:
    count = 0
    encoding_pattern = re.compile(r"#.*coding[:=]\s*[-\w.]+")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and stripped.startswith("#!"):
            count += 1
            continue
        if stripped.lower().startswith("<!doctype") or stripped.startswith("<?xml"):
            count += 1
            continue
        if encoding_pattern.match(stripped):
            count += 1
            continue
        break
    return count


def find_feature_index_bounds(lines: list[str], file_path: str | Path) -> tuple[int | None, int | None]:
    start = None
    for index, line in enumerate(lines):
        payload = normalize_index_payload(line, file_path)
        if payload is None:
            continue
        if payload == FEATURE_INDEX_START:
            start = index
            continue
        if payload == FEATURE_INDEX_END and start is not None:
            return start, index
    return None, None


def extract_feature_index_entries_from_lines(
    lines: list[str], file_path: str | Path
) -> list[tuple[str, int]]:
    start, end = find_feature_index_bounds(lines, file_path)
    if start is None or end is None:
        return []

    entries: list[tuple[str, int]] = []
    for line in lines[start + 1 : end]:
        payload = normalize_index_payload(line, file_path)
        if not payload:
            continue
        match = FEATURE_INDEX_ENTRY.match(payload)
        if not match:
            continue
        entries.append((match.group("label"), int(match.group("line"))))
    return entries


def get_feature_index(file_path: str | Path, project_path: str | Path = ".") -> list[tuple[str, int]]:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        return []

    if can_embed_inline_index(target):
        return extract_feature_index_entries_from_lines(read_text(target).splitlines(), target)

    sidecar_payload = read_sidecar_index(target, project_path)
    if sidecar_payload is None:
        return []
    return [(item["feature"], int(item["line"])) for item in sidecar_payload.get("entries", [])]


def count_code_lines(file_path: str | Path, project_path: str | Path = ".") -> int:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        return 0
    return len(read_text(target).splitlines())


def is_index_required(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    threshold: int = DEFAULT_INDEX_THRESHOLD,
) -> bool:
    return count_code_lines(file_path, project_path) > threshold


def render_feature_index_lines(
    file_path: str | Path,
    entries: list[tuple[str, int]],
) -> list[str]:
    comment = get_comment_format(file_path)
    start = comment["start"]
    end = f" {comment['end']}" if comment["end"] else ""
    lines = [f"{start} {FEATURE_INDEX_START}{end}"]
    for label, line_number in entries:
        lines.append(f"{start} - {label} -> line {line_number}{end}")
    lines.append(f"{start} {FEATURE_INDEX_END}{end}")
    return lines


def parse_index_entry_spec(spec: str) -> tuple[str, int]:
    if ":" not in spec:
        raise ValueError(
            f'Unsupported entry format: {spec}. Use "Feature description:LineNumber".'
        )
    label, raw_line = spec.rsplit(":", 1)
    label = label.strip()
    if not label:
        raise ValueError("Feature description cannot be empty.")
    line_number = int(raw_line.strip())
    if line_number < 1:
        raise ValueError("Line numbers must be positive.")
    return label, line_number


def _condense_label(text: str, *, limit: int = 64) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = normalized.strip("`'\"-:;,.()[]{}")
    if len(normalized) > limit:
        normalized = normalized[: limit - 3].rstrip() + "..."
    return normalized


def _sample_entries(entries: list[tuple[str, int]], max_entries: int) -> list[tuple[str, int]]:
    if len(entries) <= max_entries:
        return entries
    if max_entries <= 1:
        return [entries[0]]

    selected: list[tuple[str, int]] = []
    seen: set[int] = set()
    last_index = len(entries) - 1
    for i in range(max_entries):
        idx = round(i * last_index / (max_entries - 1))
        if idx in seen:
            continue
        seen.add(idx)
        selected.append(entries[idx])
    return selected


def review_full_document_for_index(
    file_path: str | Path,
    project_path: str | Path = ".",
) -> tuple[Path, list[str], str]:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        raise FileNotFoundError(f"File not found: {target.as_posix()}")

    # Read the full document once before any index generation decision.
    content = read_text(target)
    lines = content.splitlines()
    if not lines:
        raise ValueError("Cannot generate index for an empty file.")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return target, lines, digest


def generate_feature_index_entries(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    max_entries: int = AUTO_INDEX_MAX_ENTRIES,
) -> list[tuple[str, int]]:
    target, lines, _ = review_full_document_for_index(file_path, project_path)
    ext = target.suffix.lower()
    candidates: list[tuple[str, int]] = []

    py_pattern = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_]\w*)")
    js_pattern = re.compile(
        r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)|"
        r"^(?:export\s+)?class\s+([A-Za-z_]\w*)|"
        r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\(",
    )
    c_like_pattern = re.compile(
        r"^(?:public|private|protected|internal|static|sealed|virtual|override|\s)*"
        r"(?:class|struct|interface|enum)\s+([A-Za-z_]\w*)|"
        r"^(?:public|private|protected|internal|static|virtual|override|\s)*"
        r"[A-Za-z_<>\[\],\s]+\s+([A-Za-z_]\w*)\s*\(",
    )
    xml_pattern = re.compile(r"^<([A-Za-z_][\w:.-]*)\b")
    toml_ini_pattern = re.compile(r"^\[([^\]]+)\]")

    for line_no, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            continue

        label = ""
        if ext == ".py":
            match = py_pattern.match(stripped)
            if match:
                label = match.group(1)
        elif ext in {".js", ".ts", ".jsx", ".tsx", ".go", ".rs"}:
            match = js_pattern.match(stripped)
            if match:
                label = next((group for group in match.groups() if group), "")
        elif ext in {".java", ".c", ".cpp", ".h", ".cs"}:
            match = c_like_pattern.match(stripped)
            if match:
                label = next((group for group in match.groups() if group), "")
        elif ext in {".html", ".xml", ".xaml", ".csproj"}:
            if stripped.startswith("</") or stripped.startswith("<?") or stripped.startswith("<!"):
                continue
            match = xml_pattern.match(stripped)
            if match:
                label = match.group(1)
        elif ext in {".json", ".yml", ".yaml"}:
            if stripped.startswith(("{", "}", "[", "]", "-", "#")):
                continue
            if ":" in stripped:
                label = stripped.split(":", 1)[0].strip().strip("\"'")
        elif ext in {".toml", ".ini", ".properties", ".env"}:
            sec = toml_ini_pattern.match(stripped)
            if sec:
                label = sec.group(1)
            elif "=" in stripped and not stripped.startswith("#"):
                label = stripped.split("=", 1)[0].strip()
        else:
            if re.match(r"^[A-Za-z_][\w\s:.-]{3,}$", stripped):
                label = stripped

        label = _condense_label(label)
        if label:
            candidates.append((label, line_no))

    if not candidates:
        # Fallback: pick representative non-empty lines.
        fallback: list[tuple[str, int]] = []
        for line_no, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "//", "/*", "*", "<!--", "{", "}", "[", "]")):
                continue
            fallback.append((_condense_label(stripped), line_no))
        candidates = fallback

    # Keep unique labels while preserving order.
    unique: list[tuple[str, int]] = []
    seen_labels: set[str] = set()
    for label, line_no in candidates:
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        unique.append((label, line_no))

    if not unique:
        raise ValueError("Could not auto-generate index entries from file content.")

    sampled = _sample_entries(unique, max_entries=max_entries)
    return sorted(sampled, key=lambda item: item[1])


def apply_feature_index(
    file_path: str | Path,
    entries: list[tuple[str, int]],
    project_path: str | Path = ".",
    *,
    quiet: bool = False,
) -> list[tuple[str, int]] | None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return None

    # Hard requirement: always read the full document before generating/updating index.
    _, reviewed_lines, _ = review_full_document_for_index(target, project_root)
    ordered_entries = sorted(entries, key=lambda item: item[1])
    if not can_embed_inline_index(target):
        line_count = len(reviewed_lines)
        for _, line_number in ordered_entries:
            if line_number > line_count:
                if not quiet:
                    print(f"Feature index line {line_number} exceeds file length {line_count}.")
                return None
        sidecar_path = write_sidecar_index(target, ordered_entries, project_root)
        upsert_index_state(target, project_root, entries=ordered_entries)
        if not quiet:
            print(f"Feature index sidecar updated for: {get_file_key(target, project_root)}")
            print(f"  Sidecar: {sidecar_path.as_posix()}")
        return ordered_entries

    lines = list(reviewed_lines)
    prefix_len = leading_preamble_length(lines)
    main_lines = lines[prefix_len:]
    start, end = find_feature_index_bounds(main_lines, target)

    old_body_start = prefix_len + 1
    if start is not None and end is not None:
        old_body_start = prefix_len + end + 2
        while old_body_start <= len(lines) and not lines[old_body_start - 1].strip():
            old_body_start += 1
        body_lines = main_lines[:start] + main_lines[end + 1 :]
    else:
        body_lines = list(main_lines)
        while old_body_start <= len(lines) and not lines[old_body_start - 1].strip():
            old_body_start += 1

    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)

    placeholder_index = render_feature_index_lines(target, ordered_entries)
    new_lines = list(lines[:prefix_len])
    if new_lines and placeholder_index:
        new_lines.append("")
    new_lines.extend(placeholder_index)
    if body_lines:
        new_lines.append("")
    new_body_start = len(new_lines) + 1
    delta = new_body_start - old_body_start

    adjusted_entries = [
        (label, line_number + delta if line_number >= old_body_start else line_number)
        for label, line_number in ordered_entries
    ]

    final_lines = list(lines[:prefix_len])
    final_index = render_feature_index_lines(target, adjusted_entries)
    if final_lines and final_index:
        final_lines.append("")
    final_lines.extend(final_index)
    if body_lines:
        final_lines.append("")
        final_lines.extend(body_lines)

    content = "\n".join(final_lines).rstrip("\n") + "\n"
    write_text(target, content)
    upsert_index_state(target, project_root, entries=adjusted_entries)
    if not quiet:
        print(f"Feature index updated for: {get_file_key(target, project_root)}")
    return adjusted_entries


def validate_feature_index(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    threshold: int = DEFAULT_INDEX_THRESHOLD,
    quiet: bool = False,
) -> bool:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        if not quiet:
            print(f"File not found: {target.as_posix()}")
        return False

    lines = read_text(target).splitlines()
    required = len(lines) > threshold
    entries = get_feature_index(target, project_root)
    inline_mode = can_embed_inline_index(target)

    problems: list[str] = []
    warnings: list[str] = []

    if inline_mode:
        start, end = find_feature_index_bounds(lines, target)
        if required and (start is None or end is None):
            problems.append(
                f"Feature index is required for files over {threshold} lines but no valid index block was found."
            )
        if start is not None and end is None:
            problems.append("Feature index start marker exists without a matching end marker.")
        if start is not None and end is not None and not entries:
            problems.append("Feature index block exists but contains no valid entries.")
    else:
        sidecar = read_sidecar_index(target, project_root)
        if required and sidecar is None:
            problems.append(
                f"Feature index is required for files over {threshold} lines but sidecar index is missing."
            )
        if sidecar is None and not required:
            warnings.append("Sidecar index not found. This is optional for files at or under the threshold.")

    previous_line = 0
    for label, line_number in entries:
        if len(label) > 80:
            warnings.append(
                f'Feature label "{label}" is long. Keep labels concise for readability and token efficiency.'
            )
        if line_number <= previous_line:
            problems.append("Feature index entries must be sorted by ascending start line.")
        if line_number > len(lines):
            problems.append(f"Feature index line {line_number} exceeds file length {len(lines)}.")
        if line_number <= len(lines):
            pointed_line = lines[line_number - 1].strip()
            if not pointed_line:
                warnings.append(f"Feature entry \"{label}\" points to a blank line ({line_number}).")
        previous_line = line_number

    index_state = get_index_state(target, project_root)
    if index_state is not None:
        current_hash = calculate_hash(target)
        indexed_hash = index_state.get("file_hash")
        if indexed_hash and current_hash and indexed_hash != current_hash:
            warnings.append("Feature index may be stale because the file hash changed after the last index update.")

        stored_signatures = index_state.get("entry_signatures", [])
        warnings.extend(detect_signature_drift(lines, entries, stored_signatures))

    valid = not problems
    mode = get_index_mode(target)
    format_description = describe_index_format(target, project_root)
    if not quiet:
        print(f"Feature index status for: {get_file_key(target, project_root)}")
        print(f"  Line count: {len(lines)}")
        print(f"  Required: {'yes' if required else 'no'}")
        print(f"  Mode: {mode}")
        print(f"  Format: {format_description}")
        print(f"  Entries: {len(entries)}")
        print(f"  Validation: {'valid' if valid else 'invalid'}")
        for warning in warnings:
            print(f"  Warning: {warning}")
        for problem in problems:
            print(f"  Error: {problem}")
    return valid


def show_feature_index(file_path: str | Path, project_path: str | Path = ".") -> list[tuple[str, int]]:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return []

    entries = get_feature_index(target, project_root)
    required = is_index_required(target, project_root)
    mode = get_index_mode(target)
    format_description = describe_index_format(target, project_root)
    print(f"Feature index for: {get_file_key(target, project_root)}")
    print(f"  Required: {'yes' if required else 'no'}")
    print(f"  Mode: {mode}")
    print(f"  Format: {format_description}")
    print(f"  Entries: {len(entries)}")
    if mode == "sidecar":
        print(f"  Sidecar: {get_sidecar_index_path(target, project_root).as_posix()}")
    for index, (label, line_number) in enumerate(entries, start=1):
        print(f"  {index}. {label} -> line {line_number}")
    return entries


def ensure_index_ready(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    threshold: int = DEFAULT_INDEX_THRESHOLD,
) -> bool:
    if not is_index_required(file_path, project_path, threshold=threshold):
        return True
    if validate_feature_index(file_path, project_path, threshold=threshold, quiet=True):
        return True
    print(
        f"Feature index recommended for files over {threshold} lines. "
        "Update with `python scripts/codeguard.py index ... --auto` for efficient navigation (not required to proceed)."
    )
    return False


def update_current_state(
    file_path: str | Path,
    feature_name: str,
    project_path: str | Path = ".",
    *,
    reason: str | None = None,
    source: str,
) -> None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    file_key = get_file_key(target, project_root)
    state = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "feature": feature_name,
        "hash": calculate_hash(target),
        "path": target.as_posix(),
        "source": source,
    }
    if reason:
        state["reason"] = reason

    def mutation(index: dict[str, Any]) -> None:
        index["current_state"][file_key] = state

    mutate_index(project_root, mutation)


def get_current_state(file_path: str | Path, project_path: str | Path = ".") -> dict[str, Any] | None:
    index = load_index(project_path)
    return index["current_state"].get(get_file_key(file_path, project_path))


def create_snapshot_record(
    file_path: str | Path,
    feature_name: str,
    project_path: str | Path = ".",
    *,
    reason: str | None = None,
    ensure_marker: bool = False,
) -> dict[str, Any] | None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return None
    if not ensure_index_ready(target, project_root):
        return None

    init_codeguard(project_root, quiet=True)
    version = next_version(target, project_root)

    if ensure_marker:
        ensure_protection_marker(target, feature_name, version)

    file_key = get_file_key(target, project_root)
    suffix = get_storage_suffix(target, project_root)
    backup_name = f"{target.name}.{suffix}.v{version}.bak"
    backup_path = project_root / VERSIONS_DIR / backup_name
    shutil.copy2(target, backup_path)

    snapshot = {
        "version": version,
        "feature": feature_name,
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "hash": calculate_hash(target),
        "backup_path": backup_path.as_posix(),
        "original_path": target.as_posix(),
        "file_key": file_key,
    }
    if reason:
        snapshot["reason"] = reason

    stale_backup_paths: list[Path] = []

    def mutation(index: dict[str, Any]) -> None:
        previous_versions = list(index["versions"].get(file_key, []))
        for old_snapshot in previous_versions:
            backup = old_snapshot.get("backup_path")
            if not backup:
                continue
            old_backup_path = Path(str(backup))
            stale_backup_paths.append(old_backup_path)

        index["versions"][file_key] = [snapshot]
        index["last_version"][file_key] = version
        current = {
            "timestamp": snapshot["timestamp"],
            "feature": feature_name,
            "hash": snapshot["hash"],
            "path": target.as_posix(),
            "source": "snapshot",
            "reason": reason or "",
        }
        index["current_state"][file_key] = current
        protected = index["protected_features"].setdefault(file_key, [])
        if feature_name not in protected:
            protected.append(feature_name)

    mutate_index(project_root, mutation)

    for stale_path in stale_backup_paths:
        if stale_path.as_posix() == backup_path.as_posix():
            continue
        if not stale_path.exists():
            continue
        try:
            stale_path.unlink()
        except OSError:
            continue

    print(f"Snapshot created: v{version}")
    print(f"  Feature: {feature_name}")
    print(f"  Backup: {backup_path.as_posix()}")
    return snapshot


def create_version_snapshot(
    file_path: str | Path,
    feature_name: str,
    project_path: str | Path = ".",
    *,
    ensure_marker: bool = False,
) -> dict[str, Any] | None:
    return create_snapshot_record(file_path, feature_name, project_path, ensure_marker=ensure_marker)


def create_manual_snapshot(
    file_path: str | Path,
    feature_name: str,
    reason: str,
    project_path: str | Path = ".",
) -> dict[str, Any] | None:
    return create_snapshot_record(
        file_path,
        feature_name,
        project_path,
        reason=reason,
        ensure_marker=False,
    )


def sync_current_baseline(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    feature_name: str = "dev-baseline",
    reason: str = "Synchronize current development baseline before continuing",
) -> str | None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return None
    if not ensure_index_ready(target, project_root):
        return None

    init_codeguard(project_root, quiet=True)
    suffix = get_storage_suffix(target, project_root)
    baseline_name = f"{target.name}.{suffix}.sync-current.bak"
    baseline_path = project_root / TEMP_DIR / baseline_name
    shutil.copy2(target, baseline_path)
    update_current_state(target, feature_name, project_root, reason=reason, source="sync-current")
    print(f"Current development baseline synchronized: {get_file_key(target, project_root)}")
    print(f"  Baseline backup: {baseline_path.as_posix()}")
    return str(baseline_path)


def get_latest_snapshot(file_path: str | Path, project_path: str | Path = ".") -> dict[str, Any] | None:
    index = load_index(project_path)
    file_key = get_file_key(file_path, project_path)
    versions = index["versions"].get(file_key, [])
    if not versions:
        return None
    return versions[-1]


def check_conflict(file_path: str | Path, project_path: str | Path = ".") -> bool:
    current_state = get_current_state(file_path, project_path)
    expected_hash = None
    file_key = get_file_key(file_path, project_path)
    if current_state is not None:
        expected_hash = current_state.get("hash")
    else:
        latest_snapshot = get_latest_snapshot(file_path, project_path)
        if latest_snapshot is not None:
            expected_hash = latest_snapshot.get("hash")
    if expected_hash is None:
        return False

    current_hash = calculate_hash(resolve_file_path(file_path, project_path))
    if current_hash == expected_hash:
        return False

    print("Conflict detected.")
    print(f"  File key: {file_key}")
    print(f"  Expected hash: {expected_hash[:16]}...")
    print(f"  Current file hash: {current_hash[:16]}...")
    return True


def backup_before_modification(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    auto_sync: bool = True,
) -> str | None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return None
    if not ensure_index_ready(target, project_root):
        return None
    if check_conflict(target, project_root):
        if not auto_sync:
            print("Aborting backup due to conflict.")
            return None
        if sync_current_baseline(target, project_root) is None:
            print("Aborting backup because current baseline sync failed.")
            return None

    init_codeguard(project_root, quiet=True)
    suffix = get_storage_suffix(target, project_root)
    backup_name = f"{target.name}.{suffix}.pre-modification.bak"
    backup_path = project_root / TEMP_DIR / backup_name
    shutil.copy2(target, backup_path)
    print(f"Pre-modification backup created: {backup_path.as_posix()}")
    return str(backup_path)


def find_snapshot(
    file_path: str | Path,
    *,
    version: int | None = None,
    feature: str | None = None,
    project_path: str | Path = ".",
) -> dict[str, Any] | None:
    index = load_index(project_path)
    file_key = get_file_key(file_path, project_path)
    versions = index["versions"].get(file_key, [])
    if not versions:
        return None

    if version is not None:
        for snapshot in versions:
            if snapshot["version"] == version:
                return snapshot
        return None

    if feature is not None:
        for snapshot in reversed(versions):
            if snapshot["feature"] == feature:
                return snapshot
        return None

    return versions[-1]


def rollback(
    file_path: str | Path,
    version: int | None = None,
    feature: str | None = None,
    project_path: str | Path = ".",
    *,
    force: bool = False,
) -> bool:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    snapshot = find_snapshot(target, version=version, feature=feature, project_path=project_root)
    if snapshot is None:
        print("No matching snapshot found.")
        return False

    backup_path = Path(snapshot["backup_path"])
    if not backup_path.exists():
        print(f"Snapshot backup not found: {backup_path.as_posix()}")
        return False

    if not force:
        print(f"Rollback requested for v{snapshot['version']} ({snapshot['feature']}).")
        response = input("Confirm rollback? (y/N): ").strip().lower()
        if response != "y":
            print("Rollback cancelled.")
            return False

    rollback_backup = (
        target.parent
        / f"{target.name}.rollback-backup.{dt.datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    )
    shutil.copy2(target, rollback_backup)
    shutil.copy2(backup_path, target)
    update_current_state(
        target,
        snapshot["feature"],
        project_root,
        reason=snapshot.get("reason"),
        source="rollback",
    )
    print(f"Current file backed up to: {rollback_backup.as_posix()}")
    print(f"Rollback successful: restored v{snapshot['version']} ({snapshot['feature']})")
    return True


def get_temp_backup_path(file_path: str | Path, project_path: str | Path = ".") -> Path:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    suffix = get_storage_suffix(target, project_root)
    return project_root / TEMP_DIR / f"{target.name}.{suffix}.pre-modification.bak"


def write_modification_record(
    file_path: str | Path,
    feature_name: str,
    reason: str,
    project_path: str | Path = ".",
) -> Path:
    project_root = normalize_project_path(project_path)
    records_path = project_root / MODIFICATIONS_FILE
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_hash = calculate_hash(resolve_file_path(file_path, project_root))
    header = f"## Modification Record | {timestamp} | User Confirmed"
    entry = "\n".join(
        [
            header,
            f"- **File**: {get_file_key(file_path, project_root)}",
            f"- **Feature**: {feature_name}",
            f"- **Reason**: {reason}",
            f"- **Hash**: {current_hash}",
            f"- **Path**: {resolve_file_path(file_path, project_root).as_posix()}",
            f"- **Project**: {project_root.as_posix()}",
            "",
            "---",
            "",
        ]
    )
    existing = ""
    if records_path.exists():
        existing = records_path.read_text(encoding="utf-8")
    # Avoid duplicate entries with same header
    if header in existing:
        return records_path
    with records_path.open("a", encoding="utf-8", newline="\n") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(entry)
    return records_path


def confirm_modification(
    file_path: str | Path,
    feature_name: str,
    reason: str,
    success: bool = True,
    project_path: str | Path = ".",
    refresh_index_files: list[str] | None = None,
    *,
    add_marker: bool = False,
) -> bool:
    project_root = normalize_project_path(project_path)
    init_codeguard(project_root, quiet=True)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return False
    if not ensure_index_ready(target, project_root):
        return False

    if not success:
        print("Modification not confirmed by the user. No permanent record created.")
        print("Pre-modification backup remains available for inspection or rollback.")
        return False

    temp_backup = get_temp_backup_path(target, project_root)
    if temp_backup.exists():
        temp_backup.unlink()
        print(f"Temporary backup removed: {temp_backup.as_posix()}")

    if add_marker:
        if apply_confirm_policy_note(target, reason):
            print("Post-confirm modification policy note updated in file header.")
        else:
            print("Warning: could not update header policy note (CodeGuard marker missing or unsupported format).")
    else:
        print("Marker injection skipped (use --add-marker to inject CodeGuard header).")

    update_current_state(target, feature_name, project_root, reason=reason, source="confirm")
    record_path = write_modification_record(target, feature_name, reason, project_root)
    auto_snapshot_reason = f"Auto snapshot after confirm: {reason}"
    snapshot = create_manual_snapshot(target, feature_name, auto_snapshot_reason, project_root)
    if snapshot is None:
        print("Failed to create auto snapshot after confirm.")
        return False

    if refresh_index_files is not None:
        refresh_targets = [target.as_posix()]
        refresh_targets.extend(refresh_index_files)
        if not refresh_feature_indexes(refresh_targets, project_root):
            print("Failed to refresh feature indexes after confirm.")
            return False
        print("Feature indexes refreshed after confirm.")

    print("User-confirmed modification recorded.")
    print("Auto snapshot created after confirm.")
    print(f"Modification record: {record_path.as_posix()}")
    return True


def file_has_protection_marker(file_path: str | Path, project_path: str | Path = ".") -> bool:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        return False
    content = read_text(target)
    return has_codeguard_marker(content) or has_protection_marker(content)


def gather_file_status(file_path: str | Path, project_path: str | Path = ".") -> dict[str, Any] | None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        return None

    file_key = get_file_key(target, project_root)
    index = load_index(project_root)
    versions = index["versions"].get(file_key, [])
    current_state = index["current_state"].get(file_key)
    protected_features = index["protected_features"].get(file_key, [])
    entries = get_feature_index(target, project_root)
    index_required = is_index_required(target, project_root)
    index_valid = validate_feature_index(target, project_root, quiet=True)
    index_state = index["index_state"].get(file_key)
    mode = get_index_mode(target)

    latest_snapshot = versions[-1] if versions else None
    rollback_ready = latest_snapshot is not None and Path(latest_snapshot.get("backup_path", "")).exists()
    stale_index = False
    if index_state is not None:
        stale_index = bool(index_state.get("file_hash")) and index_state.get("file_hash") != calculate_hash(target)
    missing_index = bool(index_required and (not index_valid or len(entries) == 0))

    orphan_count = 0
    for snapshot in versions:
        if not Path(snapshot.get("backup_path", "")).exists():
            orphan_count += 1

    return {
        "file_key": file_key,
        "path": target.as_posix(),
        "protection_marker": file_has_protection_marker(target, project_root),
        "protected_features": protected_features,
        "snapshots": len(versions),
        "latest_snapshot": latest_snapshot,
        "current_state": current_state,
        "index_required": index_required,
        "index_valid": index_valid,
        "index_entries": len(entries),
        "index_mode": mode,
        "index_format": describe_index_format(target, project_root),
        "index_stale": stale_index,
        "index_missing": missing_index,
        "index_summary": {
            "required": index_required,
            "missing": missing_index,
            "stale": stale_index,
            "action_required": missing_index or stale_index,
        },
        "index_state": index_state,
        "rollback_ready": rollback_ready,
        "orphan_snapshots": orphan_count,
    }


def refresh_feature_indexes(file_paths: list[str], project_path: str | Path = ".") -> bool:
    project_root = normalize_project_path(project_path)
    unique_paths: list[str] = []
    seen: set[str] = set()
    for file_path in file_paths:
        file_text = str(file_path).strip()
        if not file_text:
            continue
        if file_text in seen:
            continue
        seen.add(file_text)
        unique_paths.append(file_text)

    if not unique_paths:
        return True

    all_ok = True
    for file_path in unique_paths:
        target = resolve_file_path(file_path, project_root)
        if not target.exists():
            print(f"Refresh index skipped (file not found): {target.as_posix()}")
            all_ok = False
            continue

        status = gather_file_status(target, project_root)
        if status is None:
            print(f"Refresh index skipped (status unavailable): {target.as_posix()}")
            all_ok = False
            continue

        if not status.get("index_required", False):
            print(f"Refresh index skipped (not required): {status['file_key']}")
            continue

        needs_refresh = bool(
            status.get("index_stale", False)
            or status.get("index_missing", False)
            or not status.get("index_valid", False)
        )
        if not needs_refresh:
            print(f"Refresh index skipped (up-to-date): {status['file_key']}")
            continue

        try:
            entries = generate_feature_index_entries(target, project_root)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Refresh index failed for {get_file_key(target, project_root)}: {exc}")
            all_ok = False
            continue

        applied = apply_feature_index(target, entries, project_root, quiet=True)
        if applied is None:
            print(f"Refresh index failed for {get_file_key(target, project_root)}")
            all_ok = False
            continue
        print(f"Refresh index updated: {get_file_key(target, project_root)} ({len(applied)} entries)")
    return all_ok


def show_status(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    json_output: bool = False,
    json_compact: bool = False,
) -> bool:
    status = gather_file_status(file_path, project_path)
    if status is None:
        target = resolve_file_path(file_path, project_path)
        if json_output:
            emit_json(
                build_json_payload(
                    "status",
                    {
                        "file": get_file_key(target, project_path),
                        "ok": False,
                        "error": f"File not found: {target.as_posix()}",
                    },
                ),
                compact=json_compact,
            )
        else:
            print(f"File not found: {target.as_posix()}")
        return False

    if json_output:
        payload = dict(status)
        payload["ok"] = True
        emit_json(build_json_payload("status", payload), compact=json_compact)
        return True

    print(f"CodeGuard status for: {status['file_key']}")
    print(f"  Protection marker: {'yes' if status['protection_marker'] else 'no'}")
    print(f"  Protected features: {', '.join(status['protected_features']) if status['protected_features'] else 'none'}")
    print(f"  Snapshots: {status['snapshots']}")
    print(f"  Rollback ready: {'yes' if status['rollback_ready'] else 'no'}")
    print(f"  Orphan snapshots: {status['orphan_snapshots']}")

    latest = status["latest_snapshot"]
    if latest is None:
        print("  Latest snapshot: none")
    else:
        print(f"  Latest snapshot: v{latest['version']} ({latest['feature']}) at {latest['timestamp']}")

    current = status["current_state"]
    if current is None:
        print("  Accepted current state: none")
    else:
        print(
            "  Accepted current state: "
            f"{current.get('source', 'unknown')} / {current.get('feature', 'unknown')} / "
            f"{current.get('timestamp', 'unknown')}"
        )

    print(f"  Feature index required: {'yes' if status['index_required'] else 'no'}")
    print(f"  Feature index mode: {status['index_mode']}")
    print(f"  Feature index entries: {status['index_entries']}")
    print(f"  Feature index valid: {'yes' if status['index_valid'] else 'no'}")
    print(f"  Feature index stale: {'yes' if status['index_stale'] else 'no'}")

    if status["index_mode"] == "sidecar":
        print(f"  Sidecar: {get_sidecar_index_path(file_path, project_path).as_posix()}")

    return True


def build_doctor_report(project_path: str | Path = ".", *, repair: bool = False) -> dict[str, Any]:
    project_root = normalize_project_path(project_path)
    init_codeguard(project_root, quiet=True)

    raw_index_path = project_root / INDEX_FILE
    try:
        raw_index = read_json(raw_index_path)
        raw_last_version = raw_index.get("last_version", {}) if isinstance(raw_index, dict) else {}
    except json.JSONDecodeError:
        raw_last_version = {}

    index = load_index(project_root, repair=repair)

    errors: list[str] = []
    warnings: list[str] = []

    file_keys = set(index["versions"].keys())
    file_keys.update(index["current_state"].keys())
    file_keys.update(index["protected_features"].keys())

    for file_key in sorted(file_keys):
        versions = index["versions"].get(file_key, [])
        protected = index["protected_features"].get(file_key, [])
        if protected and not versions:
            errors.append(f"{file_key}: protected_features exists but versions are empty")

        max_version = 0
        for snapshot in versions:
            try:
                snapshot_version = int(snapshot.get("version", 0))
            except (TypeError, ValueError):
                snapshot_version = 0
                errors.append(f"{file_key}: snapshot has invalid version value")
            max_version = max(max_version, snapshot_version)
            backup_path = Path(snapshot.get("backup_path", ""))
            if not backup_path.exists():
                errors.append(f"{file_key}: snapshot v{snapshot.get('version')} missing backup file")

        raw_last = raw_last_version.get(file_key, index["last_version"].get(file_key, 0))
        if raw_last != max_version:
            warnings.append(f"{file_key}: last_version mismatch (expected {max_version}, actual {raw_last})")
            if repair:
                index["last_version"][file_key] = max_version

        target = resolve_file_path(file_key, project_root)
        if target.exists():
            if is_index_required(target, project_root) and not validate_feature_index(target, project_root, quiet=True):
                errors.append(f"{file_key}: feature index required but invalid")
            state = index["current_state"].get(file_key)
            if state and state.get("hash") and calculate_hash(target) != state.get("hash"):
                warnings.append(f"{file_key}: accepted current state hash differs from current file")

    versions_dir = project_root / VERSIONS_DIR
    known_backups = {
        Path(snapshot.get("backup_path", "")).resolve().as_posix()
        for snapshots in index["versions"].values()
        for snapshot in snapshots
        if snapshot.get("backup_path")
    }
    orphan_files = []
    if versions_dir.exists():
        for backup in versions_dir.glob("*.bak"):
            if backup.resolve().as_posix() not in known_backups:
                orphan_files.append(backup.as_posix())

    for orphan in orphan_files:
        warnings.append(f"orphan snapshot file: {orphan}")

    if repair:
        save_index(project_root, index)

    return {
        "project": project_root.as_posix(),
        "repair_mode": repair,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "healthy": len(errors) == 0,
    }


def run_doctor(
    project_path: str | Path = ".",
    *,
    repair: bool = False,
    json_output: bool = False,
    json_compact: bool = False,
) -> bool:
    report = build_doctor_report(project_path, repair=repair)

    if json_output:
        emit_json(build_json_payload("doctor", report), compact=json_compact)
        return report["healthy"]

    print("CodeGuard doctor report")
    print(f"  Project: {report['project']}")
    print(f"  Errors: {report['error_count']}")
    print(f"  Warnings: {report['warning_count']}")
    for item in report["errors"]:
        print(f"  Error: {item}")
    for item in report["warnings"]:
        print(f"  Warning: {item}")

    if not report["errors"] and not report["warnings"]:
        print("  Healthy: no issues found")

    return report["healthy"]


def batch_run(
    action: str,
    files: list[str],
    project_path: str | Path = ".",
    *,
    auto_index: bool = False,
    fail_fast: bool = False,
    json_output: bool = False,
    json_compact: bool = False,
) -> bool:
    all_ok = True
    results: list[dict[str, Any]] = []

    for item in files:
        file_result: dict[str, Any] = {"file": item, "action": action, "ok": False}
        if action == "validate-index":
            ok = validate_feature_index(item, project_path)
            file_result["ok"] = ok
        elif action == "backup":
            backup_path = backup_before_modification(item, project_path)
            ok = backup_path is not None
            file_result["ok"] = ok
            file_result["backup_path"] = backup_path
        elif action == "status":
            status_payload = gather_file_status(item, project_path)
            ok = status_payload is not None
            file_result["ok"] = ok
            if status_payload is None:
                target = resolve_file_path(item, project_path)
                file_result["error"] = f"File not found: {target.as_posix()}"
            else:
                file_result["status"] = status_payload
        elif action == "index":
            if not auto_index:
                ok = False
                file_result["ok"] = ok
                file_result["error"] = (
                    "Batch index requires --auto to avoid reusing static entries across files."
                )
            else:
                try:
                    _, reviewed_lines, reviewed_hash = review_full_document_for_index(item, project_path)
                    entries = generate_feature_index_entries(item, project_path)
                except (FileNotFoundError, ValueError) as exc:
                    ok = False
                    file_result["ok"] = ok
                    file_result["error"] = str(exc)
                else:
                    applied = apply_feature_index(item, entries, project_path, quiet=json_output)
                    ok = applied is not None
                    file_result["ok"] = ok
                    file_result["entries"] = entries
                    file_result["reviewed_line_count"] = len(reviewed_lines)
                    file_result["reviewed_hash"] = reviewed_hash
        else:
            if json_output:
                emit_json(
                    build_json_payload(
                        "batch",
                        {
                            "action": action,
                            "ok": False,
                            "error": f"Unsupported batch action: {action}",
                            "results": [],
                        },
                    ),
                    compact=json_compact,
                )
            else:
                print(f"Unsupported batch action: {action}")
            return False

        all_ok = all_ok and ok
        results.append(file_result)

        if not json_output:
            print("=" * 72)
            print(f"File: {item}")
            if action == "status":
                if ok:
                    status = file_result["status"]
                    print(f"  Protection marker: {'yes' if status['protection_marker'] else 'no'}")
                    print(f"  Snapshots: {status['snapshots']}")
                    print(f"  Feature index valid: {'yes' if status['index_valid'] else 'no'}")
                else:
                    print(f"  Error: {file_result.get('error', 'unknown error')}")
            elif action == "backup":
                if ok:
                    print(f"  Backup: {backup_path}")
                else:
                    print("  Backup failed")
            elif action == "index":
                if ok:
                    print(f"  Auto index entries: {len(file_result.get('entries', []))}")
                    print(
                        f"  Full-document review: {file_result.get('reviewed_line_count', 0)} lines "
                        f"(hash {file_result.get('reviewed_hash', 'n/a')})"
                    )
                else:
                    print(f"  Error: {file_result.get('error', 'index generation failed')}")
            else:
                print(f"  Validate index: {'ok' if ok else 'failed'}")

        if fail_fast and not ok:
            break

    if json_output:
        stopped_early = fail_fast and len(results) < len(files)
        emit_json(
            build_json_payload(
                "batch",
                {
                    "action": action,
                    "ok": all_ok,
                    "fail_fast": fail_fast,
                    "stopped_early": stopped_early,
                    "result_count": len(results),
                    "results": results,
                },
            ),
            compact=json_compact,
        )

    return all_ok


def list_versions(file_path: str | Path, project_path: str | Path = ".") -> list[dict[str, Any]]:
    index = load_index(project_path)
    file_key = get_file_key(file_path, project_path)
    versions = index["versions"].get(file_key, [])
    if not versions:
        print("No snapshot history found.")
        return []

    print(f"Snapshot history for: {file_key}")
    print("-" * 96)
    print(f"{'Version':<10}{'Feature':<24}{'Timestamp':<24}{'Hash':<18}{'Backup':<18}")
    print("-" * 96)
    for snapshot in versions:
        backup_exists = Path(snapshot.get("backup_path", "")).exists()
        backup_flag = "ok" if backup_exists else "missing"
        print(
            f"v{snapshot['version']:<9}"
            f"{snapshot['feature'][:23]:<24}"
            f"{snapshot['timestamp']:<24}"
            f"{snapshot['hash'][:16]:<18}"
            f"{backup_flag:<18}"
        )
    print("-" * 96)

    current_state = index["current_state"].get(file_key)
    if current_state is not None:
        print(
            "Accepted state: "
            f"{current_state.get('source', 'unknown')} / {current_state.get('feature', 'unknown')} / "
            f"{current_state.get('timestamp', 'unknown')}"
        )
    else:
        print("Accepted state: none")

    return versions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeguard",
        description="Project-local feature indexing, confirmation, and snapshot workflow for CodeGuard.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument(
        "--project",
        default=".",
        help="Project root that stores the .codeguard directory. Defaults to the current directory.",
    )
    subparsers = parser.add_subparsers(dest="command")

    def add_lock_timeout_argument(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--lock-timeout",
            type=float,
            default=DEFAULT_LOCK_TIMEOUT_SECONDS,
            help=f"Lock wait timeout in seconds (default: {DEFAULT_LOCK_TIMEOUT_SECONDS}).",
        )

    init_parser = subparsers.add_parser("init", help="Initialize CodeGuard in a project.")
    init_parser.add_argument("path", nargs="?", default=None)

    add_parser = subparsers.add_parser(
        "add",
        help="Add or refresh a protection marker and create an initial important snapshot.",
    )
    add_parser.add_argument("file")
    add_parser.add_argument("feature")
    add_parser.add_argument("--no-marker", action="store_true", help="Skip injecting a marker into the source file.")
    add_lock_timeout_argument(add_parser)

    index_parser = subparsers.add_parser(
        "index",
        help='Create or update a feature index. Use --auto or repeated --entry "Feature description:LineNumber".',
    )
    index_parser.add_argument("file")
    index_parser.add_argument("--entry", action="append")
    index_parser.add_argument("--auto", action="store_true", help="Auto-generate entries from file content.")
    add_lock_timeout_argument(index_parser)

    show_index_parser = subparsers.add_parser("show-index", help="Show the current feature index.")
    show_index_parser.add_argument("file")
    add_lock_timeout_argument(show_index_parser)

    validate_index_parser = subparsers.add_parser(
        "validate-index",
        help="Validate the current feature index and the over-200-lines rule.",
    )
    validate_index_parser.add_argument("file")
    validate_index_parser.add_argument("--max-lines", type=int, default=DEFAULT_INDEX_THRESHOLD)
    add_lock_timeout_argument(validate_index_parser)

    backup_parser = subparsers.add_parser("backup", help="Create a pre-modification backup.")
    backup_parser.add_argument("file")
    backup_parser.add_argument(
        "--strict-conflict",
        action="store_true",
        help="Fail on hash drift instead of syncing the current development baseline.",
    )
    add_lock_timeout_argument(backup_parser)

    sync_parser = subparsers.add_parser(
        "sync-current",
        help="Record the current file hash as a development baseline without user success confirmation.",
    )
    sync_parser.add_argument("file")
    sync_parser.add_argument("--feature", default="dev-baseline")
    sync_parser.add_argument(
        "--reason",
        default="Synchronize current development baseline before continuing",
    )
    add_lock_timeout_argument(sync_parser)

    confirm_parser = subparsers.add_parser(
        "confirm",
        help="Record a user-confirmed successful modification and create an auto snapshot.",
    )
    confirm_parser.add_argument("file")
    confirm_parser.add_argument("feature")
    confirm_parser.add_argument("reason")
    confirm_parser.add_argument("success", nargs="?", default="true")
    confirm_parser.add_argument(
        "--add-marker",
        action="store_true",
        help="Inject a CodeGuard protection marker into the source file header (opt-in).",
    )
    confirm_parser.add_argument(
        "--refresh-index",
        nargs="*",
        metavar="FILE",
        help="Refresh feature indexes after confirm. If FILE is omitted, refreshes the confirmed file.",
    )
    add_lock_timeout_argument(confirm_parser)

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Manually mark the current file state as an important version and store a snapshot.",
    )
    snapshot_parser.add_argument("file")
    snapshot_parser.add_argument("feature")
    snapshot_parser.add_argument("reason")
    add_lock_timeout_argument(snapshot_parser)

    rollback_parser = subparsers.add_parser("rollback", help="Restore a previous snapshot.")
    rollback_parser.add_argument("file")
    selector = rollback_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--version", type=int)
    selector.add_argument("--feature")
    rollback_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    add_lock_timeout_argument(rollback_parser)

    list_parser = subparsers.add_parser("list", help="List important snapshots for a file.")
    list_parser.add_argument("file")
    add_lock_timeout_argument(list_parser)

    status_parser = subparsers.add_parser(
        "status",
        help="Show protection, accepted state, index health, and rollback readiness.",
    )
    status_parser.add_argument("file")
    status_parser.add_argument("--json", action="store_true", help="Emit status as JSON.")
    status_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")
    add_lock_timeout_argument(status_parser)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Scan CodeGuard metadata consistency and snapshot/index health.",
    )
    doctor_parser.add_argument("--repair", action="store_true", help="Repair safe metadata mismatches.")
    doctor_parser.add_argument("--json", action="store_true", help="Emit doctor report as JSON.")
    doctor_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")
    add_lock_timeout_argument(doctor_parser)

    batch_parser = subparsers.add_parser(
        "batch",
        help="Run validate-index, backup, status, or index in batch mode.",
    )
    batch_parser.add_argument("action", choices=["validate-index", "backup", "status", "index"])
    batch_parser.add_argument("files", nargs="+")
    batch_parser.add_argument("--auto", action="store_true", help="Required for batch index generation.")
    batch_parser.add_argument("--fail-fast", action="store_true", help="Stop batch execution on first failure.")
    batch_parser.add_argument("--json", action="store_true", help="Emit batch result as JSON.")
    batch_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")
    add_lock_timeout_argument(batch_parser)

    lock_status_parser = subparsers.add_parser(
        "lock-status",
        help="Show lock file diagnostics, occupancy, and actionable next steps.",
    )
    lock_status_parser.add_argument("--json", action="store_true", help="Emit lock status as JSON.")
    lock_status_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")

    unlock_parser = subparsers.add_parser(
        "unlock",
        help="Clean stale lock file with explicit authorization controls.",
    )
    unlock_parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation.")
    unlock_parser.add_argument(
        "--force",
        action="store_true",
        help="Attempt cleanup even when lock is currently occupied (requires --yes).",
    )

    token_tips_parser = subparsers.add_parser(
        "token-tips",
        help="Show actionable token-saving guidance and project-specific diagnostics.",
    )
    token_tips_parser.add_argument("--json", action="store_true", help="Emit tips as JSON.")
    token_tips_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")

    compress_parser = subparsers.add_parser(
        "compress",
        help="Compress prose in markdown/text files while keeping code blocks intact (caveman-style).",
    )
    compress_parser.add_argument("file")
    compress_parser.add_argument(
        "--level",
        default="full",
        choices=["lite", "full", "ultra"],
        help="Compression level: lite (edges only), full (default, drop filler/hedging/articles), ultra (max compression).",
    )
    compress_parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write compressed content back to file (creates backup first). Without this, prints preview to stdout.",
    )
    compress_parser.add_argument("--json", action="store_true", help="Emit result as JSON.")
    compress_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")
    add_lock_timeout_argument(compress_parser)

    guard_parser = subparsers.add_parser(
        "guard",
        help="Unified pre-edit guard: detect encoding, backup, and return tx info in one step.",
    )
    guard_parser.add_argument("file")
    guard_parser.add_argument("--feature", default="edit", help="Feature name for this change.")
    guard_parser.add_argument("--reason", default="", help="Reason for this change.")
    guard_parser.add_argument(
        "--tier",
        default="standard",
        choices=["lite", "standard", "strict"],
        help="Risk tier (default: standard). Strict also creates a snapshot.",
    )
    guard_parser.add_argument("--json", action="store_true", help="Emit guard result as JSON.")
    guard_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")
    add_lock_timeout_argument(guard_parser)

    schema_parser = subparsers.add_parser(
        "schema",
        help="Show stable JSON schema metadata for status/doctor/batch reports.",
    )
    schema_parser.add_argument(
        "target",
        nargs="?",
        default="all",
        choices=["all", "status", "doctor", "batch"],
    )
    schema_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")

    return parser


def parse_success(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Unsupported success value: {value}")


# ---------------------------------------------------------------------------
# Token compression (Caveman-style)
# ---------------------------------------------------------------------------

FILLER_WORDS = {
    "just", "really", "basically", "actually", "simply", "very", "quite",
    "rather", "pretty", "somewhat", "kind of", "sort of", "a bit", "a little",
    "in order to", "due to the fact that", "it is important to note that",
    "please note that", "it should be noted that", "as a matter of fact",
}

HEDGING_PATTERNS = [
    (re.compile(r"\b(maybe|perhaps|possibly|potentially)\b\s*", re.IGNORECASE), ""),
    (re.compile(r"\b(I think|I believe|it seems like|it appears that)\b\s*", re.IGNORECASE), ""),
    (re.compile(r"\b(in my opinion|from my perspective)\b\s*", re.IGNORECASE), ""),
]

PLEASANTRIES = {
    "sure", "certainly", "of course", "absolutely", "definitely",
    "happy to", "glad to", "no problem", "you're welcome",
}

PHRASE_SHORTEN: list[tuple[str, str]] = [
    ("for example", "e.g."),
    ("that is", "i.e."),
    ("and so on", "etc."),
    ("in other words", "i.e."),
    ("as well as", "and"),
    ("a number of", "many"),
    ("the majority of", "most"),
    ("in the event that", "if"),
    ("on a regular basis", "regularly"),
    ("at this point in time", "now"),
    ("in the near future", "soon"),
    ("prior to", "before"),
    ("subsequent to", "after"),
    ("in addition to", "besides"),
    ("with regard to", "about"),
    ("with the exception of", "except"),
    ("a lot of", "many"),
    ("each and every", "each"),
    ("first and foremost", "first"),
    ("last but not least", "finally"),
    ("in spite of", "despite"),
    ("in the process of", "while"),
    ("on the part of", "by"),
    ("until such time as", "until"),
    ("in close proximity to", "near"),
    ("be able to", "can"),
    ("is required to", "must"),
    ("has the ability to", "can"),
    ("make a decision", "decide"),
    ("take action", "act"),
    ("conduct an analysis", "analyze"),
    ("give consideration to", "consider"),
    ("provide assistance", "help"),
    ("make use of", "use"),
    ("take into account", "consider"),
    ("carry out", "do"),
    ("in a timely manner", "quickly"),
]


def _is_code_fence(line: str) -> bool:
    return line.strip().startswith("```")


def _compress_prose_line(line: str, level: str) -> str:
    """Compress a single prose line. Code lines are returned verbatim."""
    stripped = line.strip()

    # Never touch code fences, indented code, or HTML comments
    if _is_code_fence(stripped) or stripped.startswith("    ") or stripped.startswith("\t"):
        return line
    if stripped.startswith("<!--") or stripped.startswith("-->"):
        return line

    result = stripped

    if level in ("full", "ultra"):
        # Drop filler words (word boundary match)
        for word in sorted(FILLER_WORDS, key=len, reverse=True):
            pattern = re.compile(r"\b" + re.escape(word) + r"\b\s*", re.IGNORECASE)
            result = pattern.sub("", result)

        # Drop hedging phrases
        for pattern, replacement in HEDGING_PATTERNS:
            result = pattern.sub(replacement, result)

        # Drop pleasantries at sentence start
        for word in sorted(PLEASANTRIES, key=len, reverse=True):
            pattern = re.compile(r"^" + re.escape(word) + r"[,\s]*", re.IGNORECASE)
            result = pattern.sub("", result)

        # Shorten common phrases
        for long_phrase, short_phrase in PHRASE_SHORTEN:
            pattern = re.compile(re.escape(long_phrase), re.IGNORECASE)
            result = pattern.sub(short_phrase, result)

    if level == "ultra":
        # Drop articles
        result = re.sub(r"\b(a|an|the)\b\s*", "", result, flags=re.IGNORECASE)
        # Drop "is/are/was/were" before adjectives
        result = re.sub(r"\b(is|are|was|were)\s+(a\s+)?(\w+ing)\b", r"\3", result, flags=re.IGNORECASE)
        # Merge multiple spaces
        result = re.sub(r"\s{2,}", " ", result)
        # Use arrows for causality
        result = re.sub(r",?\s*(so|therefore|thus|hence|as a result)\s*,?\s*", " -> ", result, flags=re.IGNORECASE)

    # Lite: just drop filler and pleasantries at edges
    if level == "lite":
        result = re.sub(r"^(just|really|basically|actually|simply|sure|certainly|of course)\s*,?\s*", "", result, flags=re.IGNORECASE)
        result = re.sub(r"^(please|kindly)\s+", "", result, flags=re.IGNORECASE)

    # Clean up
    result = re.sub(r"\s{2,}", " ", result).strip()
    # Capitalize first letter
    if result and result[0].islower():
        result = result[0].upper() + result[1:]

    return result


def compress_text(content: str, level: str = "full") -> tuple[str, dict[str, Any]]:
    """Compress prose while keeping code blocks intact.

    Levels:
      lite   - Drop filler/pleasantries at sentence edges
      full   - Drop articles, filler, hedging, shorten phrases
      ultra  - Full + articles, be-verbs, arrows for causality
    """
    if level not in ("lite", "full", "ultra"):
        raise ValueError(f"Unknown compression level: {level}")

    lines = content.split("\n")
    in_code_block = False
    compressed: list[str] = []
    stats = {"original_chars": len(content), "compressed_chars": 0, "lines_in": len(lines), "lines_out": 0}

    for line in lines:
        if _is_code_fence(line):
            in_code_block = not in_code_block
            compressed.append(line)
            continue

        if in_code_block or line.startswith("    ") or line.startswith("\t"):
            compressed.append(line)
            continue

        # Skip blank lines but don't remove more than 1 consecutive
        stripped = line.strip()
        if not stripped:
            if compressed and compressed[-1].strip():
                compressed.append("")
            continue

        compressed_line = _compress_prose_line(line, level)
        if compressed_line:
            compressed.append(compressed_line)

    # Remove trailing blank lines
    while compressed and not compressed[-1].strip():
        compressed.pop()

    result = "\n".join(compressed)
    stats["compressed_chars"] = len(result)
    stats["lines_out"] = len(compressed)
    stats["reduction_pct"] = round(
        (1 - stats["compressed_chars"] / max(stats["original_chars"], 1)) * 100, 1
    )
    return result, stats


# File extensions safe for prose compression
PROSE_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc", ".asciidoc", ".tex", ".text"}


def _check_compress_safe(target: Path) -> str | None:
    """Return error message if target is not safe for compression, else None."""
    ext = target.suffix.lower()
    if ext not in PROSE_EXTENSIONS:
        return (
            f"Compress only supports prose files ({', '.join(sorted(PROSE_EXTENSIONS))}). "
            f"'{ext}' files cannot be compressed — code and structured data would be corrupted."
        )
    return None


def run_compress(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    level: str = "full",
    in_place: bool = False,
    json_output: bool = False,
    json_compact: bool = False,
) -> int:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        if json_output:
            emit_json(build_json_payload("compress", {"ok": False, "error": f"File not found: {target.as_posix()}"}), compact=json_compact)
        else:
            print(f"File not found: {target.as_posix()}")
        return 1

    # Safety check: refuse code/structured files
    error = _check_compress_safe(target)
    if error is not None:
        if json_output:
            emit_json(build_json_payload("compress", {"ok": False, "error": error}), compact=json_compact)
        else:
            print(f"Error: {error}")
        return 1

    # Check for CodeGuard inline markers that would be corrupted
    content, encoding_meta = read_text_preserving(target)
    if in_place and has_codeguard_marker(content):
        print("Warning: File contains CodeGuard protection markers that may be altered by compression.")
        print("  Use 'guard' before compress for a proper backup, or remove markers first.")
        if not json_output:
            answer = input("Continue anyway? (y/N): ").strip().lower()
            if answer != "y":
                print("Compression cancelled.")
                return 1

    # Check for feature index that would become stale
    if in_place and is_index_required(target, project_root):
        print("Warning: File has a feature index. Compression changes line counts; re-index after compression.")
        print("  Run 'python scripts/codeguard.py index <file> --auto' after compress to refresh.")

    compressed, stats = compress_text(content, level=level)
    stats["file"] = get_file_key(target, project_root)
    stats["level"] = level
    stats["encoding"] = encoding_meta

    if in_place:
        # Use guard pipeline for proper backup
        init_codeguard(project_root, quiet=True)
        suffix = get_storage_suffix(target, project_root)
        backup_name = f"{target.name}.{suffix}.pre-compress.bak"
        backup_path = project_root / TEMP_DIR / backup_name
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
        # Also save encoding metadata alongside backup (guard-style)
        encoding_meta_path = Path(str(backup_path) + ".encoding.json")
        write_json(encoding_meta_path, encoding_meta)
        update_current_state(target, f"compress-{level}", project_root, reason="Pre-compress baseline", source="compress")
        stats["backup_path"] = backup_path.as_posix()

        write_text_preserving(target, compressed, encoding_meta)
        stats["ok"] = True

        if json_output:
            emit_json(build_json_payload("compress", stats), compact=json_compact)
        else:
            print(f"Compressed: {stats['file']} (level={level})")
            print(f"  {stats['original_chars']} -> {stats['compressed_chars']} chars ({stats['reduction_pct']}% reduction)")
            print(f"  Backup: {backup_path.as_posix()}")
        return 0
    else:
        # Preview mode: print to stdout
        if json_output:
            emit_json(build_json_payload("compress", {**stats, "preview": compressed[:500]}), compact=json_compact)
        else:
            print(compressed)
            print(f"\n--- Compression stats: {stats['original_chars']} -> {stats['compressed_chars']} chars ({stats['reduction_pct']}% reduction) ---", file=sys.stderr)
        return 0


def run_guard(
    file_path: str | Path,
    project_path: str | Path = ".",
    *,
    feature: str = "edit",
    reason: str = "",
    tier: str = "standard",
    json_output: bool = False,
    json_compact: bool = False,
) -> int:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        if json_output:
            emit_json(build_json_payload("guard", {"ok": False, "error": f"File not found: {target.as_posix()}"}), compact=json_compact)
        else:
            print(f"File not found: {target.as_posix()}")
        return 1

    init_codeguard(project_root, quiet=True)

    # Detect encoding
    _, encoding_meta = read_text_preserving(target)

    # Create pre-modification backup (always, silently)
    suffix = get_storage_suffix(target, project_root)
    backup_name = f"{target.name}.{suffix}.pre-modification.bak"
    backup_path = project_root / TEMP_DIR / backup_name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup_path)

    # Save encoding metadata alongside backup
    encoding_meta_path = Path(str(backup_path) + ".encoding.json")
    write_json(encoding_meta_path, encoding_meta)

    # Generate a simple tx id
    tx_id = hashlib.sha256(
        f"{get_file_key(target, project_root)}:{dt.datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    pre_hash = calculate_hash(target)
    line_count = count_code_lines(target, project_root)

    # For strict tier, also create a milestone snapshot
    snapshot_info = None
    if tier == "strict":
        snapshot_info = create_manual_snapshot(target, feature, reason or f"Guard strict snapshot for {feature}", project_root)

    # Update current state to track this operation
    update_current_state(target, feature, project_root, reason=reason, source="guard")

    guard_result = {
        "ok": True,
        "tx_id": tx_id,
        "file": get_file_key(target, project_root),
        "pre_hash": pre_hash,
        "line_count": line_count,
        "encoding": encoding_meta,
        "backup_path": backup_path.as_posix(),
        "tier": tier,
        "feature": feature,
        "reason": reason,
        "snapshot_created": snapshot_info is not None,
    }

    if json_output:
        emit_json(build_json_payload("guard", guard_result), compact=json_compact)
    else:
        print(f"Guard: {get_file_key(target, project_root)}")
        print(f"  tx_id: {tx_id}")
        print(f"  tier: {tier}")
        print(f"  backup: {backup_path.as_posix()}")
        print(f"  encoding: {encoding_meta['encoding']}{' BOM' if encoding_meta.get('bom') else ''}")
        if snapshot_info:
            print(f"  snapshot: v{snapshot_info['version']}")
    return 0


# ---------------------------------------------------------------------------
# Token diagnostics
# ---------------------------------------------------------------------------

TOKEN_TIPS = [
    {
        "id": 1,
        "title": "Don't follow up to correct — restart",
        "detail": "When Claude makes a mistake, use /clear + re-prompt instead of adding correction turns. Each turn re-reads full history.",
        "action": "/clear",
    },
    {
        "id": 2,
        "title": "Fresh chat every 15-20 turns",
        "detail": "Long conversations burn tokens re-reading history. Use /compact or /clear + paste a summary from the previous session.",
        "action": "/compact or /clear",
    },
    {
        "id": 3,
        "title": "Batch questions into one message",
        "detail": "Combine related asks into a single message instead of multiple back-and-forth turns.",
        "action": "Combine questions",
    },
    {
        "id": 4,
        "title": "Track actual token usage",
        "detail": "Use /context to see current token consumption. Check which files and tools burn the most tokens.",
        "action": "/context",
    },
    {
        "id": 5,
        "title": "Reuse recurring context",
        "detail": "Use CLAUDE.md, skills, and .codeguard/ feature indexes to avoid re-reading entire files. CodeGuard indexes cut read windows from full-file to ~40 lines.",
        "action": "Use CLAUDE.md + codeguard indexes",
    },
    {
        "id": 6,
        "title": "Use feature indexes for large files",
        "detail": "Files over 200 lines with a CodeGuard feature index enable targeted ~40-line reads instead of full-file reads. Run 'codeguard index <file> --auto' on large files.",
        "action": "python scripts/codeguard.py index <file> --auto",
    },
    {
        "id": 7,
        "title": "Compress verbose instruction files",
        "detail": "Use 'codeguard compress --in-place' on CLAUDE.md and AGENTS.md to reduce per-session token burn. The compress command preserves code blocks and technical terms.",
        "action": "python scripts/codeguard.py compress CLAUDE.md --level full --in-place",
    },
    {
        "id": 8,
        "title": "Guard creates targeted backups, not full copies",
        "detail": "The guard command stores backups in .codeguard/temp/ which are excluded from context. Use guard instead of reading full files for safety.",
        "action": "python scripts/codeguard.py guard <file>",
    },
    {
        "id": 9,
        "title": "Spread work across sessions",
        "detail": "Split large tasks into 2-3 sessions to stay under token thresholds. The 5-hour rolling window resets between sessions.",
        "action": "Plan task boundaries",
    },
    {
        "id": 10,
        "title": "Use Haiku for simple tasks",
        "detail": "Switch to Haiku for typo fixes, simple refactors, and low-risk changes. Reserve Opus/Sonnet for complex architecture work.",
        "action": "/model claude-haiku-4-5",
    },
    {
        "id": 11,
        "title": "Disable unused MCP tools and hooks",
        "detail": "Each MCP tool definition burns tokens before your first keystroke. Disable unused integrations in settings.json.",
        "action": "Check settings.json",
    },
]


def run_token_tips(
    project_path: str | Path = ".",
    *,
    json_output: bool = False,
    json_compact: bool = False,
) -> int:
    project_root = normalize_project_path(project_path)
    init_codeguard(project_root, quiet=True)

    # Gather project-specific diagnostics
    index = load_index(project_root)
    indexed_files = len(index.get("index_state", {}))
    snapshot_files = len(index.get("versions", {}))
    total_snapshots = sum(len(v) for v in index.get("versions", {}).values())
    has_modifications = (project_root / MODIFICATIONS_FILE).exists()

    diagnostics = {
        "indexed_files": indexed_files,
        "snapshot_files": snapshot_files,
        "total_snapshots": total_snapshots,
        "has_modification_records": has_modifications,
    }

    if json_output:
        payload = build_json_payload(
            "token-tips",
            {
                "ok": True,
                "diagnostics": diagnostics,
                "rules": TOKEN_TIPS,
            },
        )
        emit_json(payload, compact=json_compact)
        return 0

    print("=" * 60)
    print("CodeGuard Token Efficiency Tips")
    print("=" * 60)
    print()
    print(f"Project state: {indexed_files} files indexed, {snapshot_files} files with snapshots")
    print()

    if indexed_files == 0:
        print("Tip: No files have feature indexes. Run 'codeguard index <file> --auto'")
        print("     on large files (>200 lines) to enable targeted reads (~85% token savings).")
        print()

    print("Top 11 Token-Saving Rules:")
    print("-" * 60)
    for tip in TOKEN_TIPS:
        print(f"  #{tip['id']:2d}  {tip['title']}")
        print(f"       {tip['detail']}")
        print(f"       Action: {tip['action']}")
        print()

    print("-" * 60)
    print("CodeGuard-specific savings:")
    print("  1. Feature indexes -> ~40-line targeted reads vs full-file reads")
    print("  2. Compress command -> ~40-50% reduction on verbose CLAUDE.md files")
    print("  3. Guard command -> backup without re-reading file in context")
    print("  4. Token compression mode -> ~20-65% output token reduction")
    return 0


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    if hasattr(args, "lock_timeout"):
        try:
            set_active_lock_timeout(float(args.lock_timeout))
        except ValueError as exc:
            print(f"Invalid --lock-timeout: {exc}")
            return 1

    try:
        if args.command == "init":
            init_codeguard(args.path or args.project)
            return 0

        if args.command == "add":
            return 0 if create_version_snapshot(args.file, args.feature, args.project, ensure_marker=not args.no_marker) else 1

        if args.command == "index":
            if args.auto and args.entry:
                print("Use either --auto or --entry, not both.")
                return 1
            if not args.auto and not args.entry:
                print('Feature index entries are required. Use --auto or repeated --entry "Feature:Line".')
                return 1
            if args.auto:
                try:
                    _, reviewed_lines, reviewed_hash = review_full_document_for_index(args.file, args.project)
                    entries = generate_feature_index_entries(args.file, args.project)
                except (FileNotFoundError, ValueError) as exc:
                    print(exc)
                    return 1
                print(
                    f"Full-document review completed: {len(reviewed_lines)} lines "
                    f"(hash {reviewed_hash})"
                )
            else:
                try:
                    entries = [parse_index_entry_spec(item) for item in args.entry]
                except ValueError as exc:
                    print(exc)
                    return 1
            applied = apply_feature_index(args.file, entries, args.project)
            return 0 if applied is not None else 1

        if args.command == "show-index":
            show_feature_index(args.file, args.project)
            return 0

        if args.command == "validate-index":
            return 0 if validate_feature_index(args.file, args.project, threshold=args.max_lines) else 1

        if args.command == "backup":
            return 0 if backup_before_modification(args.file, args.project, auto_sync=not args.strict_conflict) else 1

        if args.command == "sync-current":
            return 0 if sync_current_baseline(args.file, args.project, feature_name=args.feature, reason=args.reason) else 1

        if args.command == "confirm":
            try:
                success_value = parse_success(args.success)
            except ValueError as exc:
                print(exc)
                return 1
            success = confirm_modification(
                args.file,
                args.feature,
                args.reason,
                success_value,
                args.project,
                refresh_index_files=args.refresh_index,
                add_marker=args.add_marker,
            )
            return 0 if success else 1

        if args.command == "snapshot":
            success = create_manual_snapshot(args.file, args.feature, args.reason, args.project)
            return 0 if success else 1

        if args.command == "rollback":
            success = rollback(
                args.file,
                version=args.version,
                feature=args.feature,
                project_path=args.project,
                force=args.yes,
            )
            return 0 if success else 1

        if args.command == "list":
            list_versions(args.file, args.project)
            return 0

        if args.command == "status":
            return 0 if show_status(
                args.file,
                args.project,
                json_output=args.json,
                json_compact=args.json_compact,
            ) else 1

        if args.command == "doctor":
            return 0 if run_doctor(
                args.project,
                repair=args.repair,
                json_output=args.json,
                json_compact=args.json_compact,
            ) else 1

        if args.command == "batch":
            return 0 if batch_run(
                args.action,
                args.files,
                args.project,
                auto_index=args.auto,
                fail_fast=args.fail_fast,
                json_output=args.json,
                json_compact=args.json_compact,
            ) else 1

        if args.command == "lock-status":
            return 0 if show_lock_status(
                args.project,
                json_output=args.json,
                json_compact=args.json_compact,
            ) else 1

        if args.command == "unlock":
            return 0 if unlock_lock_file(
                args.project,
                assume_yes=args.yes,
                force=args.force,
            ) else 1

        if args.command == "token-tips":
            return run_token_tips(
                args.project,
                json_output=args.json,
                json_compact=args.json_compact,
            )

        if args.command == "compress":
            return run_compress(
                args.file,
                args.project,
                level=args.level,
                in_place=args.in_place,
                json_output=args.json,
                json_compact=args.json_compact,
            )

        if args.command == "guard":
            return run_guard(
                args.file,
                args.project,
                feature=args.feature,
                reason=args.reason,
                tier=args.tier,
                json_output=args.json,
                json_compact=args.json_compact,
            )

        if args.command == "schema":
            show_schema(args.target, compact=args.json_compact)
            return 0
    except TimeoutError as exc:
        print(exc)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

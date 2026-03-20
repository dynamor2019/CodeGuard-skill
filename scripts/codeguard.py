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
def index_lock(project_path: str | Path = ".", timeout_seconds: float = 8.0):
    project_root = normalize_project_path(project_path)
    lock_path = project_root / LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+", encoding="utf-8") as handle:
        started = time.time()
        acquired = False
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.time() - started >= timeout_seconds:
                    raise TimeoutError(
                        f"Could not acquire CodeGuard state lock within {timeout_seconds:.1f}s"
                    )
                time.sleep(0.05)

        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        f"{start} {'=' * 60}{end}",
        f"{start} {PROTECTION_MARKER}{end}",
        f"{start} Feature: {feature_name}{end}",
        f"{start} Version: {version}{end}",
        f"{start} Protected: {protected_at}{end}",
        f"{start} {'=' * 60}{end}",
        "",
    ]
    return "\n".join(marker_lines)


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
    write_text(target, marker + content)
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


def apply_feature_index(
    file_path: str | Path,
    entries: list[tuple[str, int]],
    project_path: str | Path = ".",
) -> list[tuple[str, int]] | None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return None

    ordered_entries = sorted(entries, key=lambda item: item[1])
    if not can_embed_inline_index(target):
        line_count = count_code_lines(target, project_root)
        for _, line_number in ordered_entries:
            if line_number > line_count:
                print(f"Feature index line {line_number} exceeds file length {line_count}.")
                return None
        sidecar_path = write_sidecar_index(target, ordered_entries, project_root)
        upsert_index_state(target, project_root, entries=ordered_entries)
        print(f"Feature index sidecar updated for: {get_file_key(target, project_root)}")
        print(f"  Sidecar: {sidecar_path.as_posix()}")
        return ordered_entries

    lines = read_text(target).splitlines()
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
        f"Feature index is required before working on files over {threshold} lines. "
        "Update the index first with `python scripts/codeguard.py index ...` after user approval."
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
    ensure_marker: bool = True,
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

    def mutation(index: dict[str, Any]) -> None:
        index["versions"].setdefault(file_key, []).append(snapshot)
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

    print(f"Snapshot created: v{version}")
    print(f"  Feature: {feature_name}")
    print(f"  Backup: {backup_path.as_posix()}")
    return snapshot


def create_version_snapshot(
    file_path: str | Path,
    feature_name: str,
    project_path: str | Path = ".",
) -> dict[str, Any] | None:
    return create_snapshot_record(file_path, feature_name, project_path, ensure_marker=True)


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


def backup_before_modification(file_path: str | Path, project_path: str | Path = ".") -> str | None:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return None
    if not ensure_index_ready(target, project_root):
        return None
    if check_conflict(target, project_root):
        print("Aborting backup due to conflict.")
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
    entry = "\n".join(
        [
            f"## Modification Record | {timestamp} | User Confirmed",
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
    with records_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry)
    return records_path


def confirm_modification(
    file_path: str | Path,
    feature_name: str,
    reason: str,
    success: bool = True,
    project_path: str | Path = ".",
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

    update_current_state(target, feature_name, project_root, reason=reason, source="confirm")
    record_path = write_modification_record(target, feature_name, reason, project_root)
    print("User-confirmed modification recorded.")
    print("Run `python scripts/codeguard.py snapshot ...` only if the user marks this state as important.")
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
        "index_state": index_state,
        "rollback_ready": rollback_ready,
        "orphan_snapshots": orphan_count,
    }


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

    init_parser = subparsers.add_parser("init", help="Initialize CodeGuard in a project.")
    init_parser.add_argument("path", nargs="?", default=None)

    add_parser = subparsers.add_parser(
        "add",
        help="Add or refresh a protection marker and create an initial important snapshot.",
    )
    add_parser.add_argument("file")
    add_parser.add_argument("feature")

    index_parser = subparsers.add_parser(
        "index",
        help='Create or update a feature index. Use repeated --entry "Feature description:LineNumber".',
    )
    index_parser.add_argument("file")
    index_parser.add_argument("--entry", action="append", required=True)

    show_index_parser = subparsers.add_parser("show-index", help="Show the current feature index.")
    show_index_parser.add_argument("file")

    validate_index_parser = subparsers.add_parser(
        "validate-index",
        help="Validate the current feature index and the over-200-lines rule.",
    )
    validate_index_parser.add_argument("file")
    validate_index_parser.add_argument("--max-lines", type=int, default=DEFAULT_INDEX_THRESHOLD)

    backup_parser = subparsers.add_parser("backup", help="Create a pre-modification backup.")
    backup_parser.add_argument("file")

    confirm_parser = subparsers.add_parser(
        "confirm",
        help="Record a user-confirmed successful modification without creating a milestone snapshot.",
    )
    confirm_parser.add_argument("file")
    confirm_parser.add_argument("feature")
    confirm_parser.add_argument("reason")
    confirm_parser.add_argument("success", nargs="?", default="true")

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Manually mark the current file state as an important version and store a snapshot.",
    )
    snapshot_parser.add_argument("file")
    snapshot_parser.add_argument("feature")
    snapshot_parser.add_argument("reason")

    rollback_parser = subparsers.add_parser("rollback", help="Restore a previous snapshot.")
    rollback_parser.add_argument("file")
    selector = rollback_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--version", type=int)
    selector.add_argument("--feature")
    rollback_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")

    list_parser = subparsers.add_parser("list", help="List important snapshots for a file.")
    list_parser.add_argument("file")

    status_parser = subparsers.add_parser(
        "status",
        help="Show protection, accepted state, index health, and rollback readiness.",
    )
    status_parser.add_argument("file")
    status_parser.add_argument("--json", action="store_true", help="Emit status as JSON.")
    status_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Scan CodeGuard metadata consistency and snapshot/index health.",
    )
    doctor_parser.add_argument("--repair", action="store_true", help="Repair safe metadata mismatches.")
    doctor_parser.add_argument("--json", action="store_true", help="Emit doctor report as JSON.")
    doctor_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")

    batch_parser = subparsers.add_parser(
        "batch",
        help="Run validate-index, backup, or status in batch mode.",
    )
    batch_parser.add_argument("action", choices=["validate-index", "backup", "status"])
    batch_parser.add_argument("files", nargs="+")
    batch_parser.add_argument("--fail-fast", action="store_true", help="Stop batch execution on first failure.")
    batch_parser.add_argument("--json", action="store_true", help="Emit batch result as JSON.")
    batch_parser.add_argument("--json-compact", action="store_true", help="Emit compact single-line JSON.")

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

    if args.command == "init":
        init_codeguard(args.path or args.project)
        return 0

    if args.command == "add":
        return 0 if create_version_snapshot(args.file, args.feature, args.project) else 1

    if args.command == "index":
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
        return 0 if backup_before_modification(args.file, args.project) else 1

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
            fail_fast=args.fail_fast,
            json_output=args.json,
            json_compact=args.json_compact,
        ) else 1

    if args.command == "schema":
        show_schema(args.target, compact=args.json_compact)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())




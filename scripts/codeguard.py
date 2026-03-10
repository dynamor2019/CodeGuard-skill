#!/usr/bin/env python3
"""Project-local feature indexing, confirmation, and snapshot workflow for CodeGuard."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

VERSION = "1.2.0"

CODEGUARD_DIR = Path(".codeguard")
VERSIONS_DIR = CODEGUARD_DIR / "versions"
TEMP_DIR = CODEGUARD_DIR / "temp"
RECORDS_DIR = CODEGUARD_DIR / "records"
INDEX_FILE = CODEGUARD_DIR / "index.json"
MODIFICATIONS_FILE = RECORDS_DIR / "modifications.md"

DEFAULT_INDEX_THRESHOLD = 200
FEATURE_INDEX_START = "[CodeGuard Feature Index]"
FEATURE_INDEX_END = "[/CodeGuard Feature Index]"
FEATURE_INDEX_ENTRY = re.compile(r"^- (?P<label>.+?) -> line (?P<line>\d+)$")

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
    ".css": {"start": "/*", "end": "*/"},
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


def normalize_project_path(project_path: str | Path = ".") -> Path:
    return Path(project_path).expanduser().resolve()


def resolve_file_path(file_path: str | Path, project_path: str | Path = ".") -> Path:
    raw = Path(file_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    return (normalize_project_path(project_path) / raw).resolve()


def init_codeguard(project_path: str | Path = ".", quiet: bool = False) -> str:
    project_root = normalize_project_path(project_path)
    for path in (CODEGUARD_DIR, VERSIONS_DIR, TEMP_DIR, RECORDS_DIR):
        (project_root / path).mkdir(parents=True, exist_ok=True)

    index_path = project_root / INDEX_FILE
    if not index_path.exists():
        write_json(
            index_path,
            {"versions": {}, "last_version": {}, "current_state": {}},
        )

    if not quiet:
        print(f"CodeGuard initialized at: {(project_root / CODEGUARD_DIR).as_posix()}")
    return str(project_root / CODEGUARD_DIR)


def load_index(project_path: str | Path = ".") -> dict[str, Any]:
    project_root = normalize_project_path(project_path)
    init_codeguard(project_root, quiet=True)
    index_path = project_root / INDEX_FILE
    with index_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("versions", {})
    data.setdefault("last_version", {})
    data.setdefault("current_state", {})
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temp_path.replace(path)


def save_index(project_path: str | Path, index: dict[str, Any]) -> None:
    project_root = normalize_project_path(project_path)
    write_json(project_root / INDEX_FILE, index)


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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


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


def normalize_index_payload(line: str) -> str:
    payload = line.strip()
    payload = re.sub(r"^(?://|#|/\*+|\*|<!--)\s*", "", payload)
    payload = re.sub(r"\s*(?:\*/|-->)\s*$", "", payload)
    return payload.strip()


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


def find_feature_index_bounds(lines: list[str]) -> tuple[int | None, int | None]:
    start = None
    for index, line in enumerate(lines):
        payload = normalize_index_payload(line)
        if payload == FEATURE_INDEX_START:
            start = index
            continue
        if payload == FEATURE_INDEX_END and start is not None:
            return start, index
    return None, None


def extract_feature_index_entries_from_lines(lines: list[str]) -> list[tuple[str, int]]:
    start, end = find_feature_index_bounds(lines)
    if start is None or end is None:
        return []

    entries: list[tuple[str, int]] = []
    for line in lines[start + 1 : end]:
        payload = normalize_index_payload(line)
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
    return extract_feature_index_entries_from_lines(read_text(target).splitlines())


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

    lines = read_text(target).splitlines()
    prefix_len = leading_preamble_length(lines)
    main_lines = lines[prefix_len:]
    start, end = find_feature_index_bounds(main_lines)

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

    ordered_entries = sorted(entries, key=lambda item: item[1])
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
    entries = extract_feature_index_entries_from_lines(lines)
    start, end = find_feature_index_bounds(lines)

    problems: list[str] = []
    warnings: list[str] = []
    if required and (start is None or end is None):
        problems.append(
            f"Feature index is required for files over {threshold} lines but no valid index block was found."
        )
    if start is not None and end is None:
        problems.append("Feature index start marker exists without a matching end marker.")
    if start is not None and end is not None and not entries:
        problems.append("Feature index block exists but contains no valid entries.")

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
        previous_line = line_number

    valid = not problems
    if not quiet:
        print(f"Feature index status for: {get_file_key(target, project_root)}")
        print(f"  Line count: {len(lines)}")
        print(f"  Required: {'yes' if required else 'no'}")
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
    print(f"Feature index for: {get_file_key(target, project_root)}")
    print(f"  Required: {'yes' if required else 'no'}")
    print(f"  Entries: {len(entries)}")
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
    index = load_index(project_root)
    state = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "feature": feature_name,
        "hash": calculate_hash(target),
        "path": target.as_posix(),
        "source": source,
    }
    if reason:
        state["reason"] = reason
    index["current_state"][file_key] = state
    save_index(project_root, index)


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

    index = load_index(project_root)
    index["versions"].setdefault(file_key, []).append(snapshot)
    index["last_version"][file_key] = version
    index["current_state"][file_key] = {
        "timestamp": snapshot["timestamp"],
        "feature": feature_name,
        "hash": snapshot["hash"],
        "path": target.as_posix(),
        "source": "snapshot",
        "reason": reason or "",
    }
    save_index(project_root, index)

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


def list_versions(file_path: str | Path, project_path: str | Path = ".") -> list[dict[str, Any]]:
    index = load_index(project_path)
    file_key = get_file_key(file_path, project_path)
    versions = index["versions"].get(file_key, [])
    if not versions:
        print("No snapshot history found.")
        return []

    print(f"Snapshot history for: {file_key}")
    print("-" * 80)
    print(f"{'Version':<10}{'Feature':<24}{'Timestamp':<24}{'Hash':<18}")
    print("-" * 80)
    for snapshot in versions:
        print(
            f"v{snapshot['version']:<9}"
            f"{snapshot['feature'][:23]:<24}"
            f"{snapshot['timestamp']:<24}"
            f"{snapshot['hash'][:16]:<18}"
        )
    print("-" * 80)
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
    return parser


def parse_success(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Unsupported success value: {value}")


def main(argv: list[str] | None = None) -> int:
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

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

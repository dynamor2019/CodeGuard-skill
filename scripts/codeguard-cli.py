#!/usr/bin/env python3
"""Legacy repository CLI that now shares the project-local CodeGuard core."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from codeguard_v2 import (
    backup_before_modification,
    calculate_hash,
    confirm_modification,
    create_version_snapshot,
    get_comment_format,
    get_file_key,
    get_latest_snapshot,
    list_versions,
    normalize_project_path,
    resolve_file_path,
    rollback as core_rollback,
)

RECORD_FILE = "codeguard-records.md"
ATTEMPT_FILE = ".codeguard-attempts.json"
LOCK_FILE = ".codeguard-locks.json"
AI_TRACE_FILE = ".codeguard-ai-traces.json"
INDEX_HEADER = "Code Functionality Index"


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except ValueError:
                pass


configure_console()


def state_path(project_path: str | Path, name: str) -> Path:
    return normalize_project_path(project_path) / name


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    if not data:
        if path.exists():
            path.unlink()
        return
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def relative_key(file_path: str | Path, project_path: str | Path = ".") -> str:
    return get_file_key(file_path, project_path)


def feature_key(file_path: str | Path, feature_name: str, project_path: str | Path = ".") -> str:
    return f"{relative_key(file_path, project_path)}:{feature_name}"


def load_locks(project_path: str | Path = ".") -> dict[str, Any]:
    return load_json(state_path(project_path, LOCK_FILE))


def save_locks(project_path: str | Path, locks: dict[str, Any]) -> None:
    save_json(state_path(project_path, LOCK_FILE), locks)


def load_attempts(project_path: str | Path = ".") -> dict[str, Any]:
    return load_json(state_path(project_path, ATTEMPT_FILE))


def save_attempts(project_path: str | Path, attempts: dict[str, Any]) -> None:
    save_json(state_path(project_path, ATTEMPT_FILE), attempts)


def load_ai_traces(project_path: str | Path = ".") -> dict[str, Any]:
    return load_json(state_path(project_path, AI_TRACE_FILE))


def save_ai_traces(project_path: str | Path, traces: dict[str, Any]) -> None:
    save_json(state_path(project_path, AI_TRACE_FILE), traces)


def append_legacy_record(
    file_path: str | Path,
    feature_name: str,
    reason: str,
    approach: str,
    success: bool,
    project_path: str | Path = ".",
) -> Path | None:
    if not success:
        return None

    target = resolve_file_path(file_path, project_path)
    output = state_path(project_path, RECORD_FILE)
    entry = "\n".join(
        [
            f"## Modification Record | {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Success",
            f"- **File Path**: {relative_key(target, project_path)}",
            f"- **Feature Name**: {feature_name}",
            f"- **Reason**: {reason}",
            f"- **Approach**: {approach}",
            f"- **Hash**: {calculate_hash(target)}",
            "",
            "---",
            "",
        ]
    )
    with output.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry)
    return output


def lock_feature(file_path: str, feature_name: str, project_path: str | Path = ".") -> bool:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return False

    locks = load_locks(project_path)
    key = feature_key(target, feature_name, project_path)
    locks[key] = {
        "file_path": target.as_posix(),
        "file_key": relative_key(target, project_path),
        "feature_name": feature_name,
        "file_hash": calculate_hash(target),
        "locked_by": os.getenv("USER", os.getenv("USERNAME", "unknown")),
        "locked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "status": "locked",
    }
    save_locks(project_path, locks)
    print(f"Feature locked: {feature_name}")
    return True


def unlock_feature(
    file_path: str,
    feature_name: str,
    project_path: str | Path = ".",
    *,
    force: bool = False,
) -> bool:
    locks = load_locks(project_path)
    target = resolve_file_path(file_path, project_path)
    key = feature_key(target, feature_name, project_path)
    if key not in locks:
        print(f"Feature not locked: {feature_name}")
        return False

    current_hash = calculate_hash(target)
    original_hash = locks[key]["file_hash"]
    if current_hash != original_hash and not force:
        print("Warning: file contents differ from the recorded lock hash.")
        response = input("Continue unlocking? (y/N): ").strip().lower()
        if response != "y":
            print("Unlock cancelled.")
            return False

    del locks[key]
    save_locks(project_path, locks)
    print(f"Feature unlocked: {feature_name}")
    return True


def check_tampering(file_path: str, feature_name: str, project_path: str | Path = ".") -> bool:
    locks = load_locks(project_path)
    target = resolve_file_path(file_path, project_path)
    key = feature_key(target, feature_name, project_path)
    if key not in locks:
        return True

    current_hash = calculate_hash(target)
    original_hash = locks[key]["file_hash"]
    if current_hash == original_hash:
        return True

    print("Tampering detected.")
    print(f"  Feature: {feature_name}")
    print(f"  Locked by: {locks[key]['locked_by']}")
    print(f"  Original hash: {original_hash[:16]}...")
    print(f"  Current hash: {current_hash[:16]}...")
    return False


def record_ai_trace(
    file_path: str,
    feature_name: str,
    action: str,
    details: dict[str, Any],
    project_path: str | Path = ".",
) -> None:
    traces = load_ai_traces(project_path)
    key = feature_key(file_path, feature_name, project_path)
    traces.setdefault(key, []).append(
        {
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "details": details,
            "file_hash": calculate_hash(resolve_file_path(file_path, project_path)),
        }
    )
    save_ai_traces(project_path, traces)


def add_mark(file_path: str, feature_name: str, project_path: str | Path = ".") -> bool:
    snapshot = create_version_snapshot(file_path, feature_name, project_path)
    if snapshot is None:
        return False
    lock_feature(file_path, feature_name, project_path)
    return True


def latest_attempt(project_path: str | Path, key: str) -> dict[str, Any] | None:
    attempts = load_attempts(project_path)
    values = attempts.get(key, [])
    return values[-1] if values else None


def record(
    file_path: str,
    feature_name: str,
    reason: str,
    approach: str,
    success: bool = False,
    project_path: str | Path = ".",
) -> bool:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return False

    if not check_tampering(target, feature_name, project_path):
        print("Continuing to record the attempt, but the lock hash no longer matches.")

    entry = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "approach": approach,
        "success": success,
        "file_hash": calculate_hash(target),
    }

    attempts = load_attempts(project_path)
    key = feature_key(target, feature_name, project_path)
    attempts.setdefault(key, []).append(entry)
    save_attempts(project_path, attempts)
    record_ai_trace(target, feature_name, "modify", entry, project_path)

    if success:
        print("Modification attempt recorded as successful.")
        print("Run `confirm` to promote the current file into a permanent snapshot record.")
    else:
        print("Modification attempt recorded as failed.")
    return True


def confirm_implementation(file_path: str, feature_name: str, project_path: str | Path = ".") -> bool:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return False

    key = feature_key(target, feature_name, project_path)
    attempt = latest_attempt(project_path, key)
    reason = "Confirmed implementation via legacy CLI"
    approach = "n/a"
    if attempt:
        reason = attempt.get("reason") or reason
        approach = attempt.get("approach") or approach

    confirmed = confirm_modification(target, feature_name, reason, True, project_path)
    if not confirmed:
        return False

    append_legacy_record(target, feature_name, reason, approach, True, project_path)

    locks = load_locks(project_path)
    if key in locks:
        locks[key]["status"] = "confirmed"
        locks[key]["confirmed_at"] = dt.datetime.now().isoformat(timespec="seconds")
        locks[key]["file_hash"] = calculate_hash(target)
        save_locks(project_path, locks)

    attempts = load_attempts(project_path)
    if key in attempts:
        del attempts[key]
        save_attempts(project_path, attempts)

    traces = load_ai_traces(project_path)
    if key in traces:
        del traces[key]
        save_ai_traces(project_path, traces)

    print(f"Feature implementation confirmed: {feature_name}")
    return True


def clean_traces(
    file_path: str | None = None,
    feature_name: str | None = None,
    project_path: str | Path = ".",
) -> None:
    if file_path and feature_name:
        key = feature_key(file_path, feature_name, project_path)
        attempts = load_attempts(project_path)
        traces = load_ai_traces(project_path)

        if key in attempts:
            del attempts[key]
            save_attempts(project_path, attempts)
        if key in traces:
            del traces[key]
            save_ai_traces(project_path, traces)
        print(f"Removed temporary traces for {feature_name}.")
        return

    for name in (ATTEMPT_FILE, AI_TRACE_FILE):
        path = state_path(project_path, name)
        if path.exists():
            path.unlink()
            print(f"Deleted {path.name}")


def marker_features(file_path: str | Path) -> list[tuple[int, str]]:
    target = Path(file_path)
    if not target.exists():
        return []

    features: list[tuple[int, str]] = []
    patterns = [
        re.compile(r"Feature Protection:\s*(.+?)(?:\s+\[[^\]]+\])?\s*$"),
        re.compile(r"Feature Name:\s*(.+?)\s*$"),
        re.compile(r"Feature:\s*(.+?)\s*$"),
    ]
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                features.append((line_number, match.group(1).strip()))
                break
    return features


def check(file_path: str, project_path: str | Path = ".") -> None:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return

    features = marker_features(target)
    locks = load_locks(project_path)
    file_key = relative_key(target, project_path)
    related_locks = {key: value for key, value in locks.items() if key.startswith(f"{file_key}:")}

    if not features and not related_locks:
        print(f"{file_key} has no protection markers or locks.")
        return

    print(f"Protection status for {file_key}:")
    for line_number, feature_name in features:
        key = feature_key(target, feature_name, project_path)
        locked = "locked" if key in locks else "unlocked"
        print(f"  line {line_number}: {feature_name} ({locked})")

    if related_locks and not features:
        for key, value in related_locks.items():
            print(f"  locked: {value['feature_name']} ({value['status']})")

    latest = get_latest_snapshot(target, project_path)
    if latest:
        print(f"Latest snapshot: v{latest['version']} ({latest['feature']})")


def show_status(file_path: str, feature_name: str, project_path: str | Path = ".") -> None:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return

    key = feature_key(target, feature_name, project_path)
    locks = load_locks(project_path)
    attempts = load_attempts(project_path)
    traces = load_ai_traces(project_path)
    latest = get_latest_snapshot(target, project_path)

    print(f"Status for {key}")
    if key in locks:
        info = locks[key]
        current_hash = calculate_hash(target)
        tampered = current_hash != info["file_hash"]
        print(f"  lock: {info['status']} by {info['locked_by']}")
        print(f"  locked_at: {info['locked_at']}")
        print(f"  tampered: {'yes' if tampered else 'no'}")
    else:
        print("  lock: none")

    attempt_values = attempts.get(key, [])
    trace_values = traces.get(key, [])
    print(f"  attempts: {len(attempt_values)}")
    print(f"  traces: {len(trace_values)}")
    if latest:
        print(f"  latest_snapshot: v{latest['version']} ({latest['feature']})")


def detect_regions(lines: list[str], suffix: str) -> list[dict[str, Any]]:
    patterns = {
        ".js": [r"function\s+(\w+)", r"class\s+(\w+)", r"const\s+(\w+)\s*=\s*\("],
        ".ts": [r"function\s+(\w+)", r"class\s+(\w+)", r"const\s+(\w+)\s*=\s*\("],
        ".py": [r"def\s+(\w+)", r"class\s+(\w+)"],
        ".java": [r"class\s+(\w+)", r"(?:public|private|protected)?\s+\w+\s+(\w+)\s*\("],
        ".html": [r"function\s+(\w+)"],
    }
    use_patterns = patterns.get(suffix, patterns[".js"])

    regions: list[dict[str, Any]] = []
    current_name = None
    current_start = None
    for index, line in enumerate(lines, start=1):
        for pattern in use_patterns:
            match = re.search(pattern, line)
            if not match:
                continue
            name = next(group for group in match.groups() if group)
            if current_name is not None:
                regions.append({"name": current_name, "start": current_start, "end": index - 1, "type": "symbol"})
            current_name = name
            current_start = index
            break

    if current_name is not None:
        regions.append({"name": current_name, "start": current_start, "end": len(lines), "type": "symbol"})
    return regions


def render_comment_line(comment_format: dict[str, str], text: str = "") -> str:
    start = comment_format["start"]
    end = comment_format["end"]
    if end:
        return f"{start} {text} {end}".rstrip()
    return f"{start} {text}".rstrip()


def build_index(comment_format: dict[str, str], file_path: Path, regions: list[dict[str, Any]]) -> str:
    lines = [
        render_comment_line(comment_format, f"==================== {INDEX_HEADER} ===================="),
        render_comment_line(comment_format, f"File: {file_path}"),
        render_comment_line(comment_format, f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
        render_comment_line(comment_format, f"Total Regions: {len(regions)}"),
        render_comment_line(comment_format),
    ]
    for idx, region in enumerate(regions, start=1):
        lines.append(
            render_comment_line(
                comment_format,
                f"Region {idx}: {region['name']} (Lines {region['start']}-{region['end']})",
            )
        )
    lines.extend(
        [
            render_comment_line(comment_format),
            render_comment_line(comment_format, f"==================== {INDEX_HEADER} ===================="),
            "",
        ]
    )
    return "\n".join(lines)


def strip_existing_index(content: str) -> str:
    if INDEX_HEADER not in content:
        return content
    lines = content.splitlines()
    start = None
    end = None
    for index, line in enumerate(lines):
        if INDEX_HEADER in line and start is None:
            start = index
        elif INDEX_HEADER in line and start is not None and index > start:
            end = index + 1
            break
    if start is None or end is None:
        return content
    return "\n".join(lines[end:]).lstrip("\n")


def analyze_code(file_path: str, regenerate: bool = False, project_path: str | Path = ".") -> None:
    target = resolve_file_path(file_path, project_path)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return

    content = target.read_text(encoding="utf-8")
    if regenerate:
        content = strip_existing_index(content)

    lines = content.splitlines()
    comment_format = get_comment_format(target)
    regions = detect_regions(lines, target.suffix.lower())
    index = build_index(comment_format, target, regions)
    target.write_text(index + content, encoding="utf-8", newline="\n")
    print(f"Indexed {len(regions)} region(s) in {relative_key(target, project_path)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeguard-cli",
        description="Legacy repository CLI that shares the project-local CodeGuard core.",
    )
    parser.add_argument(
        "--project",
        default=".",
        help="Project root for CodeGuard state files. Defaults to the current directory.",
    )
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a protection marker and snapshot.")
    add_parser.add_argument("file")
    add_parser.add_argument("feature")

    lock_parser = subparsers.add_parser("lock", help="Record a lock hash for a feature.")
    lock_parser.add_argument("file")
    lock_parser.add_argument("feature")

    unlock_parser = subparsers.add_parser("unlock", help="Remove a recorded lock.")
    unlock_parser.add_argument("file")
    unlock_parser.add_argument("feature")
    unlock_parser.add_argument("--force", action="store_true")

    record_parser = subparsers.add_parser("record", help="Record a modification attempt.")
    record_parser.add_argument("file")
    record_parser.add_argument("feature")
    record_parser.add_argument("reason")
    record_parser.add_argument("approach")
    record_parser.add_argument("success")

    confirm_parser = subparsers.add_parser("confirm", help="Confirm a successful implementation.")
    confirm_parser.add_argument("file")
    confirm_parser.add_argument("feature")

    backup_parser = subparsers.add_parser("backup", help="Create a pre-modification backup.")
    backup_parser.add_argument("file")

    check_parser = subparsers.add_parser("check", help="Inspect markers and lock state.")
    check_parser.add_argument("file")

    analyze_parser = subparsers.add_parser("analyze", help="Insert a code navigation index.")
    analyze_parser.add_argument("file")

    index_parser = subparsers.add_parser("index", help="Regenerate a code navigation index.")
    index_parser.add_argument("file")

    status_parser = subparsers.add_parser("status", help="Show detailed feature status.")
    status_parser.add_argument("file")
    status_parser.add_argument("feature")

    clean_parser = subparsers.add_parser("clean", help="Clean attempt and trace files.")
    clean_parser.add_argument("file", nargs="?")
    clean_parser.add_argument("feature", nargs="?")

    list_parser = subparsers.add_parser("list", help="List snapshots for a file.")
    list_parser.add_argument("file")

    rollback_parser = subparsers.add_parser("rollback", help="Rollback to a snapshot.")
    rollback_parser.add_argument("file")
    selector = rollback_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--version", type=int)
    selector.add_argument("--feature")
    rollback_parser.add_argument("--yes", action="store_true")
    return parser


def parse_success(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Unsupported success value: {value}")


def help_text() -> None:
    build_parser().print_help()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    project = args.project
    if args.command == "add":
        return 0 if add_mark(args.file, args.feature, project) else 1
    if args.command == "lock":
        return 0 if lock_feature(args.file, args.feature, project) else 1
    if args.command == "unlock":
        return 0 if unlock_feature(args.file, args.feature, project, force=args.force) else 1
    if args.command == "record":
        return 0 if record(args.file, args.feature, args.reason, args.approach, parse_success(args.success), project) else 1
    if args.command == "confirm":
        return 0 if confirm_implementation(args.file, args.feature, project) else 1
    if args.command == "backup":
        return 0 if backup_before_modification(args.file, project) else 1
    if args.command == "check":
        check(args.file, project)
        return 0
    if args.command == "analyze":
        analyze_code(args.file, regenerate=False, project_path=project)
        return 0
    if args.command == "index":
        analyze_code(args.file, regenerate=True, project_path=project)
        return 0
    if args.command == "status":
        show_status(args.file, args.feature, project)
        return 0
    if args.command == "clean":
        clean_traces(args.file, args.feature, project)
        return 0
    if args.command == "list":
        list_versions(args.file, project)
        return 0
    if args.command == "rollback":
        return 0 if core_rollback(args.file, args.version, args.feature, project, force=args.yes) else 1

    help_text()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

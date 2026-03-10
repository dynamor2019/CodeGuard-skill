#!/usr/bin/env python3
"""Compatibility wrapper around the official project-local CodeGuard workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codeguard import (
    VERSION,
    backup_before_modification,
    confirm_modification,
    create_manual_snapshot,
    create_version_snapshot,
    get_current_state,
    get_feature_index,
    get_latest_snapshot,
    get_file_key,
    has_codeguard_marker,
    has_protection_marker,
    is_index_required,
    list_versions,
    normalize_project_path,
    parse_index_entry_spec,
    parse_success,
    resolve_file_path,
    rollback as core_rollback,
    show_feature_index,
    validate_feature_index,
    apply_feature_index,
)


DEFAULT_CONFIRM_REASON = "User confirmed via compatibility CLI"
ANALYZE_REMOVAL_MESSAGE = (
    "Automatic function-based indexing was removed. "
    'Use `python scripts/codeguard-cli.py index <file> --entry "Feature description:LineNumber"` '
    "after user approval."
)


def compatibility_reason(value: str | None) -> str:
    if value is None:
        return DEFAULT_CONFIRM_REASON
    stripped = value.strip()
    return stripped or DEFAULT_CONFIRM_REASON


def show_status(file_path: str, project_path: str | Path = ".") -> bool:
    project_root = normalize_project_path(project_path)
    target = resolve_file_path(file_path, project_root)
    if not target.exists():
        print(f"File not found: {target.as_posix()}")
        return False

    content = target.read_text(encoding="utf-8")
    marker_present = has_codeguard_marker(content) or has_protection_marker(content)
    entries = get_feature_index(target, project_root)
    index_required = is_index_required(target, project_root)
    index_valid = validate_feature_index(target, project_root, quiet=True)
    current_state = get_current_state(target, project_root)
    latest_snapshot = get_latest_snapshot(target, project_root)

    print(f"CodeGuard status for: {get_file_key(target, project_root)}")
    print(f"  Protection marker: {'yes' if marker_present else 'no'}")
    print(f"  Feature index required: {'yes' if index_required else 'no'}")
    print(f"  Feature index valid: {'yes' if index_valid else 'no'}")
    print(f"  Feature index entries: {len(entries)}")
    if current_state is None:
        print("  Current state: none recorded")
    else:
        print(
            f"  Current state: {current_state.get('source', 'unknown')} at "
            f"{current_state.get('timestamp', 'unknown')}"
        )
    if latest_snapshot is None:
        print("  Latest snapshot: none")
    else:
        print(
            f"  Latest snapshot: v{latest_snapshot['version']} "
            f"({latest_snapshot['feature']})"
        )
    return True


def apply_index_entries(
    file_path: str,
    entry_specs: list[str] | None,
    project_path: str | Path = ".",
) -> bool:
    if not entry_specs:
        print(
            "Feature index entries are required. "
            'Use repeated `--entry "Feature description:LineNumber"` arguments.'
        )
        return False

    try:
        entries = [parse_index_entry_spec(item) for item in entry_specs]
    except ValueError as exc:
        print(exc)
        return False

    return apply_feature_index(file_path, entries, project_path) is not None


def confirm_from_args(args: argparse.Namespace) -> bool:
    reason = compatibility_reason(getattr(args, "reason", None))
    try:
        success = parse_success(getattr(args, "success", "true"))
    except ValueError as exc:
        print(exc)
        return False

    if getattr(args, "approach", None):
        print("Legacy `approach` metadata is ignored. CodeGuard now records success only.")

    return confirm_modification(
        args.file,
        args.feature,
        reason,
        success,
        args.project,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeguard-cli",
        description="Compatibility wrapper around the official project-local CodeGuard workflow.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument(
        "--project",
        default=".",
        help="Project root that stores the .codeguard directory. Defaults to the current directory.",
    )
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser(
        "add",
        help="Add or refresh a protection marker and create an initial important snapshot.",
    )
    add_parser.add_argument("file")
    add_parser.add_argument("feature")

    backup_parser = subparsers.add_parser("backup", help="Create a pre-modification backup.")
    backup_parser.add_argument("file")

    confirm_parser = subparsers.add_parser(
        "confirm",
        help="Record a user-confirmed successful modification without creating a snapshot.",
    )
    confirm_parser.add_argument("file")
    confirm_parser.add_argument("feature")
    confirm_parser.add_argument("reason", nargs="?")
    confirm_parser.add_argument("success", nargs="?", default="true")

    record_parser = subparsers.add_parser(
        "record",
        help="Legacy alias for confirm. Permanent records are still created only after user confirmation.",
    )
    record_parser.add_argument("file")
    record_parser.add_argument("feature")
    record_parser.add_argument("reason")
    record_parser.add_argument("approach", nargs="?")
    record_parser.add_argument("success", nargs="?", default="true")

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Manually mark the current file state as an important version and store a snapshot.",
    )
    snapshot_parser.add_argument("file")
    snapshot_parser.add_argument("feature")
    snapshot_parser.add_argument("reason")

    index_parser = subparsers.add_parser(
        "index",
        help='Create or update a feature index. Use repeated --entry "Feature description:LineNumber".',
    )
    index_parser.add_argument("file")
    index_parser.add_argument("--entry", action="append")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Deprecated alias for index. CodeGuard no longer auto-generates function indexes.",
    )
    analyze_parser.add_argument("file")
    analyze_parser.add_argument("--entry", action="append")

    show_index_parser = subparsers.add_parser("show-index", help="Show the current feature index.")
    show_index_parser.add_argument("file")

    validate_index_parser = subparsers.add_parser(
        "validate-index",
        help="Validate the current feature index and the over-200-lines rule.",
    )
    validate_index_parser.add_argument("file")
    validate_index_parser.add_argument("--max-lines", type=int, default=200)

    check_parser = subparsers.add_parser(
        "check",
        help="Show protection, index, current-state, and latest-snapshot status for a file.",
    )
    check_parser.add_argument("file")

    status_parser = subparsers.add_parser(
        "status",
        help="Alias for check. Kept for compatibility with older repository workflows.",
    )
    status_parser.add_argument("file")

    list_parser = subparsers.add_parser("list", help="List important snapshots for a file.")
    list_parser.add_argument("file")

    rollback_parser = subparsers.add_parser("rollback", help="Restore a previous snapshot.")
    rollback_parser.add_argument("file")
    selector = rollback_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--version", type=int)
    selector.add_argument("--feature")
    rollback_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    if args.command == "add":
        return 0 if create_version_snapshot(args.file, args.feature, args.project) else 1

    if args.command == "backup":
        return 0 if backup_before_modification(args.file, args.project) else 1

    if args.command in {"confirm", "record"}:
        return 0 if confirm_from_args(args) else 1

    if args.command == "snapshot":
        return 0 if create_manual_snapshot(args.file, args.feature, args.reason, args.project) else 1

    if args.command == "index":
        return 0 if apply_index_entries(args.file, args.entry, args.project) else 1

    if args.command == "analyze":
        if not args.entry:
            print(ANALYZE_REMOVAL_MESSAGE)
            return 1
        return 0 if apply_index_entries(args.file, args.entry, args.project) else 1

    if args.command == "show-index":
        show_feature_index(args.file, args.project)
        return 0

    if args.command == "validate-index":
        return 0 if validate_feature_index(args.file, args.project, threshold=args.max_lines) else 1

    if args.command in {"check", "status"}:
        return 0 if show_status(args.file, args.project) else 1

    if args.command == "list":
        list_versions(args.file, args.project)
        return 0

    if args.command == "rollback":
        success = core_rollback(
            args.file,
            version=args.version,
            feature=args.feature,
            project_path=args.project,
            force=args.yes,
        )
        return 0 if success else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

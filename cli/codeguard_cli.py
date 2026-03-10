#!/usr/bin/env python3
"""Legacy global CodeGuard CLI."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import re
import sys
from pathlib import Path


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except ValueError:
                pass


configure_console()

CONFIG_DIR = Path.home() / ".codeguard"
CONFIG_FILE = CONFIG_DIR / "config.json"
RECORDS_FILE = CONFIG_DIR / "records.json"

INDEX_HEADER = "Code Functionality Index"

IDE_PATHS = {
    "windows": {
        "trae-cn": [
            os.path.expandvars(r"%USERPROFILE%\.trae-cn\claude\skills"),
            os.path.expandvars(r"%USERPROFILE%\.trae-cn\skills"),
        ],
        "trae": [
            os.path.expandvars(r"%USERPROFILE%\.trae\claude\skills"),
            os.path.expandvars(r"%USERPROFILE%\.trae\skills"),
        ],
        "cursor": [os.path.expandvars(r"%USERPROFILE%\.cursor\skills")],
        "vscode": [os.path.expandvars(r"%USERPROFILE%\.vscode\skills")],
    },
    "darwin": {
        "trae-cn": ["~/.trae-cn/skills"],
        "trae": ["~/.trae/skills"],
        "cursor": ["~/.cursor/skills"],
        "vscode": ["~/.vscode/skills"],
    },
    "linux": {
        "trae-cn": ["~/.trae-cn/skills"],
        "trae": ["~/.trae/skills"],
        "cursor": ["~/.cursor/skills"],
        "vscode": ["~/.vscode/skills"],
    },
}


def init_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        return

    default_config = {
        "version": "1.0.0",
        "installed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "ide_paths": IDE_PATHS,
    }
    CONFIG_FILE.write_text(json.dumps(default_config, indent=2), encoding="utf-8")


def get_comment(file_path: str | Path) -> str:
    ext = Path(file_path).suffix.lower()
    return {".py": "#", ".sh": "#", ".rb": "#", ".php": "#"}.get(ext, "//")


def get_file_hash(file_path: str | Path) -> str | None:
    target = Path(file_path)
    if not target.exists():
        return None

    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records() -> dict:
    if RECORDS_FILE.exists():
        return json.loads(RECORDS_FILE.read_text(encoding="utf-8"))
    return {}


def save_records(records: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_FILE.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def add_protection_mark(file_path: str, feature_name: str) -> bool:
    target = Path(file_path)
    if not target.exists():
        print(f"File not found: {target}")
        return False

    content = target.read_text(encoding="utf-8")
    if "[CodeGuard Protection]" in content or "Feature Protection:" in content:
        print(f"Protection marker already exists in {target}")
        return False

    comment = get_comment(target)
    marker = "\n".join(
        [
            f"{comment} ============================================================",
            f"{comment} [CodeGuard Protection]",
            f"{comment} Feature: {feature_name}",
            f"{comment} Status: Completed",
            f"{comment} Protected: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{comment} ============================================================",
            "",
        ]
    )
    target.write_text(marker + content, encoding="utf-8", newline="\n")

    records = load_records()
    records[f"{target}:{feature_name}"] = {
        "file_path": str(target),
        "feature_name": feature_name,
        "action": "add_protection",
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "file_hash": get_file_hash(target),
    }
    save_records(records)
    print(f"Protection marker added to {target}")
    return True


def check_protection(file_path: str) -> None:
    target = Path(file_path)
    if not target.exists():
        print(f"File not found: {target}")
        return

    lines = target.read_text(encoding="utf-8").splitlines()
    matches = []
    for line_number, line in enumerate(lines, start=1):
        if "Feature Protection:" in line or "Feature:" in line and "[CodeGuard Protection]" not in line:
            matches.append((line_number, line.strip()))

    if "[CodeGuard Protection]" in target.read_text(encoding="utf-8"):
        print(f"{target} contains CodeGuard markers.")
    if matches:
        for line_number, line in matches:
            print(f"  line {line_number}: {line}")
    elif "[CodeGuard Protection]" not in target.read_text(encoding="utf-8"):
        print(f"{target} has no protection markers.")


def detect_regions(lines: list[str], suffix: str) -> list[dict]:
    patterns = {
        ".js": [r"function\s+(\w+)", r"class\s+(\w+)", r"const\s+(\w+)\s*=\s*\("],
        ".ts": [r"function\s+(\w+)", r"class\s+(\w+)", r"const\s+(\w+)\s*=\s*\("],
        ".py": [r"def\s+(\w+)", r"class\s+(\w+)"],
        ".java": [r"class\s+(\w+)", r"(?:public|private|protected)?\s+\w+\s+(\w+)\s*\("],
        ".html": [r"function\s+(\w+)"],
    }
    use_patterns = patterns.get(suffix, patterns[".js"])

    regions = []
    current_name = None
    current_start = None
    for index, line in enumerate(lines, start=1):
        for pattern in use_patterns:
            match = re.search(pattern, line)
            if match:
                name = next(group for group in match.groups() if group)
                if current_name is not None:
                    regions.append(
                        {"name": current_name, "start": current_start, "end": index - 1, "type": "symbol"}
                    )
                current_name = name
                current_start = index
                break

    if current_name is not None:
        regions.append({"name": current_name, "start": current_start, "end": len(lines), "type": "symbol"})
    return regions


def build_index(comment: str, file_path: Path, regions: list[dict]) -> str:
    lines = [
        f"{comment} ==================== {INDEX_HEADER} ====================",
        f"{comment} File: {file_path}",
        f"{comment} Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"{comment} Total Regions: {len(regions)}",
        f"{comment}",
    ]
    for idx, region in enumerate(regions, start=1):
        lines.append(
            f"{comment} Region {idx}: {region['name']} (Lines {region['start']}-{region['end']})"
        )
    lines.extend(
        [
            f"{comment}",
            f"{comment} ==================== {INDEX_HEADER} ====================",
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
    remainder = lines[end:]
    return "\n".join(remainder).lstrip("\n")


def analyze_code(file_path: str, regenerate: bool = False) -> None:
    target = Path(file_path)
    if not target.exists():
        print(f"File not found: {target}")
        return

    content = target.read_text(encoding="utf-8")
    if regenerate:
        content = strip_existing_index(content)

    lines = content.splitlines()
    comment = get_comment(target)
    regions = detect_regions(lines, target.suffix.lower())
    index = build_index(comment, target, regions)
    target.write_text(index + content, encoding="utf-8", newline="\n")
    print(f"Indexed {len(regions)} region(s) in {target}")


def installed_skill_candidates(skills_root: Path) -> list[Path]:
    return [
        skills_root / "codeguard-skill" / "SKILL.md",
        skills_root / "codeguard-skill.md",
    ]


def show_status() -> None:
    init_config()
    print("=" * 60)
    print("CodeGuard Global Status")
    print("=" * 60)
    print(f"Config directory: {CONFIG_DIR}")
    print(f"Records file: {RECORDS_FILE}")
    print(f"Records stored: {len(load_records())}")

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    system = platform.system().lower()
    if system not in {"windows", "darwin", "linux"}:
        system = "linux"
    ide_paths = config.get("ide_paths", {}).get(system, {})

    print("\nDetected IDE installs:")
    for ide_name, raw_paths in ide_paths.items():
        paths = raw_paths if isinstance(raw_paths, list) else [raw_paths]
        installed = False
        resolved = []
        for raw_path in paths:
            skills_root = Path(os.path.expandvars(os.path.expanduser(raw_path)))
            resolved.append(skills_root.as_posix())
            if any(candidate.exists() for candidate in installed_skill_candidates(skills_root)):
                installed = True
        status = "Installed" if installed else "Not installed"
        print(f"  {ide_name}: {status}")
        for resolved_path in resolved:
            print(f"    - {resolved_path}")


def help() -> None:
    print(
        """CodeGuard CLI - Global Code Protection Tool

Usage:
  codeguard <command> [arguments]

Commands:
  add <file> <feature>     Add protection mark to a file
  check <file>             Check protection markers in a file
  analyze <file>           Insert a code navigation index
  index <file>             Regenerate a code navigation index
  status                   Show global installation status
  help                     Show this help
"""
    )


def main() -> None:
    init_config()

    if len(sys.argv) < 2:
        help()
        return

    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) >= 4:
        add_protection_mark(sys.argv[2], sys.argv[3])
    elif cmd == "check" and len(sys.argv) >= 3:
        check_protection(sys.argv[2])
    elif cmd == "analyze" and len(sys.argv) >= 3:
        analyze_code(sys.argv[2], regenerate=False)
    elif cmd == "index" and len(sys.argv) >= 3:
        analyze_code(sys.argv[2], regenerate=True)
    elif cmd == "status":
        show_status()
    elif cmd in {"help", "-h", "--help"}:
        help()
    else:
        print("Unknown command.")
        help()


if __name__ == "__main__":
    main()

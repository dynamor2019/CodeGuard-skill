#!/usr/bin/env python3
"""Global CodeGuard launcher that forwards to the local project bundle."""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

VERSION = "1.4.0"
CONFIG_DIR = Path.home() / ".codeguard"
CONFIG_FILE = CONFIG_DIR / "config.json"

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

LOCAL_COMMANDS = {
    "init",
    "add",
    "index",
    "show-index",
    "validate-index",
    "backup",
    "confirm",
    "snapshot",
    "rollback",
    "list",
    "status",
    "doctor",
    "batch",
    "schema",
}


def init_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        return

    default_config = {
        "version": VERSION,
        "installed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "ide_paths": IDE_PATHS,
    }
    CONFIG_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def current_system() -> str:
    name = platform.system().lower()
    if name == "windows":
        return "windows"
    if name == "darwin":
        return "darwin"
    return "linux"


def installed_skill_candidates(skills_root: Path) -> list[Path]:
    return [
        skills_root / "codeguard-skill" / "SKILL.md",
        skills_root / "codeguard-skill.md",
    ]


def find_project_script(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        script = candidate / "scripts" / "codeguard.py"
        if script.exists():
            return script
    return None


def show_status() -> None:
    init_config()
    print("=" * 60)
    print("CodeGuard Global Status")
    print("=" * 60)
    print(f"Launcher version: {VERSION}")
    print(f"Config directory: {CONFIG_DIR}")
    print(f"Config file: {CONFIG_FILE}")

    local_script = find_project_script()
    if local_script is None:
        print("Project-local script: not found from the current working directory")
    else:
        print(f"Project-local script: {local_script.as_posix()}")

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    ide_paths = config.get("ide_paths", {}).get(current_system(), {})

    print("")
    print("Detected IDE installs:")
    for ide_name, raw_paths in ide_paths.items():
        paths = raw_paths if isinstance(raw_paths, list) else [raw_paths]
        installed = False
        resolved_paths: list[str] = []
        for raw_path in paths:
            skills_root = Path(os.path.expandvars(os.path.expanduser(raw_path)))
            resolved_paths.append(skills_root.as_posix())
            if any(candidate.exists() for candidate in installed_skill_candidates(skills_root)):
                installed = True

        print(f"  {ide_name}: {'Installed' if installed else 'Not installed'}")
        for resolved in resolved_paths:
            print(f"    - {resolved}")


def help_text() -> None:
    print(
        """CodeGuard - Global Launcher

Usage:
  codeguard <command> [arguments]

Global commands:
  status                  Show launcher and IDE installation status
  help                    Show this help
  --version               Show launcher version

Project-local passthrough commands:
  init
  add
  index
  show-index
  validate-index
  backup
  confirm
  snapshot
  rollback
  list
  status
  doctor
  batch
  schema

Notes:
  - The single official implementation lives in scripts/codeguard.py inside the project.
  - This launcher forwards project commands to that local script.
  - For files over 200 lines, generate or update the feature index only after user approval.
"""
    )


def run_local_command(arguments: list[str]) -> int:
    script = find_project_script()
    if script is None:
        print(
            "Could not find scripts/codeguard.py in the current directory or any parent directory."
        )
        print(
            "Run this command inside a project that contains the CodeGuard skill bundle, "
            "or use `codeguard status` to inspect the installation."
        )
        return 1

    result = subprocess.run([sys.executable, str(script), *arguments], check=False)
    return result.returncode


def main() -> int:
    init_config()

    if len(sys.argv) < 2:
        help_text()
        return 0

    command = sys.argv[1]
    if command in {"help", "-h", "--help"}:
        help_text()
        return 0
    if command == "--version":
        print(f"codeguard {VERSION}")
        return 0
    if command == "status":
        show_status()
        return 0
    if command in LOCAL_COMMANDS:
        return run_local_command(sys.argv[1:])

    print("Unknown command.")
    help_text()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

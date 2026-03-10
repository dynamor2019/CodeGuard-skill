#!/usr/bin/env python3
"""Install the canonical CodeGuard skill bundle into local IDE skill folders."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
from pathlib import Path

SKILL_NAME = "codeguard-skill"
TRAE_REGISTRY_FILE = Path(".trae/skills/codeguard-skill.json")
SKILL_BUNDLE_FILES = [
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("README.md"),
    Path("LICENSE"),
    Path("scripts/codeguard_v2.py"),
    Path("scripts/codeguard-v2.py"),
    Path("scripts/codeguard-cli.py"),
]

IDE_CANDIDATES = {
    "windows": {
        "trae-cn": [
            Path(os.path.expandvars(r"%USERPROFILE%\.trae-cn\claude\skills")),
            Path(os.path.expandvars(r"%USERPROFILE%\.trae-cn\skills")),
        ],
        "trae": [
            Path(os.path.expandvars(r"%USERPROFILE%\.trae\claude\skills")),
            Path(os.path.expandvars(r"%USERPROFILE%\.trae\skills")),
        ],
        "cursor": [Path(os.path.expandvars(r"%USERPROFILE%\.cursor\skills"))],
        "vscode": [Path(os.path.expandvars(r"%USERPROFILE%\.vscode\skills"))],
    },
    "darwin": {
        "trae-cn": [Path.home() / ".trae-cn" / "skills"],
        "trae": [Path.home() / ".trae" / "skills"],
        "cursor": [Path.home() / ".cursor" / "skills"],
        "vscode": [Path.home() / ".vscode" / "skills"],
    },
    "linux": {
        "trae-cn": [Path.home() / ".trae-cn" / "skills"],
        "trae": [Path.home() / ".trae" / "skills"],
        "cursor": [Path.home() / ".cursor" / "skills"],
        "vscode": [Path.home() / ".vscode" / "skills"],
    },
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def current_system() -> str:
    name = platform.system().lower()
    if name == "windows":
        return "windows"
    if name == "darwin":
        return "darwin"
    return "linux"


def copy_relative_file(source_root: Path, relative_path: Path, target_root: Path, dry_run: bool) -> None:
    source = source_root / relative_path
    destination = target_root / relative_path
    if not source.exists():
        raise FileNotFoundError(f"Required file not found: {source}")
    print(f"  copy {relative_path.as_posix()} -> {destination.as_posix()}")
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def pick_target_for_ide(ide_name: str, create_if_missing: bool) -> Path | None:
    candidates = IDE_CANDIDATES[current_system()].get(ide_name, [])
    if not candidates:
        return None

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0] if create_if_missing else None


def install_bundle_to_skills_dir(
    skills_dir: Path,
    *,
    include_trae_registry: bool = False,
    dry_run: bool = False,
) -> Path:
    source_root = repo_root()
    bundle_root = skills_dir / SKILL_NAME
    print(f"Installing CodeGuard bundle into {bundle_root.as_posix()}")
    if not dry_run:
        bundle_root.mkdir(parents=True, exist_ok=True)

    for relative_path in SKILL_BUNDLE_FILES:
        copy_relative_file(source_root, relative_path, bundle_root, dry_run)

    if include_trae_registry:
        registry_source = source_root / TRAE_REGISTRY_FILE
        registry_target = skills_dir / TRAE_REGISTRY_FILE.name
        print(f"  copy {TRAE_REGISTRY_FILE.as_posix()} -> {registry_target.as_posix()}")
        if not dry_run:
            registry_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(registry_source, registry_target)

    return bundle_root


def install_global_cli(dry_run: bool = False) -> Path:
    source = repo_root() / "cli" / "codeguard_cli.py"
    system = current_system()
    if system == "windows":
        bin_dir = Path(os.path.expandvars(r"%USERPROFILE%\.codeguard\bin"))
        script_target = bin_dir / "codeguard.py"
        launcher_target = bin_dir / "codeguard.bat"
        print(f"Installing global CLI into {bin_dir.as_posix()}")
        if not dry_run:
            bin_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, script_target)
            launcher_target.write_text(f'@echo off\npython "{script_target}" %*\n', encoding="utf-8")
        return script_target

    bin_dir = Path.home() / ".local" / "bin"
    target = bin_dir / "codeguard"
    print(f"Installing global CLI into {bin_dir.as_posix()}")
    if not dry_run:
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(0o755)
    return target


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install CodeGuard into IDE skill folders.")
    parser.add_argument(
        "--ide",
        choices=["all", "trae", "trae-cn", "cursor", "vscode"],
        default="all",
        help="IDE family to target. Defaults to all detected IDEs.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Explicit skills directory to install into. Repeat for multiple directories.",
    )
    parser.add_argument(
        "--install-cli",
        action="store_true",
        help="Also install the legacy global CLI launcher.",
    )
    parser.add_argument(
        "--trae-registry",
        action="store_true",
        help="Copy the Trae registry json next to the installed skill bundle.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing files.",
    )
    return parser.parse_args(argv)


def selected_ides(ide_flag: str) -> list[str]:
    if ide_flag == "all":
        return list(IDE_CANDIDATES[current_system()].keys())
    return [ide_flag]


def install_to_targets(args: argparse.Namespace) -> list[Path]:
    installed: list[Path] = []
    explicit_targets = [Path(value).expanduser() for value in args.target]

    for target in explicit_targets:
        installed.append(
            install_bundle_to_skills_dir(
                target,
                include_trae_registry=args.trae_registry,
                dry_run=args.dry_run,
            )
        )

    if explicit_targets:
        return installed

    found = False
    for ide_name in selected_ides(args.ide):
        skills_dir = pick_target_for_ide(ide_name, create_if_missing=args.ide != "all")
        if skills_dir is None:
            continue
        found = True
        include_registry = args.trae_registry or ide_name.startswith("trae")
        print(f"Detected {ide_name} skills dir: {skills_dir.as_posix()}")
        installed.append(
            install_bundle_to_skills_dir(
                skills_dir,
                include_trae_registry=include_registry,
                dry_run=args.dry_run,
            )
        )

    if not found:
        raise SystemExit(
            "No supported IDE skills directory was detected. Use --target <skills-dir> to install manually."
        )

    return installed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    installed = install_to_targets(args)

    if args.install_cli:
        cli_target = install_global_cli(dry_run=args.dry_run)
        print(f"Global CLI target: {cli_target.as_posix()}")

    print("")
    print("Installed skill bundle(s):")
    for path in installed:
        print(f"  - {path.as_posix()}")
    if args.dry_run:
        print("Dry run only. No files were written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

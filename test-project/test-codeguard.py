#!/usr/bin/env python3
"""Regression tests for the project-local CodeGuard workflow."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from codeguard import (  # noqa: E402
    apply_feature_index,
    backup_before_modification,
    calculate_hash,
    check_conflict,
    confirm_modification,
    create_manual_snapshot,
    create_version_snapshot,
    get_current_state,
    get_feature_index,
    get_temp_backup_path,
    init_codeguard,
    is_index_required,
    list_versions,
    load_index,
    rollback,
    validate_feature_index,
)


def write_large_python_file(path: Path, total_lines: int = 230) -> None:
    lines = [
        "#!/usr/bin/env python3",
        "",
        "def bootstrap():",
        "    return 'ready'",
        "",
        "class Workflow:",
        "    def run(self):",
        "        return 'ok'",
        "",
    ]
    while len(lines) < total_lines:
        lines.append(f"value_{len(lines)} = {len(lines)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class CodeGuardTests(unittest.TestCase):
    def test_init_creates_expected_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cg_path = init_codeguard(tmpdir)
            self.assertTrue(Path(cg_path).exists())
            self.assertTrue(Path(tmpdir, ".codeguard", "versions").exists())
            self.assertTrue(Path(tmpdir, ".codeguard", "temp").exists())
            self.assertTrue(Path(tmpdir, ".codeguard", "records").exists())
            self.assertTrue(Path(tmpdir, ".codeguard", "index.json").exists())

    def test_add_protection_creates_snapshot_and_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Hello World\n", encoding="utf-8")

            snapshot = create_version_snapshot(target, "Test Feature", tmpdir)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["version"], 1)
            self.assertEqual(snapshot["feature"], "Test Feature")

            content = target.read_text(encoding="utf-8")
            self.assertIn("[CodeGuard Protection]", content)
            self.assertIn("Feature: Test Feature", content)
            self.assertIn("Version: 1", content)
            self.assertTrue(Path(snapshot["backup_path"]).exists())
            self.assertEqual(calculate_hash(target), snapshot["hash"])

    def test_marker_refresh_still_works_after_feature_index_is_inserted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "script.py")
            target.write_text("print('hello')\n", encoding="utf-8")

            first = create_version_snapshot(target, "Greeting", tmpdir)
            self.assertIsNotNone(first)

            updated_entries = apply_feature_index(target, [("Output logic", 8)], tmpdir)
            self.assertIsNotNone(updated_entries)

            second = create_version_snapshot(target, "Greeting", tmpdir)
            self.assertIsNotNone(second)
            self.assertEqual(second["version"], 2)

            content = target.read_text(encoding="utf-8")
            self.assertEqual(content.count("[CodeGuard Protection]"), 1)
            self.assertIn("Version: 2", content)

    def test_confirm_success_updates_current_state_without_creating_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Initial content\n", encoding="utf-8")

            create_version_snapshot(target, "Test Feature", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text(
                target.read_text(encoding="utf-8") + "Updated implementation\n",
                encoding="utf-8",
            )

            confirmed = confirm_modification(target, "Test Feature", "Refine implementation", True, tmpdir)
            self.assertTrue(confirmed)
            self.assertFalse(get_temp_backup_path(target, tmpdir).exists())

            index = load_index(tmpdir)
            self.assertEqual(len(index["versions"]["test.txt"]), 1)

            current_state = get_current_state(target, tmpdir)
            self.assertIsNotNone(current_state)
            self.assertEqual(current_state["source"], "confirm")
            self.assertEqual(current_state["reason"], "Refine implementation")
            self.assertEqual(current_state["hash"], calculate_hash(target))

            record_path = Path(tmpdir, ".codeguard", "records", "modifications.md")
            self.assertTrue(record_path.exists())
            self.assertIn("Refine implementation", record_path.read_text(encoding="utf-8"))

    def test_manual_snapshot_creates_new_important_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Version 1\n", encoding="utf-8")

            create_version_snapshot(target, "Feature", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text("Version 1\nVersion 1.1\n", encoding="utf-8")
            confirm_modification(target, "Feature", "User accepted revision", True, tmpdir)

            snapshot = create_manual_snapshot(target, "Feature", "Milestone approved", tmpdir)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["version"], 2)
            self.assertEqual(snapshot["reason"], "Milestone approved")

            versions = list_versions(target, tmpdir)
            self.assertEqual([item["version"] for item in versions], [1, 2])

            current_state = get_current_state(target, tmpdir)
            self.assertEqual(current_state["source"], "snapshot")

    def test_confirm_failure_keeps_backup_and_skips_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Initial content\n", encoding="utf-8")

            create_version_snapshot(target, "Test Feature", tmpdir)
            before_state = get_current_state(target, tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text("Broken implementation\n", encoding="utf-8")

            confirmed = confirm_modification(target, "Test Feature", "Attempted fix", False, tmpdir)
            self.assertFalse(confirmed)
            self.assertTrue(get_temp_backup_path(target, tmpdir).exists())
            self.assertFalse(Path(tmpdir, ".codeguard", "records", "modifications.md").exists())
            self.assertEqual(get_current_state(target, tmpdir), before_state)

    def test_backup_after_confirm_does_not_raise_false_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Initial content\n", encoding="utf-8")

            create_version_snapshot(target, "Test Feature", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text("Initial content\nConfirmed update\n", encoding="utf-8")
            confirm_modification(target, "Test Feature", "User accepted update", True, tmpdir)

            backup_path = backup_before_modification(target, tmpdir)
            self.assertIsNotNone(backup_path)
            self.assertTrue(Path(backup_path).exists())
            self.assertFalse(check_conflict(target, tmpdir))

    def test_large_files_require_feature_index_before_snapshot_or_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "large.py")
            write_large_python_file(target)

            self.assertTrue(is_index_required(target, tmpdir))
            self.assertIsNone(create_version_snapshot(target, "Large Feature", tmpdir))
            self.assertIsNone(backup_before_modification(target, tmpdir))
            self.assertFalse(confirm_modification(target, "Large Feature", "No index yet", True, tmpdir))

            updated_entries = apply_feature_index(
                target,
                [("Workflow entry", 3), ("State updates", 6), ("Generated data", 25)],
                tmpdir,
            )
            self.assertIsNotNone(updated_entries)
            self.assertTrue(validate_feature_index(target, tmpdir, quiet=True))

            snapshot = create_version_snapshot(target, "Large Feature", tmpdir)
            self.assertIsNotNone(snapshot)

    def test_apply_feature_index_sorts_entries_and_keeps_it_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "large.py")
            write_large_python_file(target)

            applied = apply_feature_index(
                target,
                [("Generated data", 25), ("Workflow entry", 3), ("State updates", 6)],
                tmpdir,
            )
            self.assertIsNotNone(applied)

            entries = get_feature_index(target, tmpdir)
            self.assertEqual([label for label, _ in entries], ["Workflow entry", "State updates", "Generated data"])
            self.assertTrue(validate_feature_index(target, tmpdir, quiet=True))

    def test_same_basename_in_different_directories_does_not_collide(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first_dir = Path(tmpdir, "one")
            second_dir = Path(tmpdir, "two")
            first_dir.mkdir()
            second_dir.mkdir()

            first = first_dir / "same.js"
            second = second_dir / "same.js"
            first.write_text("console.log('one');\n", encoding="utf-8")
            second.write_text("console.log('two');\n", encoding="utf-8")

            first_snapshot = create_version_snapshot(first, "Feature One", tmpdir)
            second_snapshot = create_version_snapshot(second, "Feature Two", tmpdir)

            index = load_index(tmpdir)
            self.assertIn("one/same.js", index["versions"])
            self.assertIn("two/same.js", index["versions"])
            self.assertNotEqual(first_snapshot["backup_path"], second_snapshot["backup_path"])

    def test_legacy_protection_marker_is_not_wrapped_with_duplicate_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "legacy.html")
            original = (
                "<!-- ==================== Feature Protection Mark ==================== -->\n"
                "<!-- Feature Name: Legacy Feature -->\n"
                "<!-- Status: Completed (Do not modify without authorization) -->\n"
                "<!-- Author: wu -->\n"
                "<!-- Completed Date: 2026-03-02 -->\n"
                "<!-- Modification Approval: Contact author before modifying -->\n"
                "<!-- ==================== Feature Protection Mark ==================== -->\n"
                "<html></html>\n"
            )
            target.write_text(original, encoding="utf-8")

            snapshot = create_version_snapshot(target, "Legacy Feature", tmpdir)

            self.assertIsNotNone(snapshot)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertNotIn("[CodeGuard Protection]", target.read_text(encoding="utf-8"))
            self.assertEqual(len(load_index(tmpdir)["versions"]["legacy.html"]), 1)

    def test_rollback_restores_requested_manual_snapshot_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Version 1\n", encoding="utf-8")

            create_version_snapshot(target, "Feature", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text("Version 1\nVersion 2\n", encoding="utf-8")
            confirm_modification(target, "Feature", "Accepted version 2", True, tmpdir)
            create_manual_snapshot(target, "Feature", "Milestone v2", tmpdir)
            target.write_text("Broken version\n", encoding="utf-8")

            rolled_back = rollback(target, version=1, project_path=tmpdir, force=True)
            self.assertTrue(rolled_back)
            restored = target.read_text(encoding="utf-8")
            self.assertIn("Version 1", restored)
            self.assertNotIn("Broken version", restored)

    def test_compatibility_cli_record_is_success_only_alias_for_confirm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "sample.js")
            target.write_text("function hello() { return 1; }\n", encoding="utf-8")
            cli_path = Path(__file__).resolve().parents[1] / "scripts" / "codeguard-cli.py"

            add_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "add",
                    str(target),
                    "Sample Feature",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(add_result.returncode, 0, add_result.stdout + add_result.stderr)

            backup_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "backup",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(backup_result.returncode, 0, backup_result.stdout + backup_result.stderr)

            target.write_text(
                target.read_text(encoding="utf-8") + "function world() { return 2; }\n",
                encoding="utf-8",
            )

            record_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "record",
                    str(target),
                    "Sample Feature",
                    "User confirmed the helper addition",
                    "Legacy approach metadata",
                    "true",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(record_result.returncode, 0, record_result.stdout + record_result.stderr)
            self.assertIn("success only", record_result.stdout.lower())

            record_path = Path(tmpdir, ".codeguard", "records", "modifications.md")
            self.assertTrue(record_path.exists())
            self.assertIn("User confirmed the helper addition", record_path.read_text(encoding="utf-8"))

            index = load_index(tmpdir)
            self.assertEqual(len(index["versions"]["sample.js"]), 1)

            snapshot_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "snapshot",
                    str(target),
                    "Sample Feature",
                    "Important milestone",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(snapshot_result.returncode, 0, snapshot_result.stdout + snapshot_result.stderr)

            index = load_index(tmpdir)
            self.assertEqual(len(index["versions"]["sample.js"]), 2)

    def test_compatibility_cli_index_and_check_follow_feature_index_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "large.py")
            write_large_python_file(target)
            cli_path = Path(__file__).resolve().parents[1] / "scripts" / "codeguard-cli.py"

            analyze_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "analyze",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(analyze_result.returncode, 0)
            self.assertIn("removed", analyze_result.stdout.lower())

            index_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "index",
                    str(target),
                    "--entry",
                    "Generated data:25",
                    "--entry",
                    "Workflow entry:3",
                    "--entry",
                    "State updates:6",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(index_result.returncode, 0, index_result.stdout + index_result.stderr)

            check_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "check",
                    str(target),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check_result.returncode, 0, check_result.stdout + check_result.stderr)
            self.assertIn("Feature index valid: yes", check_result.stdout)
            self.assertIn("Feature index entries: 3", check_result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

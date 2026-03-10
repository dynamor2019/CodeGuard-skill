#!/usr/bin/env python3
"""Regression tests for the project-local CodeGuard workflow."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from codeguard_v2 import (  # noqa: E402
    backup_before_modification,
    calculate_hash,
    check_conflict,
    confirm_modification,
    create_version_snapshot,
    get_temp_backup_path,
    init_codeguard,
    list_versions,
    load_index,
    rollback,
)


class CodeGuardV2Tests(unittest.TestCase):
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

    def test_backup_after_add_does_not_raise_false_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Initial content\n", encoding="utf-8")

            create_version_snapshot(target, "Test Feature", tmpdir)
            backup_path = backup_before_modification(target, tmpdir)

            self.assertIsNotNone(backup_path)
            self.assertTrue(Path(backup_path).exists())
            self.assertFalse(check_conflict(target, tmpdir))
            self.assertEqual(Path(backup_path).read_text(encoding="utf-8"), target.read_text(encoding="utf-8"))

    def test_confirm_success_promotes_current_state_and_cleans_temp_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Initial content\n", encoding="utf-8")

            create_version_snapshot(target, "Test Feature", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text(target.read_text(encoding="utf-8") + "Updated implementation\n", encoding="utf-8")

            confirmed = confirm_modification(target, "Test Feature", "Refine implementation", True, tmpdir)
            self.assertTrue(confirmed)
            self.assertFalse(get_temp_backup_path(target, tmpdir).exists())

            index = load_index(tmpdir)
            file_versions = index["versions"]["test.txt"]
            self.assertEqual(len(file_versions), 2)
            self.assertEqual(file_versions[-1]["version"], 2)
            self.assertEqual(file_versions[-1]["reason"], "Refine implementation")
            self.assertEqual(file_versions[-1]["hash"], calculate_hash(target))

            record_path = Path(tmpdir, ".codeguard", "records", "modifications.md")
            self.assertTrue(record_path.exists())
            self.assertIn("Refine implementation", record_path.read_text(encoding="utf-8"))

    def test_confirm_failure_keeps_backup_and_skips_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Initial content\n", encoding="utf-8")

            create_version_snapshot(target, "Test Feature", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text("Broken implementation\n", encoding="utf-8")

            confirmed = confirm_modification(target, "Test Feature", "Attempted fix", False, tmpdir)
            self.assertFalse(confirmed)
            self.assertTrue(get_temp_backup_path(target, tmpdir).exists())
            self.assertFalse(Path(tmpdir, ".codeguard", "records", "modifications.md").exists())

    def test_conflict_detection_only_triggers_on_external_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Initial content\n", encoding="utf-8")

            create_version_snapshot(target, "Test Feature", tmpdir)
            target.write_text("External modification\n", encoding="utf-8")

            self.assertTrue(check_conflict(target, tmpdir))
            self.assertIsNone(backup_before_modification(target, tmpdir))

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

    def test_rollback_restores_requested_version_without_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Version 1\n", encoding="utf-8")

            create_version_snapshot(target, "Feature", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text(target.read_text(encoding="utf-8") + "Version 2\n", encoding="utf-8")
            confirm_modification(target, "Feature", "Add line", True, tmpdir)
            target.write_text("Broken version\n", encoding="utf-8")

            rolled_back = rollback(target, version=1, project_path=tmpdir, force=True)
            self.assertTrue(rolled_back)
            restored = target.read_text(encoding="utf-8")
            self.assertIn("Version 1", restored)
            self.assertNotIn("Broken version", restored)

    def test_list_versions_returns_snapshot_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "test.txt")
            target.write_text("Version 1\n", encoding="utf-8")

            create_version_snapshot(target, "Feature 1", tmpdir)
            backup_before_modification(target, tmpdir)
            target.write_text(target.read_text(encoding="utf-8") + "Version 2\n", encoding="utf-8")
            confirm_modification(target, "Feature 1", "Promote v2", True, tmpdir)

            versions = list_versions(target, tmpdir)
            self.assertEqual(len(versions), 2)
            self.assertEqual([item["version"] for item in versions], [1, 2])

    def test_legacy_cli_add_creates_snapshot_and_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "sample.js")
            target.write_text("function hello() { return 1; }\n", encoding="utf-8")
            cli_path = Path(__file__).resolve().parents[1] / "scripts" / "codeguard-cli.py"

            result = subprocess.run(
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(Path(tmpdir, ".codeguard", "index.json").exists())
            self.assertTrue(Path(tmpdir, ".codeguard-locks.json").exists())
            self.assertIn("[CodeGuard Protection]", target.read_text(encoding="utf-8"))

    def test_legacy_cli_record_and_confirm_use_core_snapshot_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "sample.js")
            target.write_text("function hello() { return 1; }\n", encoding="utf-8")
            cli_path = Path(__file__).resolve().parents[1] / "scripts" / "codeguard-cli.py"

            subprocess.run(
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
                check=True,
            )

            subprocess.run(
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
                check=True,
            )

            target.write_text(target.read_text(encoding="utf-8") + "function world() { return 2; }\n", encoding="utf-8")

            record_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "record",
                    str(target),
                    "Sample Feature",
                    "Refine behavior",
                    "Add helper function",
                    "true",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(record_result.returncode, 0, record_result.stdout + record_result.stderr)
            self.assertTrue(Path(tmpdir, ".codeguard-attempts.json").exists())

            confirm_result = subprocess.run(
                [
                    sys.executable,
                    str(cli_path),
                    "--project",
                    tmpdir,
                    "confirm",
                    str(target),
                    "Sample Feature",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(confirm_result.returncode, 0, confirm_result.stdout + confirm_result.stderr)
            self.assertFalse(Path(tmpdir, ".codeguard-attempts.json").exists())
            self.assertTrue(Path(tmpdir, ".codeguard", "records", "modifications.md").exists())
            self.assertTrue(Path(tmpdir, "codeguard-records.md").exists())
            index = load_index(tmpdir)
            self.assertEqual(len(index["versions"]["sample.js"]), 2)

    def test_legacy_cli_analyze_closes_html_comments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir, "sample.html")
            target.write_text(
                "<!DOCTYPE html>\n"
                "<html><body><script>function start() { return 1; }</script></body></html>\n",
                encoding="utf-8",
            )
            cli_path = Path(__file__).resolve().parents[1] / "scripts" / "codeguard-cli.py"

            result = subprocess.run(
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            first_lines = target.read_text(encoding="utf-8").splitlines()[:6]
            self.assertTrue(first_lines[0].endswith("-->"))
            self.assertTrue(first_lines[1].endswith("-->"))
            self.assertIn("Code Functionality Index", first_lines[0])

if __name__ == "__main__":
    unittest.main(verbosity=2)

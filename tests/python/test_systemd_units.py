#!/usr/bin/env python3
"""
Test suite for static validation and custom constraint assertions of systemd unit files.
Ensures 100% of deployed system and user unit files pass structural syntax and security rules.
"""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def get_repo_root() -> Path:
    """Returns the absolute Path to the repository root directory."""
    return Path(__file__).resolve().parents[2]


def parse_unit_file(file_path: Path) -> dict[str, dict[str, list[str]]]:
    """
    Statically parses a systemd unit file into a dictionary of sections and options.
    Handles comment lines, blank lines, and line continuations.
    """
    sections: dict[str, dict[str, list[str]]] = {}
    current_section: str | None = None

    with open(file_path, encoding="utf-8") as file_descriptor:
        raw_lines = file_descriptor.readlines()

    # Consolidate line continuations
    lines: list[str] = []
    continuation_buffer = ""
    for raw_line in raw_lines:
        line = raw_line.strip()
        if continuation_buffer:
            line = continuation_buffer + " " + line
            continuation_buffer = ""

        if line.endswith("\\") and not line.startswith(("#", ";")):
            continuation_buffer = line[:-1].rstrip()
            continue

        lines.append(line)

    if continuation_buffer:
        lines.append(continuation_buffer)

    for line in lines:
        if not line or line.startswith(("#", ";")):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            if current_section not in sections:
                sections[current_section] = {}
            continue

        if current_section is None:
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key not in sections[current_section]:
                sections[current_section][key] = []
            sections[current_section][key].append(value)

    return sections


class TestSystemdUnits(unittest.TestCase):
    """
    Unit test cases for systemd unit file static verification and custom constraint assertions.
    """

    def setUp(self) -> None:
        self.repo_root = get_repo_root()
        self.system_dir = self.repo_root / "src" / "lib" / "systemd" / "system"
        self.user_dir = self.repo_root / "src" / "lib" / "systemd" / "user"

        self.system_unit_paths = sorted(
            list(self.system_dir.glob("*.service"))
            + list(self.system_dir.glob("*.timer"))
            + list(self.system_dir.glob("*.socket"))
        )
        self.user_unit_paths = sorted(
            list(self.user_dir.glob("*.service"))
            + list(self.user_dir.glob("*.timer"))
            + list(self.user_dir.glob("*.socket"))
        )
        self.all_unit_paths = self.system_unit_paths + self.user_unit_paths

    def test_unit_files_count(self) -> None:
        """
        Verify that all expected system and user unit files exist in the repository.
        Expected at least 40 unit files total across system and user scopes.
        """
        self.assertGreaterEqual(
            len(self.all_unit_paths),
            40,
            f"Expected at least 40 unit files, found {len(self.all_unit_paths)}.",
        )
        self.assertGreaterEqual(len(self.system_unit_paths), 25)
        self.assertGreaterEqual(len(self.user_unit_paths), 8)

    def test_native_systemd_analyze_verify(self) -> None:
        """
        Runs systemd-analyze verify (if available) against all unit files.
        Ensures zero structural syntax errors or invalid directive warnings.
        """
        systemd_analyze = shutil.which("systemd-analyze")
        if not systemd_analyze:
            self.skipTest("systemd-analyze utility is not available in host environment.")

        unit_file_strings = [str(p) for p in self.all_unit_paths]
        command = [systemd_analyze, "verify", "--man=no"] + unit_file_strings

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        stderr_lines = process.stderr.splitlines()
        syntax_errors: list[str] = []

        # Filter out expected missing binary execution warnings in test environment
        ignore_patterns = [
            r"is not executable",
            r"Permission denied",
            r"Failed to create .* control group",
            r"Cannot determine cgroup",
        ]

        for line in stderr_lines:
            line_str = line.strip()
            if not line_str:
                continue
            if any(re.search(pat, line_str) for pat in ignore_patterns):
                continue
            syntax_errors.append(line_str)

        self.assertEqual(
            len(syntax_errors),
            0,
            "systemd-analyze verify reported syntax errors or warnings:\n"
            + "\n".join(syntax_errors),
        )

    def test_structural_syntax_parsing(self) -> None:
        """
        Statically parses all system and user unit files.
        Validates section structure and boolean values for hardened directives.
        """
        valid_booleans = {"yes", "no", "true", "false", "1", "0", "on", "off"}

        for unit_path in self.all_unit_paths:
            parsed = parse_unit_file(unit_path)
            self.assertTrue(
                len(parsed) > 0,
                f"Unit file '{unit_path.name}' is empty or contains no valid section headers.",
            )

            if "Service" in parsed:
                service_sec = parsed["Service"]

                # Validate ProtectControlGroups if present
                if "ProtectControlGroups" in service_sec:
                    for val in service_sec["ProtectControlGroups"]:
                        self.assertIn(
                            val.lower(),
                            valid_booleans,
                            f"Unit file '{unit_path.name}' has invalid ProtectControlGroups value '{val}'. Must be a boolean.",
                        )

                # Validate PrivateTmp if present
                if "PrivateTmp" in service_sec:
                    for val in service_sec["PrivateTmp"]:
                        self.assertIn(
                            val.lower(),
                            valid_booleans,
                            f"Unit file '{unit_path.name}' has invalid PrivateTmp value '{val}'.",
                        )

    def assert_no_private_tmp_in_user_scope(self, unit_path: Path) -> None:
        """
        Custom constraint assertion: Rejects user-scope unit files containing PrivateTmp directives.
        """
        parsed = parse_unit_file(unit_path)
        if "Service" in parsed and "PrivateTmp" in parsed["Service"]:
            values = [v.lower() for v in parsed["Service"]["PrivateTmp"]]
            if any(v in {"yes", "true", "1", "on"} for v in values):
                raise AssertionError(
                    f"User-scope unit file '{unit_path.name}' illegally contains PrivateTmp directive. "
                    "Private temporary directory isolation is unsupported in systemd user scope."
                )

    def test_user_scope_no_private_tmp_constraint(self) -> None:
        """
        Verify that no deployed user-scope unit file contains PrivateTmp directives.
        """
        for user_unit_path in self.user_unit_paths:
            self.assert_no_private_tmp_in_user_scope(user_unit_path)

    def test_user_scope_private_tmp_rejection_assertion(self) -> None:
        """
        Asserts that the custom constraint checker correctly identifies and rejects
        user-scope unit files with isolated temporary directory directives.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_unit_path = Path(temp_dir) / "invalid-user-service.service"
            bad_unit_path.write_text(
                "[Unit]\nDescription=Invalid User Service\n\n[Service]\nExecStart=/bin/true\nPrivateTmp=yes\n",
                encoding="utf-8",
            )
            with self.assertRaises(AssertionError) as context:
                self.assert_no_private_tmp_in_user_scope(bad_unit_path)
            self.assertIn("PrivateTmp", str(context.exception))

    def assert_container_service_notification_flags(self, unit_path: Path) -> None:
        """
        Custom constraint assertion: Rejects container services configured with Type=notify
        if required notification flags (--sdnotify) are missing from ExecStart.
        """
        parsed = parse_unit_file(unit_path)
        if "Service" not in parsed:
            return

        service_sec = parsed["Service"]
        service_type = service_sec.get("Type", [""])[0].lower()
        if service_type != "notify":
            return

        exec_start_lines = service_sec.get("ExecStart", [])
        exec_start_str = " ".join(exec_start_lines)

        # Check if service invokes container engines (podman / docker)
        is_container_service = any(
            cmd in exec_start_str for cmd in ["podman", "docker"]
        ) or "container-" in unit_path.name

        if is_container_service:
            has_sdnotify = "--sdnotify" in exec_start_str
            if not has_sdnotify:
                raise AssertionError(
                    f"Container service '{unit_path.name}' configured with Type=notify "
                    "lacks required container notification flag (--sdnotify) in ExecStart."
                )

    def test_container_service_notification_flags_constraint(self) -> None:
        """
        Verify that all deployed container services with Type=notify pass verification
        and contain required notification command flags.
        """
        for unit_path in self.all_unit_paths:
            self.assert_container_service_notification_flags(unit_path)

    def test_container_service_missing_notify_flag_rejection_assertion(self) -> None:
        """
        Asserts that the custom constraint checker correctly rejects container services
        configured with Type=notify when required notification flags are missing.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_unit_path = Path(temp_dir) / "container-test.service"
            bad_unit_path.write_text(
                "[Unit]\nDescription=Bad Container Service\n\n[Service]\nType=notify\nExecStart=/usr/bin/podman start --attach test\n",
                encoding="utf-8",
            )
            with self.assertRaises(AssertionError) as context:
                self.assert_container_service_notification_flags(bad_unit_path)
            self.assertIn("lacks required container notification flag", str(context.exception))

    def test_network_service_isolation_flags(self) -> None:
        """
        Verify that background network server services do not have broken network isolation flags (PrivateNetwork=yes).
        """
        network_services = ["rest-server.service", "restic-rest-server.service"]
        for unit_path in self.all_unit_paths:
            if unit_path.name in network_services:
                parsed = parse_unit_file(unit_path)
                if "Service" in parsed and "PrivateNetwork" in parsed["Service"]:
                    values = [v.lower() for v in parsed["Service"]["PrivateNetwork"]]
                    self.assertNotIn(
                        "yes",
                        values,
                        f"Network service '{unit_path.name}' has broken network isolation PrivateNetwork=yes.",
                    )

    def test_snapshot_and_path_lock_conflicts(self) -> None:
        """
        Verify that snapshot and backup background services do not contain conflicting ReadOnlyPaths=/ path locks.
        """
        backup_services = ["catstar-backup.service", "minecraft-scheduled-restart@.service"]
        for unit_path in self.all_unit_paths:
            if unit_path.name in backup_services:
                parsed = parse_unit_file(unit_path)
                if "Service" in parsed and "ReadOnlyPaths" in parsed["Service"]:
                    values = parsed["Service"]["ReadOnlyPaths"]
                    self.assertNotIn(
                        "/",
                        values,
                        f"Service '{unit_path.name}' has conflicting ReadOnlyPaths=/ path lock directive.",
                    )


if __name__ == "__main__":
    unittest.main()

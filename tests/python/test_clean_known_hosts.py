"""Unit test suite for scripts/clean_known_hosts.py."""

import io
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts.clean_known_hosts import (
    clean_known_hosts,
    host_matches,
    line_matches,
    normalize_host,
)


class TestCleanKnownHosts(unittest.TestCase):
    def test_normalize_host(self) -> None:
        self.assertEqual(normalize_host("example.com"), "example.com")
        self.assertEqual(normalize_host("[192.168.1.1]:2222"), "192.168.1.1")
        self.assertEqual(normalize_host("[host.example.com]:22"), "host.example.com")

    def test_host_matches_domain_and_subdomain(self) -> None:
        self.assertTrue(host_matches("example.com", "example.com"))
        self.assertTrue(host_matches("sub.example.com", "example.com"))
        self.assertTrue(host_matches("192.168.1.50", "192.168.1."))
        self.assertTrue(host_matches("192.168.1.50", "192.168.1"))

        # False positives should not match
        self.assertFalse(host_matches("badexample.com", "example.com"))
        self.assertFalse(host_matches("example.com.org", "example.com"))

    def test_line_matches(self) -> None:
        self.assertFalse(line_matches("# Comment line", ["example.com"]))
        self.assertFalse(line_matches("", ["example.com"]))

        valid_line = (
            "sub.example.com,192.168.1.1 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI..."
        )
        self.assertTrue(line_matches(valid_line, ["example.com"]))
        self.assertTrue(line_matches(valid_line, ["192.168.1"]))
        self.assertFalse(line_matches(valid_line, ["other.com"]))

    def test_clean_known_hosts_stdout(self) -> None:
        sample_content = (
            "# SSH Known Hosts\n"
            "keep.com ssh-rsa AAAAB3NzaC1...\n"
            "remove.example.com ssh-ed25519 AAAAC3...\n"
        )
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as temp:
            temp.write(sample_content)
            temp_path = temp.name

        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                clean_known_hosts(
                    temp_path, ["example.com"], inplace=False, dry_run=False
                )
                output = mock_stdout.getvalue()
                self.assertIn("keep.com", output)
                self.assertNotIn("remove.example.com", output)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_clean_known_hosts_dry_run(self) -> None:
        sample_content = (
            "keep.com ssh-rsa AAAAB3...\nremove.example.com ssh-ed25519 AAAAC3...\n"
        )
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as temp:
            temp.write(sample_content)
            temp_path = temp.name

        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                clean_known_hosts(
                    temp_path, ["example.com"], inplace=False, dry_run=True
                )
                output = mock_stdout.getvalue()
                self.assertIn("  keep.com ssh-rsa AAAAB3...", output)
                self.assertIn("- remove.example.com ssh-ed25519 AAAAC3...", output)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_clean_known_hosts_inplace(self) -> None:
        sample_content = (
            "keep.com ssh-rsa AAAAB3...\nremove.example.com ssh-ed25519 AAAAC3...\n"
        )
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as temp:
            temp.write(sample_content)
            temp_path = temp.name

        try:
            clean_known_hosts(temp_path, ["example.com"], inplace=True, dry_run=False)
            backup_path = temp_path + ".bak"
            self.assertTrue(os.path.exists(backup_path))

            with open(temp_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("keep.com", content)
            self.assertNotIn("remove.example.com", content)

            os.remove(backup_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()

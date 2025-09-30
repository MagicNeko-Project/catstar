#!/usr/bin/env python3
"""A script to clean entries from a known_hosts file by pattern matching."""

import argparse
import os
import sys
from typing import List, Set

class HostMatcher:
    """Matches host patterns against lines of a known_hosts file."""
    def __init__(self, patterns: List[str]):
        self.patterns = patterns

    def line_matches(self, line: str) -> bool:
        """Checks if a known_hosts line matches any of the patterns."""
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return False  # Keep comments and blank lines

        hosts_field = stripped.split(" ", 1)[0]
        hosts = hosts_field.split(",")
        for h in hosts:
            normalized_host = self._normalize_host(h)
            if self._host_matches(normalized_host):
                return True
        return False

    def _normalize_host(self, raw: str) -> Set[str]:
        """
        Normalizes a host token from a known_hosts file.
        e.g., [host]:port -> host
        """
        if raw.startswith("[") and "]:" in raw:
            raw = raw[1:raw.find("]:")]
        return set(raw.split('.'))

    def _host_matches(self, host: Set[str]) -> bool:
        """Checks if the set of a pattern's components is a subset of the host's."""
        for p in self.patterns:
            sub = set(p.split('.'))
            if not (sub - host):
                return True
        return False

class KnownHostsFile:
    """Manages reading, cleaning, and writing a known_hosts file."""
    def __init__(self, path: str, matcher: HostMatcher):
        self.path = path
        self.matcher = matcher

    def clean(self, inplace: bool, dry_run: bool = False):
        """
        Cleans the file, writing to stdout, modifying in place, or showing a diff.
        """
        try:
            lines = self._read_lines()
        except FileNotFoundError:
            print(f"Error: File not found at {self.path}", file=sys.stderr)
            sys.exit(1)

        if dry_run:
            for line in lines:
                if self.matcher.line_matches(line):
                    sys.stdout.write(f"- {line.strip()}\n")
                else:
                    sys.stdout.write(f"  {line.strip()}\n")
            return

        output_lines = [line for line in lines if not self.matcher.line_matches(line)]

        if inplace:
            self._backup()
            self._write_lines(output_lines)
            print(f"Cleaned file written in place. Backup saved as {self.path}.bak")
        else:
            sys.stdout.writelines(output_lines)

    def _read_lines(self) -> List[str]:
        """Reads all lines from the file."""
        with open(self.path, "r", encoding="utf-8") as f:
            return f.readlines()

    def _write_lines(self, lines: List[str]):
        """Writes lines to the file."""
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def _backup(self):
        """Renames the file to create a backup."""
        backup_path = self.path + ".bak"
        os.rename(self.path, backup_path)

def main():
    """Parses CLI arguments and runs the cleaning process."""
    parser = argparse.ArgumentParser(
        description="Clean entries from ~/.ssh/known_hosts by suffix/domain/IP match."
    )
    parser.add_argument("patterns", nargs="+", help="Domain(s) or IP fragment(s) to remove")
    parser.add_argument(
        "--file", default=os.path.expanduser("~/.ssh/known_hosts"),
        help="Path to known_hosts file (default: ~/.ssh/known_hosts)"
    )
    parser.add_argument(
        "--inplace", action="store_true",
        help="Replace the known_hosts file (a backup is created)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show which lines would be removed without modifying the file."
    )
    args = parser.parse_args()

    matcher = HostMatcher(args.patterns)
    known_hosts = KnownHostsFile(args.file, matcher)
    known_hosts.clean(args.inplace, args.dry_run)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""A script to clean entries from a known_hosts file by pattern matching."""

import argparse
import os
import sys


def normalize_host(raw: str) -> str:
    """Normalizes a host token from a known_hosts file (e.g. [host]:port -> host)."""
    raw = raw.strip()
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    return raw


def host_matches(host: str, pattern: str) -> bool:
    """Checks if a normalized host matches a domain or IP pattern."""
    h = host.lower()
    p = pattern.lower().rstrip(".")
    if not p:
        return False

    if h == p or h.endswith("." + p):
        return True

    # If pattern is an IP prefix (e.g. 192.168.1)
    is_ip_prefix = all(part.isdigit() for part in p.split("."))
    if is_ip_prefix and h.startswith(p + "."):
        return True

    return False


def line_matches(line: str, patterns: list[str]) -> bool:
    """Checks if a known_hosts line matches any of the given patterns."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False

    hosts_field = stripped.split(" ", 1)[0]
    for host_token in hosts_field.split(","):
        normalized = normalize_host(host_token)
        for pattern in patterns:
            if host_matches(normalized, pattern):
                return True
    return False


def clean_known_hosts(
    path: str, patterns: list[str], inplace: bool = False, dry_run: bool = False
) -> None:
    """Cleans matching host entries from a known_hosts file."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: File not found at {path}", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        for line in lines:
            if line_matches(line, patterns):
                sys.stdout.write(f"- {line.strip()}\n")
            else:
                sys.stdout.write(f"  {line.strip()}\n")
        return

    output_lines = [line for line in lines if not line_matches(line, patterns)]

    if inplace:
        backup_path = path + ".bak"
        os.rename(path, backup_path)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(output_lines)
        print(f"Cleaned file written in place. Backup saved as {backup_path}")
    else:
        sys.stdout.writelines(output_lines)


def main():
    """Parses CLI arguments and runs the cleaning process."""
    parser = argparse.ArgumentParser(
        description="Clean entries from ~/.ssh/known_hosts by suffix/domain/IP match."
    )
    parser.add_argument(
        "patterns", nargs="+", help="Domain(s) or IP fragment(s) to remove"
    )
    parser.add_argument(
        "--file",
        default=os.path.expanduser("~/.ssh/known_hosts"),
        help="Path to known_hosts file (default: ~/.ssh/known_hosts)",
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="Replace the known_hosts file (a backup is created).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which lines would be removed without modifying the file.",
    )
    args = parser.parse_args()

    clean_known_hosts(
        args.file, args.patterns, inplace=args.inplace, dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()

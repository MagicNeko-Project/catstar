#!/usr/bin/env python3

"""
Generates random port numbers from predefined ranges (privileged, registered, or ephemeral).
Users can specify one or more ranges using command-line options and choose how many random ports to generate.
By default, generates one ephemeral port if no options are provided.
"""

import argparse
import random
from collections.abc import Iterable

# Predefined port ranges
PORT_RANGES = {
    "privileged": range(1, 1024),
    "registered": range(1024, 49152),
    "ephemeral": range(49152, 65536),
}


def choose_random_ports(ranges: Iterable[str], count: int) -> list[int]:
    """Draws count unique random ports from the combined set of specified ranges."""
    pool = []
    for name in ranges:
        pool.extend(PORT_RANGES[name])

    if count > len(pool):
        raise ValueError(f"Requested {count} ports, but only {len(pool)} available.")

    return random.sample(pool, count)


def main():
    parser = argparse.ArgumentParser(
        description="Generate random port numbers from predefined ranges."
    )
    parser.add_argument(
        "-p",
        "--privileged",
        action="store_true",
        help="Include privileged ports (1-1023).",
    )
    parser.add_argument(
        "-g",
        "--registered",
        action="store_true",
        help="Include registered ports (1024-49151).",
    )
    parser.add_argument(
        "-e",
        "--ephemeral",
        action="store_true",
        help="Include ephemeral ports (49152-65535). Default if no range is specified.",
    )
    parser.add_argument(
        "number",
        nargs="?",
        type=int,
        default=1,
        help="Number of random ports to generate (default: 1).",
    )

    args = parser.parse_args()

    selected_ranges = set()
    if args.privileged:
        selected_ranges.add("privileged")
    if args.registered:
        selected_ranges.add("registered")
    if not selected_ranges or args.ephemeral:
        selected_ranges.add("ephemeral")

    for port in choose_random_ports(selected_ranges, args.number):
        print(port)


if __name__ == "__main__":
    main()

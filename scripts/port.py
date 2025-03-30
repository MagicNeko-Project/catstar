#!/usr/bin/env python3

"""
This script generates random port numbers from predefined ranges (privileged, registered, or ephemeral).
Users can specify one or more ranges using command-line options and also choose how many random ports to generate.
By default, the script generates one ephemeral port if no options are provided.
"""

import argparse
import bisect
import random
from typing import List

# Predefined port ranges
PORT_RANGES = {
    "privileged": range(1, 1023),
    "registered": range(1024, 49151),
    "ephemeral": range(49152, 65535),
}


def choose_random_ports(ranges: List[str], count: int) -> List[int]:
    all_ranges = [PORT_RANGES[name] for name in ranges]
    cumulative = [0]
    for r in all_ranges:
        cumulative.append(cumulative[-1] + len(r))

    total = cumulative[-1]
    if count > total:
        raise ValueError(f"Requested {count} ports, but only {total} available.")

    def resolve_index(i: int) -> int:
        idx = bisect.bisect_right(cumulative, i) - 1
        return all_ranges[idx][i - cumulative[idx]]

    indices = random.sample(range(total), count)
    return [resolve_index(i) for i in indices]


def main():
    parser = argparse.ArgumentParser(
        description="Generate random port numbers from predefined ranges."
    )
    parser.add_argument(
        "-p", "--privileged",
        action="store_true",
        help="Include privileged ports (1-1023)."
    )
    parser.add_argument(
        "-g", "--registered",
        action="store_true",
        help="Include registered ports (1024-49151)."
    )
    parser.add_argument(
        "-e", "--ephemeral",
        action="store_true",
        help="Include ephemeral ports (49152-65535). Default if no range is specified."
    )
    parser.add_argument(
        "number",
        nargs="?",
        type=int,
        default=1,
        help="Number of random ports to generate (default: 1)."
    )

    args = parser.parse_args()

    # Determine selected ranges
    selected_ranges = set()
    if args.privileged:
        selected_ranges.add("privileged")
    if args.registered:
        selected_ranges.add("registered")
    selected_ranges.add("ephemeral") if not selected_ranges or args.ephemeral else None

    for port in choose_random_ports(selected_ranges, args.number):
        print(port)


if __name__ == "__main__":
    main()

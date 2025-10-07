#!/usr/bin/env python3
# This script dumps the contents of a Git repository into a single file.
# It's designed to make it easier to use repository content in RAG systems
# or as part of prompts for Large Language Models (LLMs).
# Copied from https://github.com/artkulak/repo2file
import os
import fnmatch
import argparse
from typing import List, Set, Optional


class RepoScanner:
    """
    A class to scan a repository, filter files, and dump the content to a single file.
    """

    def __init__(self, start_path: str, output_file: str, exclusion_file: Optional[str] = None, file_types: Optional[List[str]] = None):
        self.start_path = start_path
        self.output_file = output_file
        self.exclusion_file = exclusion_file
        self.file_types = file_types
        self.exclusion_patterns = self._parse_exclusion_file()

    def _parse_exclusion_file(self) -> Set[str]:
        """
        Parses an exclusion file (like .gitignore) and returns a set of patterns.
        """
        patterns = set()
        if self.exclusion_file and os.path.exists(self.exclusion_file):
            with open(self.exclusion_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.add(line)
        return patterns

    def _is_excluded(self, path: str) -> bool:
        """
        Checks if a given path matches any of the exclusion patterns.
        """
        for pattern in self.exclusion_patterns:
            if pattern.startswith('/') and pattern.endswith('/'):
                if path.startswith(pattern[1:]) or path == pattern[1:-1]:
                    return True
            elif pattern.endswith('/'):
                if path.startswith(pattern) or path == pattern[:-1]:
                    return True
            elif pattern.startswith('/'):
                if path == pattern[1:] or path.startswith(f"{pattern[1:]}{os.sep}"):
                    return True
            else:
                if fnmatch.fnmatch(path, pattern) or any(fnmatch.fnmatch(part, pattern) for part in path.split(os.sep)):
                    return True
        return False

    def _generate_directory_structure(self) -> str:
        """
        Generates a string representation of the directory structure.
        """
        tree = ['/']

        def _generate_tree(dir_path: str, prefix: str = '') -> None:
            entries = os.listdir(dir_path)
            entries = sorted(entries, key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower()))

            for i, entry in enumerate(entries):
                rel_path = os.path.relpath(os.path.join(dir_path, entry), self.start_path)
                if self._is_excluded(rel_path):
                    continue

                connector = '└── ' if i == len(entries) - 1 else '├── '
                tree.append(f"{prefix}{connector}{entry}")

                full_path = os.path.join(dir_path, entry)
                if os.path.isdir(full_path):
                    new_prefix = f"{prefix}{'    ' if i == len(entries) - 1 else '│   '}"
                    _generate_tree(full_path, new_prefix)

        _generate_tree(self.start_path)
        return '\n'.join(tree)

    def scan_and_dump(self) -> None:
        """
        Scans the repository and writes the directory structure and file contents to the output file.
        """
        with open(self.output_file, 'w', encoding='utf-8') as out_file:
            out_file.write("Directory Structure:\n")
            out_file.write("-------------------\n")
            out_file.write(self._generate_directory_structure())
            out_file.write("\n\n")
            out_file.write("File Contents:\n")
            out_file.write("--------------\n")

            for root, _, files in os.walk(self.start_path):
                rel_path = os.path.relpath(root, self.start_path)
                if self._is_excluded(rel_path):
                    continue

                for file in files:
                    file_rel_path = os.path.join(rel_path, file)
                    if self._is_excluded(file_rel_path):
                        continue

                    if not self.file_types or any(file.endswith(ext) for ext in self.file_types):
                        file_path = os.path.join(root, file)
                        print(f"Processing: {file_rel_path}")
                        out_file.write(f"File: {file_rel_path}\n")
                        out_file.write("-" * 50 + "\n")

                        try:
                            with open(file_path, 'r', encoding='utf-8') as in_file:
                                content = in_file.read()
                                out_file.write(f"Content of {file_rel_path}:\n")
                                out_file.write(content)
                        except Exception as e:
                            print(f"Error reading file {file_rel_path}: {e}. Skipping.")
                            out_file.write(f"Error reading file: {e}. Content skipped.\n")

                        out_file.write("\n\n")


def main() -> None:
    """
    Main function to parse arguments and run the repository scanner.
    """
    parser = argparse.ArgumentParser(
        description='Scan a folder and write the contents of specified file types to an output file.',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('start_path', type=str, help='The path to the folder to scan.')
    parser.add_argument('output_file', type=str, help='The path to the output file.')
    parser.add_argument(
        '-e', '--exclusion-file',
        type=str,
        help='The path to a file containing exclusion patterns (e.g., .gitignore).'
    )
    parser.add_argument(
        '-t', '--file-types',
        type=str,
        nargs='*',
        help='The file extensions to include in the scan.'
    )
    args = parser.parse_args()

    scanner = RepoScanner(
        start_path=args.start_path,
        output_file=args.output_file,
        exclusion_file=args.exclusion_file,
        file_types=args.file_types
    )

    print(f"Starting scan of '{args.start_path}'...")
    scanner.scan_and_dump()
    print(f"Scan complete. Results written to '{args.output_file}'")


if __name__ == "__main__":
    main()

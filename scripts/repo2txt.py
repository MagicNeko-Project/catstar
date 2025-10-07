#!/usr/bin/env python3
# This script dumps the contents of a Git repository into a single file.
# It's designed to make it easier to use repository content in RAG systems
# or as part of prompts for Large Language Models (LLMs).
# Copied from https://github.com/artkulak/repo2file
import os
import sys
import fnmatch
import argparse
from typing import List, Set, Optional, Tuple, IO
from datetime import datetime, timezone

EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".html": "html", ".css": "css", ".md": "markdown", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml", ".sh": "bash", ".cpp": "cpp", ".c": "c",
    ".java": "java", ".jsx": "javascript", ".go": "go", ".rs": "rust",
    ".kt": "kotlin", ".m": "objectivec", ".swift": "swift", ".rb": "ruby",
    ".php": "php", ".ps1": "powershell", ".sql": "sql", ".proto": "protobuf",
    ".toml": "toml", ".ini": "ini", ".xml": "xml", ".svg": "xml", ".tex": "latex",
}

SENSIBLE_DEFAULTS = {
    ".git/", "node_modules/", "dist/", "build/", ".venv/", "__pycache__/",
}


class RepoScanner:
    """
    A class to scan a repository, filter files, and dump the content to a single file
    in an LLM-optimized format.
    """

    def __init__(self, paths: List[str], exclusion_file: Optional[str] = None, file_types: Optional[List[str]] = None, use_sensible_defaults: bool = False):
        self.paths = sorted(list(set(paths)))
        self.root = os.getcwd()
        self.exclusion_file = exclusion_file
        self.file_types = file_types
        self.exclusion_patterns = self._parse_exclusion_file(use_sensible_defaults)

    def _parse_exclusion_file(self, use_sensible_defaults: bool) -> Set[str]:
        """
        Parses an exclusion file and adds sensible defaults if requested.
        """
        patterns = set()
        if use_sensible_defaults:
            patterns.update(SENSIBLE_DEFAULTS)

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
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
                return True
        return False

    def _get_language(self, file_path: str) -> str:
        """
        Infers the programming language from the file extension.
        """
        _, ext = os.path.splitext(file_path)
        return EXT_TO_LANG.get(ext, "text")

    def _read_file_content(self, path: str) -> Tuple[Optional[str], int, bool, int]:
        """
        Reads file content, detects if it's binary, and counts lines.
        Returns (content, line_count, is_binary, byte_len).
        """
        try:
            with open(path, "rb") as fb:
                data = fb.read()
            text = data.decode("utf-8")
            line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            return text, line_count, False, len(data)
        except UnicodeDecodeError:
            return None, 0, True, len(data)

    def _generate_directory_structure(self) -> str:
        """
        Generates a string representation of the directory structure for multiple paths.
        """
        tree = ['/']

        def _generate_tree(dir_path: str, prefix: str = '') -> None:
            entries = sorted(os.listdir(dir_path), key=str.lower)

            for i, entry in enumerate(entries):
                full_path = os.path.join(dir_path, entry)
                rel_path = os.path.relpath(full_path, self.root)
                if self._is_excluded(rel_path):
                    continue

                connector = '└── ' if i == len(entries) - 1 else '├── '
                name = f"{entry}/" if os.path.isdir(full_path) else entry
                tree.append(f"{prefix}{connector}{name}")

                if os.path.isdir(full_path):
                    new_prefix = f"{prefix}{'    ' if i == len(entries) - 1 else '│   '}"
                    _generate_tree(full_path, new_prefix)

        for path in self.paths:
            if os.path.isdir(path):
                _generate_tree(path)
            else:
                tree.append(f"└── {os.path.basename(path)}")

        return '\n'.join(tree)

    def scan_and_dump(self, out_stream: IO[str]) -> None:
        """
        Scans the repository and writes the directory structure and file contents to the output stream.
        """
        out_stream.write("# Repository Overview\n")
        out_stream.write(f"Root: {self.root}\n")
        out_stream.write(f"Included Paths: {', '.join(self.paths)}\n")
        out_stream.write("Generated by repo2txt.py\n")
        out_stream.write(f"Date: {datetime.now(timezone.utc).isoformat()}\n\n")
        out_stream.write("## Directory Tree\n")
        out_stream.write(self._generate_directory_structure())
        out_stream.write("\n\n---\n\n")

        processed_files = set()

        for path in self.paths:
            if os.path.isfile(path):
                self._process_file(path, out_stream, processed_files)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path, topdown=True):
                    dirs.sort(key=str.lower)
                    rel_path = os.path.relpath(root, self.root)
                    if self._is_excluded(rel_path):
                        dirs[:] = []
                        files[:] = []
                        continue

                    for file in sorted(files, key=str.lower):
                        self._process_file(os.path.join(root, file), out_stream, processed_files)

    def _process_file(self, file_path: str, out_stream: IO[str], processed_files: Set[str]) -> None:
        """
        Processes a single file and writes its content to the output stream.
        """
        abs_path = os.path.abspath(file_path)
        if abs_path in processed_files:
            return

        file_rel_path = os.path.relpath(file_path, self.root).replace(os.sep, "/")
        if self._is_excluded(file_rel_path):
            return

        if not self.file_types or any(file_rel_path.endswith(ext) for ext in self.file_types):
            content, line_count, is_binary, byte_len = self._read_file_content(file_path)

            out_stream.write(f"# FILE: {file_rel_path}\n")
            if is_binary:
                out_stream.write(f"LANG: binary\nSIZE: {byte_len} bytes\n\n")
                out_stream.write("# BINARY FILE (skipped)\n")
            else:
                lang = self._get_language(file_path)
                out_stream.write(f"LANG: {lang}\nSIZE: {line_count} lines\n\n")
                fence = "````" if "```" in content else "```"
                out_stream.write(f"{fence}{lang}\n{content}\n{fence}\n")

            out_stream.write("\n# END FILE\n\n---\n\n")
            processed_files.add(abs_path)


def main() -> None:
    """
    Main function to parse arguments and run the repository scanner.
    """
    parser = argparse.ArgumentParser(
        description='Scan files and directories and write the contents to an LLM-optimized output.',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('paths', nargs='+', help='One or more file or directory paths to include.')
    parser.add_argument('-o', '--output', type=str, help='Optional output file (defaults to stdout).')
    parser.add_argument('-e', '--exclusion-file', type=str, help='Path to a .gitignore-style exclusion file.')
    parser.add_argument('-t', '--file-types', type=str, nargs='*', help='File extensions to include.')
    parser.add_argument('--sensible-defaults', action='store_true', help='Exclude common noise like .git, node_modules.')
    args = parser.parse_args()

    scanner = RepoScanner(
        paths=args.paths,
        exclusion_file=args.exclusion_file,
        file_types=args.file_types,
        use_sensible_defaults=args.sensible_defaults
    )

    out_stream = open(args.output, 'w', encoding='utf-8') if args.output else sys.stdout
    with out_stream:
        scanner.scan_and_dump(out_stream)


if __name__ == "__main__":
    main()

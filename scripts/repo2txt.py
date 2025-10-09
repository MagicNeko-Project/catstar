#!/usr/bin/env python3
# This script dumps the contents of a Git repository into a single file.
# It's designed to make it easier to use repository content in RAG systems
# or as part of prompts for Large Language Models (LLMs).
# Copied from https://github.com/artkulak/repo2file
import os
import sys
import fnmatch
import argparse
from typing import List, Set, Optional, Tuple, IO, Dict
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

    def _insert_path(self, tree: dict, rel_path: str, is_file: bool) -> None:
        parts = [p for p in rel_path.split("/") if p and p != "."]
        node = tree
        for i, part in enumerate(parts):
            last = (i == len(parts) - 1)
            if last and is_file:
                node.setdefault("__files__", set()).add(part)
            else:
                node = node.setdefault(part, {})

    def _render_tree(self, tree: dict, lines: list, prefix: str = "") -> None:
        dirs = sorted([k for k in tree.keys() if k not in ("__files__")], key=str.lower)
        files = sorted(list(tree.get("__files__", [])), key=str.lower)

        entries = [(d, True) for d in dirs] + [(f, False) for f in files]
        for idx, (name, is_dir) in enumerate(entries):
            is_last = (idx == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            if is_dir:
                lines.append(f"{prefix}{connector}{name}/")
                self._render_tree(tree[name], lines, prefix + ("    " if is_last else "│   "))
            else:
                lines.append(f"{prefix}{connector}{name}")

    def _collect_entries(self) -> Tuple[Dict[str, Dict], List[str]]:
        """
        Walks all paths, applies exclusions, and returns a tuple of (tree_dict, file_list).
        """
        tree_root: Dict[str, Dict] = {}
        file_list = []

        for path in self.paths:
            if not os.path.exists(path):
                continue
            abs_path = os.path.abspath(path)
            if os.path.isdir(abs_path):
                for root, dirs, files in os.walk(abs_path, topdown=True):
                    dirs.sort(key=str.lower)
                    rel_root = os.path.relpath(root, self.root).replace(os.sep, "/")
                    if self._is_excluded(rel_root):
                        dirs[:] = []
                        files[:] = []
                        continue
                    if rel_root != "." and not self._is_excluded(rel_root):
                        self._insert_path(tree_root, rel_root, is_file=False)
                    for f in sorted(files, key=str.lower):
                        rel_file = (f if rel_root == "." else f"{rel_root}/{f}")
                        if self._is_excluded(rel_file):
                            continue
                        if self.file_types and not any(rel_file.endswith(ext) for ext in self.file_types):
                            continue
                        self._insert_path(tree_root, rel_file, is_file=True)
                        file_list.append(os.path.join(root, f))
            else:
                rel_file = os.path.relpath(abs_path, self.root).replace(os.sep, "/")
                if not self._is_excluded(rel_file):
                    if not self.file_types or any(rel_file.endswith(ext) for ext in self.file_types):
                        parent = os.path.dirname(rel_file)
                        if parent and parent != ".":
                            self._insert_path(tree_root, parent, is_file=False)
                        self._insert_path(tree_root, rel_file, is_file=True)
                        file_list.append(abs_path)

        return tree_root, sorted(file_list)

    def _generate_directory_structure(self, tree_root: Dict[str, Dict]) -> str:
        lines = ["/"]
        self._render_tree(tree_root, lines)
        return "\n".join(lines)

    def scan_and_dump(self, out_stream: IO[str]) -> None:
        """
        Scans the repository and writes the directory structure and file contents to the output stream.
        """
        tree_root, files = self._collect_entries()

        normalized_paths = ", ".join(sorted(os.path.relpath(p, self.root).replace(os.sep, "/") for p in self.paths))
        out_stream.write("# Repository Overview\n")
        out_stream.write(f"Root: {self.root}\n")
        out_stream.write(f"Included Paths: {normalized_paths}\n")
        out_stream.write("Generated by repo2txt.py\n")
        out_stream.write(f"Date: {datetime.now(timezone.utc).isoformat()}\n\n")
        out_stream.write("## Directory Tree\n")
        out_stream.write(self._generate_directory_structure(tree_root))
        out_stream.write("\n\n---\n\n")

        processed_files = set()
        for file_path in files:
            self._process_file(file_path, out_stream, processed_files)

    def _process_file(self, file_path: str, out_stream: IO[str], processed_files: Set[str]) -> None:
        """
        Processes a single file and writes its content to the output stream.
        """
        abs_path = os.path.abspath(file_path)
        if abs_path in processed_files:
            return

        file_rel_path = os.path.relpath(file_path, self.root).replace(os.sep, "/")

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

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as out_stream:
            scanner.scan_and_dump(out_stream)
    else:
        scanner.scan_and_dump(sys.stdout)


if __name__ == "__main__":
    main()

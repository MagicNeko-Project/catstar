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


Tree = Dict[str, Dict]

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

    def __init__(self, paths: List[str], exclusion_file: Optional[str] = None,
                 file_types: Optional[List[str]] = None,
                 use_sensible_defaults: bool = False,
                 debug_exclude: bool = False):
        self.paths = sorted(list(set(paths)))
        self.root = os.getcwd()
        self.exclusion_file = exclusion_file
        self.file_types = file_types
        self.exclusion_patterns = self._parse_exclusion_file(use_sensible_defaults)
        self.debug_exclude = debug_exclude

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

    def _norm(self, p: str) -> str:
        # POSIX-style, no leading './', collapse backslashes
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        return p.strip("/")

    def _is_excluded(self, path: str) -> bool:
        path = self._norm(path)
        if not path:
            return False

        for raw in self.exclusion_patterns:
            pat = raw.strip()
            if not pat or pat.startswith("#"):
                continue

            negated = pat.startswith("!")
            if negated:
                pat = pat[1:].strip()
            pat = pat.replace("\\", "/").strip()

            matched = False

            if pat.endswith("/"):
                seg = pat.rstrip("/")
                hay = f"/{path}/"
                matched = (path == seg) or (f"/{seg}/" in hay)

            elif pat.startswith("/"):
                anchor = pat.lstrip("/")
                matched = (path == anchor) or path.startswith(anchor + "/")

            elif "/" in pat:
                matched = fnmatch.fnmatch(path, pat)

            else:
                matched = any(fnmatch.fnmatch(part, pat) for part in path.split("/"))

            if matched:
                if self.debug_exclude:
                    print(f"[exclude] path='{path}' matched by pattern='{raw}'", file=sys.stderr)
                if negated:
                    return False
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

    def _insert_path(self, tree: Tree, rel_path: str, is_file: bool) -> None:
        parts = [p for p in self._norm(rel_path).split("/") if p]
        node = tree
        for i, part in enumerate(parts):
            last = (i == len(parts) - 1)
            if last and is_file:
                node.setdefault("__files__", set()).add(part)
            else:
                node = node.setdefault(part, {})

    def _render_tree(self, tree: Tree, lines: list, prefix: str = "") -> None:
        dirs = sorted([k for k in tree.keys() if k not in ("__files__",)], key=str.lower)
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

    def _include_file(self, abs_path: str, rel_path: str, tree_root: Tree, included_files: List[str]) -> None:
        """
        Includes a file in the directory tree and adds it to the collected file list.
        Handles exclusion and file-type filtering automatically.
        """
        if not self._is_excluded(rel_path):
            if not self.file_types or any(rel_path.endswith(ext) for ext in self.file_types):
                parent = os.path.dirname(rel_path)
                if parent and parent != ".":
                    self._insert_path(tree_root, parent, is_file=False)
                self._insert_path(tree_root, rel_path, is_file=True)
                included_files.append(abs_path)

    def _collect_entries(self) -> Tuple[Tree, List[str]]:
        """
        Walks all provided paths (files or directories) exactly once,
        applies exclusion patterns and file-type filters,
        and returns a tuple of:
          - tree_root: nested dictionary representing the directory hierarchy
          - included_files: sorted list of absolute file paths to process

        Duplicate files are automatically deduplicated to handle overlapping inputs.
        """
        tree_root: Tree = {}
        included_files: List[str] = []

        for path in self.paths:
            if not os.path.exists(path):
                continue

            abs_path = os.path.abspath(path)
            rel_path = os.path.relpath(abs_path, self.root).replace(os.sep, "/")

            if os.path.isdir(abs_path):
                for root, dirs, files in os.walk(abs_path, topdown=True):
                    dirs.sort(key=str.lower)
                    files.sort(key=str.lower)
                    rel_root = os.path.relpath(root, self.root).replace(os.sep, "/")

                    if self._is_excluded(rel_root):
                        dirs[:] = []
                        continue

                    if rel_root != ".":
                        self._insert_path(tree_root, rel_root, is_file=False)

                    for f in files:
                        abs_file = os.path.join(root, f)
                        rel_file = f if rel_root == "." else f"{rel_root}/{f}"
                        self._include_file(abs_file, rel_file, tree_root, included_files)
            else:
                self._include_file(abs_path, rel_path, tree_root, included_files)

        return tree_root, sorted(set(included_files))

    def _generate_directory_structure(self, tree_root: Tree) -> str:
        lines = ["/"]
        self._render_tree(tree_root, lines)
        return "\n".join(lines)

    def scan_and_dump(self, out_stream: IO[str]) -> None:
        """
        Scans the repository and writes the directory structure and file contents to the output stream.
        """
        # Phase 1: Collect all files and directory structure
        tree_root, included_files = self._collect_entries()

        # Phase 2: Render output
        normalized_paths = ", ".join(sorted(os.path.relpath(p, self.root).replace(os.sep, "/") for p in self.paths))
        out_stream.write("# Repository Overview\n")
        out_stream.write(f"Root: {self.root}\n")
        out_stream.write(f"Included Paths: {normalized_paths}\n")
        out_stream.write("Generated by repo2txt.py\n")
        out_stream.write(f"Date: {datetime.now(timezone.utc).isoformat()}\n\n")
        out_stream.write("## Directory Tree\n")
        out_stream.write(self._generate_directory_structure(tree_root))
        out_stream.write("\n\n---\n\n")

        # Phase 3: Dump file contents
        processed_files = set()
        for file_path in included_files:
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
    parser.add_argument('--debug-exclude', action='store_true', help='Print debug information for excluded files.')
    args = parser.parse_args()

    scanner = RepoScanner(
        paths=args.paths,
        exclusion_file=args.exclusion_file,
        file_types=args.file_types,
        use_sensible_defaults=args.sensible_defaults,
        debug_exclude=args.debug_exclude
    )

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as out_stream:
            scanner.scan_and_dump(out_stream)
    else:
        scanner.scan_and_dump(sys.stdout)


if __name__ == "__main__":
    main()

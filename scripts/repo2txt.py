#!/usr/bin/env python3
# This script dumps the contents of a Git repository into a single file.
# It's designed to make it easier to use repository content in RAG systems
# or as part of prompts for Large Language Models (LLMs).
# Copied from https://github.com/artkulak/repo2file
import os
import sys
import argparse
import re
from dataclasses import dataclass
from typing import List, Set, Optional, Tuple, IO, Dict, Pattern
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

SENSIBLE_DEFAULTS = [
    # Version control
    ".git/", ".svn/", ".hg/", ".CVS/",

    # Dependencies and build artifacts
    "node_modules/", "bower_components/", "vendor/",
    "dist/", "build/", "target/", "out/", "bin/",
    "__pycache__/", "*.pyc", "*.pyo", "*.pyd",
    "*.egg-info/", ".eggs/",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock",

    # IDE/Editor specific
    ".vscode/", ".idea/", ".project", ".classpath", ".settings/",
    "*.swp", "*.swo", "*~",

    # OS specific
    ".DS_Store", "Thumbs.db",

    # Logs and temporary files
    "*.log", "*.tmp", "*.temp",
    ".venv/", "venv/", "env/",
]


@dataclass(frozen=True)
class Rule:
    raw: str
    negated: bool
    anchored: bool
    dir_only: bool
    pattern: str
    regex: Pattern[str]


class GitignoreMatcher:
    def __init__(self, patterns: List[str], debug: bool = False):
        self.rules = [self._compile_rule(p) for p in patterns]
        self.debug = debug

    @staticmethod
    def _norm_posix(p: str) -> str:
        """
        Normalizes paths to use forward slashes and removes leading/trailing slashes.
        This ensures consistency across OS platforms and simplifies matching.
        """
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        while "//" in p:
            p = p.replace("//", "/")
        return p.strip("/")

    @staticmethod
    def _parse_line(line: str) -> Optional[str]:
        """
        Parses a single line from a .gitignore file.
        Handles comments (#), whitespace stripping, and escapes.
        """
        line = line.rstrip("\n\r")
        # Strip trailing unescaped spaces
        i = len(line) - 1
        while i >= 0 and line[i] == " ":
            if i > 0 and line[i-1] == "\\":
                line = line[:i-1] + line[i:]
                i -= 2
                break
            i -= 1
        else:
            line = line[:i+1]

        if not line:
            return None

        # Handle escaped # (literal pound) vs comment #
        if line.startswith(r"\#"):
            line = line[1:]
        elif line.lstrip().startswith("#"):
            return None

        # Handle escaped ! (literal exclamation) vs negation marker
        if line.startswith(r"\!"):
            return "\x00" + line[2:] # Use null byte as a marker for literal '!' for later processing

        return GitignoreMatcher._norm_posix(line) if line else None

    def _compile_rule(self, raw: str) -> Rule:
        """
        Translates a .gitignore glob pattern into a compiled regex object.
        This is the core engine for matching paths.
        """
        # 1. Detect negation and extract pure pattern
        if raw.startswith("\x00"):
            neg = False
            pat = "!" + raw[1:]
        else:
            neg = raw.startswith("!")
            pat = raw[1:] if neg else raw

        # 2. Detect anchoring (starts with / means it matches from the root)
        anchored = pat.startswith("/")
        if anchored:
            pat = pat.lstrip("/")

        # 3. Detect directory-only constraints (ends with /)
        dir_only = pat.endswith("/")
        if dir_only:
            pat = pat.rstrip("/")

        # 4. Convert glob symbols to regex syntax
        special = r".^$+{}()|"
        esc = []
        i = 0
        while i < len(pat):
            c = pat[i]
            if c == "*":
                if i + 1 < len(pat) and pat[i+1] == "*":
                    # Double asterisk '**' matches any sequence of characters across directories
                    esc.append(".*")
                    i += 2
                    continue
                else:
                    # Single asterisk '*' matches anything except directory separator '/'
                    esc.append("[^/]*")
            elif c == "?":
                # Question mark '?' matches a single character except directory separator '/'
                esc.append("[^/]")
            elif c in special:
                # Escape standard regex meta-characters
                esc.append("\\" + c)
            else:
                esc.append(c)
            i += 1
        core = "".join(esc)

        # 5. Handle directory traversal (match anything underneath if it's a dir rule)
        if dir_only:
            tail = r"(?:/.*)?"
        else:
            tail = r"(?:/.*)?"

        # 6. Final regex assembly based on anchoring
        if anchored:
            # Anchored to root: matches 'core' at start of path
            regex = rf"^(?:{core}){tail}$"
        else:
            # Unanchored: can match anywhere in the path (e.g. 'foo/bar' matches 'src/foo/bar')
            regex = rf"^(?:.*?/)*(?:{core}){tail}$"

        return Rule(raw=raw, negated=neg, anchored=anchored, dir_only=dir_only, pattern=pat, regex=re.compile(regex))

    def is_excluded(self, rel_path: str) -> bool:
        """
        Checks if a path is excluded by any of the rules.
        Standard gitignore precedence: the LAST matching rule wins.
        """
        path = self._norm_posix(rel_path)
        if not path:
            return False

        decision: Optional[bool] = None
        for rule in self.rules:
            if rule.regex.match(path):
                decision = not rule.negated
                if self.debug:
                    state = "EXCLUDE" if decision else "INCLUDE"
                    print(f"[exclude] {state}: path='{path}' matched rule='{rule.raw}'", file=sys.stderr)
        return bool(decision)


class RepoScanner:
    """
    A class to scan a repository, filter files, and dump the content to a single file
    in an LLM-optimized format.
    """

    def __init__(self, paths: List[str], exclusion_file: Optional[str] = None,
                 exclusion_patterns: Optional[List[str]] = None,
                 content_exclusion_file: Optional[str] = None,
                 content_exclusion_patterns: Optional[List[str]] = None,
                 file_types: Optional[List[str]] = None,
                 use_sensible_defaults: bool = False,
                 debug_exclude: bool = False):
        self.paths = sorted(list(set(paths)))
        self.root = os.getcwd()
        self.file_types = file_types
        self.matcher = self._create_matcher(exclusion_file, exclusion_patterns, use_sensible_defaults, debug_exclude)
        self.content_matcher = self._create_matcher(content_exclusion_file, content_exclusion_patterns, False, debug_exclude)

    def _create_matcher(self, exclusion_file: Optional[str], extra_patterns: Optional[List[str]], use_sensible_defaults: bool, debug: bool) -> GitignoreMatcher:
        patterns: List[str] = []
        if use_sensible_defaults:
            patterns.extend(SENSIBLE_DEFAULTS)

        if exclusion_file and os.path.exists(exclusion_file):
            with open(exclusion_file, "r", encoding="utf-8") as f:
                for raw in f:
                    parsed = GitignoreMatcher._parse_line(raw)
                    if parsed is not None:
                        patterns.append(parsed)

        if extra_patterns:
            for pat in extra_patterns:
                parsed = GitignoreMatcher._parse_line(pat)
                if parsed is not None:
                    patterns.append(parsed)

        return GitignoreMatcher(patterns, debug)

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
        """
        Builds a nested dictionary (trie structure) representing the filesystem.
        Leaves are stored in a special '__files__' set key at each node level.
        """
        parts = [p for p in self.matcher._norm_posix(rel_path).split("/") if p]
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
        if not self.matcher.is_excluded(rel_path):
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
          - tree_root: nested dictionary representing the directory hierarchy (for tree drawing)
          - included_files: deduplicated list of absolute file paths to dump (for content dumping)

        This separates discovery (finding files) from rendering (printing them) to ensure
        correctness and avoid processing overlapping directories twice.
        """
        tree_root: Tree = {}
        included_files: List[str] = []

        for path in self.paths:
            if not os.path.exists(path):
                continue

            abs_path = os.path.abspath(path)
            rel_path = os.path.relpath(abs_path, self.root).replace(os.sep, "/")

            if os.path.isdir(abs_path):
                # Using os.walk to find all children recursively
                for root, dirs, files in os.walk(abs_path, topdown=True):
                    dirs.sort(key=str.lower)
                    files.sort(key=str.lower)
                    rel_root = os.path.relpath(root, self.root).replace(os.sep, "/")

                    excluded_dir = self.matcher.is_excluded(rel_root)

                    if not excluded_dir and rel_root != ".":
                        self._insert_path(tree_root, rel_root, is_file=False)

                    # Always process files so negations like `!dist/keep.txt` can re-include them
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
        else:
            lang = self._get_language(file_path)
            out_stream.write(f"LANG: {lang}\nSIZE: {line_count} lines\n\n")

        if self.content_matcher.is_excluded(file_rel_path):
            out_stream.write("# CONTENT EXCLUDED\n")
        elif is_binary:
            out_stream.write("# BINARY FILE (skipped)\n")
        else:
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
    parser.add_argument('--exclude', type=str, nargs='*', help='One or more .gitignore-style exclusion patterns.')
    parser.add_argument('--content-exclusion-file', type=str, help='Path to a .gitignore-style exclusion file for content only.')
    parser.add_argument('--exclude-content', type=str, nargs='*', help='One or more .gitignore-style exclusion patterns for content only.')
    parser.add_argument('-t', '--file-types', type=str, nargs='*', help='File extensions to include.')
    parser.add_argument('--sensible-defaults', action='store_true', help='Exclude common noise like .git, node_modules.')
    parser.add_argument('--debug-exclude', action='store_true', help='Print debug information for excluded files.')
    args = parser.parse_args()

    scanner = RepoScanner(
        paths=args.paths,
        exclusion_file=args.exclusion_file,
        exclusion_patterns=args.exclude,
        content_exclusion_file=args.content_exclusion_file,
        content_exclusion_patterns=args.exclude_content,
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

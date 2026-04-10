#!/usr/bin/env python3
"""
This script dumps the contents of a Git repository into a single file.
It's designed to make it easier to use repository content in RAG systems
or as part of prompts for Large Language Models (LLMs).
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """Represents a compiled .gitignore-style rule."""
    raw: str
    negated: bool
    anchored: bool
    dir_only: bool
    pattern: str
    regex: re.Pattern[str]


@dataclass
class DirectoryNode:
    """Explicit tree structure for rendering the directory hierarchy."""
    name: str
    directories: dict[str, "DirectoryNode"] = field(default_factory=dict)
    files: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Core Logic: The Matcher
# ---------------------------------------------------------------------------

class GitignoreMatcher:
    """Handles parsing and matching paths against .gitignore-style rules."""

    def __init__(self, patterns: list[str], debug: bool = False):
        self.rules = [self._compile_rule(p) for p in patterns]
        self.debug = debug

    @classmethod
    def from_config(
        cls,
        exclusion_file: str | None,
        extra_patterns: list[str] | None,
        use_sensible_defaults: bool,
        debug: bool
    ) -> "GitignoreMatcher":
        """Factory method to assemble a matcher from various configuration sources."""
        patterns: list[str] = []
        if use_sensible_defaults:
            patterns.extend(SENSIBLE_DEFAULTS)

        if exclusion_file:
            path = Path(exclusion_file)
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        for raw in f:
                            parsed = cls._parse_line(raw)
                            if parsed is not None:
                                patterns.append(parsed)
                except PermissionError:
                    print(f"[warning] Permission denied reading exclusion file: {path}", file=sys.stderr)

        if extra_patterns:
            for pat in extra_patterns:
                parsed = cls._parse_line(pat)
                if parsed is not None:
                    patterns.append(parsed)

        return cls(patterns, debug)

    @staticmethod
    def _norm_posix(p: str) -> str:
        """Normalizes paths to use forward slashes."""
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        while "//" in p:
            p = p.replace("//", "/")
        return p.strip("/")

    @staticmethod
    def _parse_line(line: str) -> str | None:
        """Parses a single line from a .gitignore file, handling escapes/comments."""
        line = line.rstrip("\n\r")
        
        i = len(line) - 1
        while i >= 0 and line[i] == " ":
            if i > 0 and line[i - 1] == "\\":
                line = line[:i - 1] + line[i:]
                i -= 2
                break
            i -= 1
        else:
            line = line[:i + 1]

        if not line:
            return None

        if line.startswith(r"\#"):
            line = line[1:]
        elif line.lstrip().startswith("#"):
            return None

        if line.startswith(r"\!"):
            return "\x00" + line[2:]

        return GitignoreMatcher._norm_posix(line) if line else None

    def _compile_rule(self, raw: str) -> Rule:
        """Translates a glob pattern into a compiled regex object."""
        if raw.startswith("\x00"):
            neg = False
            pat = "!" + raw[1:]
        else:
            neg = raw.startswith("!")
            pat = raw[1:] if neg else raw

        anchored = pat.startswith("/")
        if anchored:
            pat = pat.lstrip("/")

        dir_only = pat.endswith("/")
        if dir_only:
            pat = pat.rstrip("/")

        special = r".^$+{}()|"
        esc = []
        i = 0
        while i < len(pat):
            c = pat[i]
            if c == "*":
                if i + 1 < len(pat) and pat[i + 1] == "*":
                    esc.append(".*")
                    i += 2
                    continue
                else:
                    esc.append("[^/]*")
            elif c == "?":
                esc.append("[^/]")
            elif c in special:
                esc.append("\\" + c)
            else:
                esc.append(c)
            i += 1
        core = "".join(esc)

        tail = r"(?:/.*)?"

        if anchored:
            regex = rf"^(?:{core}){tail}$"
        else:
            regex = rf"^(?:.*?/)*(?:{core}){tail}$"

        return Rule(
            raw=raw,
            negated=neg,
            anchored=anchored,
            dir_only=dir_only,
            pattern=pat,
            regex=re.compile(regex)
        )

    def is_excluded(self, rel_path: str) -> bool:
        """Checks if a path is excluded by any of the rules."""
        path = self._norm_posix(rel_path)
        if not path:
            return False

        decision: bool | None = None
        for rule in self.rules:
            if rule.regex.match(path):
                decision = not rule.negated
                if self.debug:
                    state = "EXCLUDE" if decision else "INCLUDE"
                    print(f"[exclude] {state}: path='{path}' matched rule='{rule.raw}'", file=sys.stderr)
        
        return bool(decision)

    def can_skip_dir(self, rel_dir: str) -> bool:
        """Returns True if the directory is safely excluded with no potential negations."""
        path = self._norm_posix(rel_dir)
        if not path:
            return False

        excluded = False
        last_match_idx = -1
        
        for i, rule in enumerate(self.rules):
            if rule.regex.match(path):
                excluded = not rule.negated
                last_match_idx = i
                
        if not excluded:
            return False
            
        for i in range(last_match_idx + 1, len(self.rules)):
            rule = self.rules[i]
            if rule.negated:
                if not rule.anchored or any(c in rule.pattern for c in "*?[]"):
                    return False
                if (rule.pattern.startswith(path + "/") or 
                    path.startswith(rule.pattern + "/") or 
                    rule.pattern == path):
                    return False

        return True


# ---------------------------------------------------------------------------
# Core Logic: The Scanner
# ---------------------------------------------------------------------------

def _safe_relative_posix(target: Path, base: Path) -> str:
    """Safely calculates a relative POSIX path, falling back if outside base."""
    try:
        return target.relative_to(base).as_posix()
    except ValueError:
        # Fallback for paths outside the root structure using legacy os.path
        return Path(os.path.relpath(target, base)).as_posix()


class RepoScanner:
    """Traverses the filesystem, applies rules, and constructs a pure data structure."""

    def __init__(self, root_dir: Path, matcher: GitignoreMatcher, file_types: list[str] | None):
        self.root_dir = root_dir
        self.matcher = matcher
        self.file_types = file_types

    def scan(self, target_paths: list[Path]) -> tuple[DirectoryNode, list[Path]]:
        root_node = DirectoryNode("/")
        included_files: set[Path] = set()

        for target in target_paths:
            if not target.exists():
                continue

            # Process individual file directly
            if target.is_file():
                self._process_file(target, root_node, included_files)
                continue
            
            # Or traverse directory
            if target.is_dir():
                self._traverse_directory(target, root_node, included_files)

        # Return a sorted, deterministic list
        return root_node, sorted(list(included_files))

    def _traverse_directory(self, current_dir: Path, root_node: DirectoryNode, included_files: set[Path]):
        try:
            entries = list(current_dir.iterdir())
        except PermissionError:
            print(f"[warning] Permission denied to read directory: {current_dir}", file=sys.stderr)
            return

        # Segregate for ordered processing
        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]

        # Register the directory itself in the tree if it's not excluded
        rel_current = _safe_relative_posix(current_dir, self.root_dir)
        if rel_current != "." and not self.matcher.is_excluded(rel_current):
            self._insert_into_tree(root_node, rel_current, is_file=False)

        for d in dirs:
            rel_d = _safe_relative_posix(d, self.root_dir)
            if self.matcher.can_skip_dir(rel_d):
                if self.matcher.debug:
                    print(f"[exclude] SKIP DIR : path='{rel_d}'", file=sys.stderr)
                continue
            
            self._traverse_directory(d, root_node, included_files)

        for f in files:
            self._process_file(f, root_node, included_files)

    def _process_file(self, file_path: Path, root_node: DirectoryNode, included_files: set[Path]):
        rel_f = _safe_relative_posix(file_path, self.root_dir)
        
        if not self.matcher.is_excluded(rel_f):
            if not self.file_types or file_path.suffix in self.file_types:
                self._insert_into_tree(root_node, rel_f, is_file=True)
                included_files.add(file_path)

    def _insert_into_tree(self, root: DirectoryNode, rel_path: str, is_file: bool):
        parts = [p for p in rel_path.split("/") if p]
        node = root
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            
            if is_last and is_file:
                node.files.add(part)
            else:
                if part not in node.directories:
                    node.directories[part] = DirectoryNode(part)
                node = node.directories[part]


# ---------------------------------------------------------------------------
# Core Logic: The Renderer
# ---------------------------------------------------------------------------

class RepoRenderer:
    """Takes pure data structures and renders them to formatted outputs (e.g., Markdown)."""

    def __init__(self, root_dir: Path, content_matcher: GitignoreMatcher):
        self.root_dir = root_dir
        self.content_matcher = content_matcher

    def render(self, tree_root: DirectoryNode, files: list[Path], target_paths: list[Path], out_stream: TextIO):
        normalized_paths = ", ".join(
            sorted(_safe_relative_posix(p, self.root_dir) for p in target_paths)
        )
        
        # Phase 1: Header
        out_stream.write("# Repository Overview\n")
        out_stream.write(f"Root: {self.root_dir.resolve()}\n")
        out_stream.write(f"Included Paths: {normalized_paths}\n")
        out_stream.write(f"Date: {datetime.now(timezone.utc).isoformat()}\n\n")
        
        # Phase 2: Tree
        out_stream.write("## Directory Tree\n")
        lines = ["/"]
        self._render_tree_nodes(tree_root, lines)
        out_stream.write("\n".join(lines))
        out_stream.write("\n\n---\n\n")

        # Phase 3: Content
        for file_path in files:
            self._render_file(file_path, out_stream)

    def _render_tree_nodes(self, node: DirectoryNode, lines: list[str], prefix: str = ""):
        dirs = sorted(node.directories.keys(), key=str.lower)
        files = sorted(list(node.files), key=str.lower)

        entries = [(d, True) for d in dirs] + [(f, False) for f in files]
        for idx, (name, is_dir) in enumerate(entries):
            is_last = (idx == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            
            if is_dir:
                lines.append(f"{prefix}{connector}{name}/")
                self._render_tree_nodes(
                    node.directories[name], 
                    lines, 
                    prefix + ("    " if is_last else "│   ")
                )
            else:
                lines.append(f"{prefix}{connector}{name}")

    def _render_file(self, file_path: Path, out_stream: TextIO):
        file_rel_path = _safe_relative_posix(file_path, self.root_dir)
        out_stream.write(f"# FILE: {file_rel_path}\n")

        content, line_count, is_binary, byte_len = self._read_file_content(file_path)

        # Write metadata block
        if is_binary:
            out_stream.write(f"LANG: binary\nSIZE: {byte_len} bytes\n\n")
        else:
            lang = EXT_TO_LANG.get(file_path.suffix, "text")
            out_stream.write(f"LANG: {lang}\nSIZE: {line_count} lines\n\n")

        # Write content block
        if self.content_matcher.is_excluded(file_rel_path):
            out_stream.write("# CONTENT EXCLUDED\n")
        elif is_binary:
            out_stream.write("# BINARY FILE (skipped)\n")
        elif content is None:
            out_stream.write("# ERROR: Skipping file due to PermissionError\n")
        else:
            fence = "````" if content and "```" in content else "```"
            out_stream.write(f"{fence}{lang}\n{content if content else ''}\n{fence}\n")

        out_stream.write("\n# END FILE\n\n---\n\n")

    def _read_file_content(self, path: Path) -> tuple[str | None, int, bool, int]:
        """Reads file content, detecting binary formats and handling permission barriers."""
        try:
            data = path.read_bytes()
            text = data.decode("utf-8")
            line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            return text, line_count, False, len(data)
        except UnicodeDecodeError:
            return None, 0, True, len(data)
        except PermissionError:
            print(f"[warning] Permission denied reading file: {path}", file=sys.stderr)
            return None, 0, False, 0


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan files and directories and write the contents to an LLM-optimized output.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", nargs="+", help="One or more file or directory paths to include.")
    parser.add_argument("-o", "--output", type=str, help="Optional output file (defaults to stdout).")
    parser.add_argument("-e", "--exclusion-file", type=str, help="Path to a .gitignore-style exclusion file.")
    parser.add_argument("--exclude", type=str, nargs="*", help="One or more .gitignore-style exclusion patterns.")
    parser.add_argument("--content-exclusion-file", type=str, help="Path to a .gitignore-style exclusion file for content only.")
    parser.add_argument("--exclude-content", type=str, nargs="*", help="One or more .gitignore-style exclusion patterns for content only.")
    parser.add_argument("-t", "--file-types", type=str, nargs="*", help="File extensions to include.")
    parser.add_argument("--sensible-defaults", action="store_true", help="Exclude common noise like .git, node_modules.")
    parser.add_argument("--debug-exclude", action="store_true", help="Print debug information for excluded files.")
    
    args = parser.parse_args()

    # Base Context
    root_dir = Path.cwd()
    target_paths = [Path(p).resolve() for p in args.paths]

    # Instantiate Matchers
    scanner_matcher = GitignoreMatcher.from_config(
        args.exclusion_file, args.exclude, args.sensible_defaults, args.debug_exclude
    )
    content_matcher = GitignoreMatcher.from_config(
        args.content_exclusion_file, args.exclude_content, False, args.debug_exclude
    )

    # Phase 1: Scan
    scanner = RepoScanner(root_dir, scanner_matcher, args.file_types)
    tree_root, included_files = scanner.scan(target_paths)

    # Phase 2: Render
    renderer = RepoRenderer(root_dir, content_matcher)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as out_stream:
            renderer.render(tree_root, included_files, target_paths, out_stream)
    else:
        renderer.render(tree_root, included_files, target_paths, sys.stdout)


if __name__ == "__main__":
    main()

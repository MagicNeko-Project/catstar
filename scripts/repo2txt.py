#!/usr/bin/env python3
"""
This script dumps the contents of a Git repository into a single file.
It utilizes a 4-Tier Visibility Spectrum to explicitly manage structural context vs.
content size, optimizing the output specifically for Large Language Models (LLMs).
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import TextIO

# ---------------------------------------------------------------------------
# Core Enums & Configurations
# ---------------------------------------------------------------------------

class Visibility(Enum):
    PRUNED = auto()    # Tier 0: Completely ignored. The void.
    GHOSTED = auto()   # Tier 1: Shown in Tree, omitted from content dump.
    REDACTED = auto()  # Tier 2: Shown in Tree & Content block, but text is stripped.
    INCLUDED = auto()  # Tier 3: Full Tree and Full Content.


# Language map for markdown fences
EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".html": "html", ".css": "css", ".md": "markdown", ".json": "json",
    ".yaml": "yaml", ".yml": "yaml", ".sh": "bash", ".cpp": "cpp", ".c": "c",
    ".java": "java", ".jsx": "javascript", ".go": "go", ".rs": "rust",
    ".kt": "kotlin", ".m": "objectivec", ".swift": "swift", ".rb": "ruby",
    ".php": "php", ".ps1": "powershell", ".sql": "sql", ".proto": "protobuf",
    ".toml": "toml", ".ini": "ini", ".xml": "xml", ".svg": "xml", ".tex": "latex",
}

# Opinionated, strict rulesets
PRUNE_VCS = [".git/", ".svn/", ".hg/"]
PRUNE_OS = [".DS_Store", "Thumbs.db"]
GHOST_DEPS = ["node_modules/", "venv/", ".venv/", "env/", "vendor/", ".tox/", "bower_components/"]
GHOST_BUILD = ["dist/", "build/", "target/", "out/", "bin/", "__pycache__/", "*.pyc", "*.egg-info/", ".eggs/"]
REDACT_SECRETS = [".env*", "*.pem", "id_rsa", "id_ed25519", "*.key", "secrets.json", "credentials.xml"]
REDACT_LOCKFILES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock", "poetry.lock", "Cargo.lock"]


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """Represents a compiled matching rule and its resulting visibility tier."""
    raw: str
    pattern: str
    regex: re.Pattern[str]
    visibility: Visibility
    anchored: bool
    dir_only: bool
    reason: str | None = None


@dataclass
class DirectoryNode:
    """Explicit tree structure for rendering the directory hierarchy."""
    name: str
    directories: dict[str, "DirectoryNode"] = field(default_factory=dict)
    files: set[str] = field(default_factory=set)


@dataclass
class Telemetry:
    """Tracks operations for the end-user stderr summary."""
    scanned_paths: int = 0
    included_files: int = 0
    ghosted_paths: int = 0
    redacted_files: int = 0
    pruned_paths: int = 0
    secrets_redacted: int = 0

    def print_summary(self):
        print("\n" + "="*50, file=sys.stderr)
        print(" SCAN TELEMETRY SUMMARY", file=sys.stderr)
        print("="*50, file=sys.stderr)
        print(f" Total Paths Scanned : {self.scanned_paths}", file=sys.stderr)
        print(f" Files Included      : {self.included_files}", file=sys.stderr)
        print(f" Paths Ghosted       : {self.ghosted_paths} (Tree Only)", file=sys.stderr)
        print(f" Files Redacted      : {self.redacted_files} (Metadata Only)", file=sys.stderr)
        print(f" Paths Pruned        : {self.pruned_paths} (Completely Ignored)", file=sys.stderr)
        
        if self.secrets_redacted > 0:
            print("\n [!] SECURITY NOTICE", file=sys.stderr)
            print(f" {self.secrets_redacted} secret/credential files were redacted.", file=sys.stderr)
            print(" Use --allow-secrets to override if absolutely necessary.", file=sys.stderr)
        print("="*50 + "\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Core Logic: The Matcher
# ---------------------------------------------------------------------------

class VisibilityMatcher:
    """Engine that maps paths to their corresponding Visibility Spectrum tier."""

    def __init__(self, rules: list[Rule], debug: bool = False):
        self.rules = rules
        self.debug = debug

    @staticmethod
    def _norm_posix(p: str) -> str:
        """Normalizes paths to use forward slashes."""
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        while "//" in p:
            p = p.replace("//", "/")
        return p.strip("/")

    @classmethod
    def compile_pattern(cls, raw: str, vis: Visibility, reason: str | None = None) -> Rule:
        """Translates a glob pattern into a compiled Rule object."""
        # Detect negation mapping to INCLUDE
        if raw.startswith("\x00"):
            pat = "!" + raw[1:]
        elif raw.startswith("!"):
            pat = raw[1:]
            vis = Visibility.INCLUDED  # Negation overrides to inclusion
            reason = "EXPLICIT INCLUDE"
        else:
            pat = raw

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
            pattern=pat,
            regex=re.compile(regex),
            visibility=vis,
            anchored=anchored,
            dir_only=dir_only,
            reason=reason
        )

    def get_visibility(self, rel_path: str) -> tuple[Visibility, str | None]:
        """Evaluates a path against all rules. Last match wins."""
        path = self._norm_posix(rel_path)
        if not path:
            return Visibility.INCLUDED, None

        current_vis = Visibility.INCLUDED
        current_reason = None

        for rule in self.rules:
            if rule.regex.match(path):
                current_vis = rule.visibility
                current_reason = rule.reason
        
        return current_vis, current_reason

    def can_skip_dir(self, rel_dir: str, current_vis: Visibility) -> bool:
        """Returns True if a PRUNED/GHOSTED directory has no descendant overrides."""
        if current_vis not in (Visibility.PRUNED, Visibility.GHOSTED):
            return False

        path = self._norm_posix(rel_dir)
        last_match_idx = -1
        
        for i, rule in enumerate(self.rules):
            if rule.regex.match(path):
                last_match_idx = i
                
        # Check if any subsequent rule could elevate a child's visibility
        for i in range(last_match_idx + 1, len(self.rules)):
            rule = self.rules[i]
            if rule.visibility in (Visibility.INCLUDED, Visibility.REDACTED):
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
        return Path(os.path.relpath(target, base)).as_posix()


class RepoScanner:
    """Traverses the filesystem, applies visibility rules, and constructs the dataset."""

    def __init__(self, root_dir: Path, matcher: VisibilityMatcher, telemetry: Telemetry):
        self.root_dir = root_dir
        self.matcher = matcher
        self.telemetry = telemetry

    def scan(self, target_paths: list[Path]) -> tuple[DirectoryNode, list[Path], list[tuple[Path, str]]]:
        root_node = DirectoryNode("/")
        included_files: list[Path] = []
        redacted_files: list[tuple[Path, str]] = []

        for target in target_paths:
            if not target.exists():
                continue

            if target.is_file():
                self._process_file(target, root_node, included_files, redacted_files)
                continue
            
            if target.is_dir():
                self._traverse_directory(target, root_node, included_files, redacted_files)

        # Sort for deterministic output
        included_files.sort()
        redacted_files.sort(key=lambda x: x[0])
        
        return root_node, included_files, redacted_files

    def _traverse_directory(
        self, current_dir: Path, root_node: DirectoryNode, 
        included_files: list[Path], redacted_files: list[tuple[Path, str]]
    ):
        try:
            entries = list(current_dir.iterdir())
        except PermissionError:
            print(f"[warning] Permission denied to read directory: {current_dir}", file=sys.stderr)
            return

        rel_current = _safe_relative_posix(current_dir, self.root_dir)
        
        # We don't evaluate the root folder itself against the matcher to prevent pruning the base
        if rel_current != ".":
            vis, _ = self.matcher.get_visibility(rel_current)
            if vis == Visibility.PRUNED:
                self.telemetry.pruned_paths += 1
                return
            if vis == Visibility.GHOSTED:
                self.telemetry.ghosted_paths += 1
                self._insert_into_tree(root_node, rel_current, is_file=False)
                if self.matcher.can_skip_dir(rel_current, vis):
                    return
            else:
                self._insert_into_tree(root_node, rel_current, is_file=False)

        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]

        for d in dirs:
            self._traverse_directory(d, root_node, included_files, redacted_files)

        for f in files:
            self._process_file(f, root_node, included_files, redacted_files)

    def _process_file(
        self, file_path: Path, root_node: DirectoryNode, 
        included_files: list[Path], redacted_files: list[tuple[Path, str]]
    ):
        self.telemetry.scanned_paths += 1
        rel_f = _safe_relative_posix(file_path, self.root_dir)
        vis, reason = self.matcher.get_visibility(rel_f)
        
        if vis == Visibility.PRUNED:
            self.telemetry.pruned_paths += 1
            return
            
        if vis == Visibility.GHOSTED:
            self.telemetry.ghosted_paths += 1
            self._insert_into_tree(root_node, rel_f, is_file=True)
            return
            
        if vis == Visibility.REDACTED:
            self.telemetry.redacted_files += 1
            if reason == "SECURITY RISK":
                self.telemetry.secrets_redacted += 1
            self._insert_into_tree(root_node, rel_f, is_file=True)
            redacted_files.append((file_path, reason or "USER OVERRIDE"))
            return
            
        if vis == Visibility.INCLUDED:
            self.telemetry.included_files += 1
            self._insert_into_tree(root_node, rel_f, is_file=True)
            included_files.append(file_path)

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
    """Takes pure data structures and renders LLM-prompt-engineered formatting."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    def render(
        self, tree_root: DirectoryNode, included: list[Path], 
        redacted: list[tuple[Path, str]], target_paths: list[Path], out_stream: TextIO
    ):
        normalized_paths = ", ".join(
            sorted(_safe_relative_posix(p, self.root_dir) for p in target_paths)
        )
        
        # Phase 1: Header & System Note
        out_stream.write("# Repository Overview\n")
        out_stream.write(f"Root: {self.root_dir.resolve()}\n")
        out_stream.write(f"Included Paths: {normalized_paths}\n")
        out_stream.write(f"Date: {datetime.now(timezone.utc).isoformat()}\n\n")
        
        out_stream.write("> **LLM SYSTEM NOTE:** This is a read-only repository snapshot.\n")
        out_stream.write("> - **GHOSTED** paths appear in the directory tree but their content is completely omitted to save context window space.\n")
        out_stream.write("> - **REDACTED** files have their content stripped for security or size constraints, but metadata is provided.\n")
        out_stream.write("> Do not hallucinate missing content. Rely on the directory tree for macro-architectural context.\n\n")
        
        # Phase 2: Tree
        out_stream.write("## Directory Tree\n")
        lines = ["/"]
        self._render_tree_nodes(tree_root, lines)
        out_stream.write("\n".join(lines))
        out_stream.write("\n\n---\n\n")

        # Phase 3: Content (Redacted first for metadata context, then Included)
        for file_path, reason in redacted:
            self._render_redacted_file(file_path, reason, out_stream)

        for file_path in included:
            self._render_included_file(file_path, out_stream)

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

    def _render_redacted_file(self, file_path: Path, reason: str, out_stream: TextIO):
        file_rel_path = _safe_relative_posix(file_path, self.root_dir)
        out_stream.write(f"# FILE: {file_rel_path}\n")

        try:
            stat = file_path.stat()
            kb = stat.st_size / 1024
        except OSError:
            kb = 0.0

        lang = EXT_TO_LANG.get(file_path.suffix, "text")
        out_stream.write(f"LANG: {lang}\n")
        out_stream.write(f"SIZE: {kb:.1f} KB\n")
        out_stream.write(f"STATUS: [REDACTED: {reason}]\n")
        
        summary = "Content hidden by scanner to preserve context quality."
        if "SECURITY" in reason:
            summary = "This file was hidden by the scanner to prevent credential leakage. Assume standard environment variables, keys, or certs are defined here."
        elif "LOCKFILE" in reason:
            summary = "Dependency lockfile redacted to save context space. Assume packages are locked to exact reproducible versions."
        elif "BINARY" in reason:
            summary = "Binary file omitted as it is not readable by LLMs."
            
        out_stream.write(f"SUMMARY: {summary}\n\n")
        out_stream.write("# END FILE\n\n---\n\n")

    def _render_included_file(self, file_path: Path, out_stream: TextIO):
        file_rel_path = _safe_relative_posix(file_path, self.root_dir)
        
        # Read content and detect binary on the fly
        try:
            data = file_path.read_bytes()
            text = data.decode("utf-8")
            line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            is_binary = False
        except UnicodeDecodeError:
            text = None
            line_count = 0
            is_binary = True
        except PermissionError:
            print(f"[warning] Permission denied reading file: {file_path}", file=sys.stderr)
            return

        # If it's a binary file that bypassed filters, redirect it to the Redacted formatter
        if is_binary:
            self._render_redacted_file(file_path, "BINARY FILE", out_stream)
            return

        out_stream.write(f"# FILE: {file_rel_path}\n")
        lang = EXT_TO_LANG.get(file_path.suffix, "text")
        out_stream.write(f"LANG: {lang}\nSIZE: {line_count} lines\n\n")

        fence = "````" if text and "```" in text else "```"
        out_stream.write(f"{fence}{lang}\n{text if text else ''}\n{fence}\n")
        out_stream.write("\n# END FILE\n\n---\n\n")


# ---------------------------------------------------------------------------
# CLI Assembly
# ---------------------------------------------------------------------------

def build_rules(args) -> list[Rule]:
    """Compiles the prioritized list of visibility rules."""
    rules: list[Rule] = []

    def append_patterns(patterns: list[str], vis: Visibility, reason: str | None = None):
        for p in patterns:
            rules.append(VisibilityMatcher.compile_pattern(p, vis, reason))

    # 1. Base Opinionated Defaults
    append_patterns(PRUNE_VCS, Visibility.PRUNED, "VCS SYSTEM")
    append_patterns(PRUNE_OS, Visibility.PRUNED, "OS SYSTEM")
    
    if not args.include_deps:
        append_patterns(GHOST_DEPS, Visibility.GHOSTED, "DEPENDENCY")
    if not args.include_build:
        append_patterns(GHOST_BUILD, Visibility.GHOSTED, "BUILD ARTIFACT")
    if not args.include_lockfiles:
        append_patterns(REDACT_LOCKFILES, Visibility.REDACTED, "LOCKFILE")
    if not args.allow_secrets:
        append_patterns(REDACT_SECRETS, Visibility.REDACTED, "SECURITY RISK")

    # 2. CLI Overrides
    if args.prune:
        append_patterns(args.prune, Visibility.PRUNED, "CLI MANUAL PRUNE")
    if args.ghost:
        append_patterns(args.ghost, Visibility.GHOSTED, "CLI MANUAL GHOST")
    if args.redact:
        append_patterns(args.redact, Visibility.REDACTED, "CLI MANUAL REDACT")

    # 3. Gitignore Integration (Defaults to GHOSTED, negations to INCLUDED)
    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        try:
            with gitignore_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # The compile_pattern handles mapping `!` to Visibility.INCLUDED
                    # Standard gitignore patterns map to GHOSTED as requested.
                    rules.append(VisibilityMatcher.compile_pattern(line, Visibility.GHOSTED, ".gitignore"))
        except PermissionError:
            print(f"[warning] Permission denied reading .gitignore", file=sys.stderr)

    return rules


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract repository context optimized for LLMs using the Visibility Spectrum.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", nargs="+", help="One or more file or directory paths to include.")
    parser.add_argument("-o", "--output", type=str, help="Optional output file (defaults to stdout).")
    
    # Targeted Overrides
    parser.add_argument("--prune", type=str, nargs="*", help="Patterns to prune completely (Tier 0).")
    parser.add_argument("--ghost", type=str, nargs="*", help="Patterns to ghost in the tree (Tier 1).")
    parser.add_argument("--redact", type=str, nargs="*", help="Patterns to redact content from (Tier 2).")
    
    # Bypass Flags
    parser.add_argument("--include-deps", action="store_true", help="Bypass GHOST_DEPS (include node_modules, venv).")
    parser.add_argument("--include-build", action="store_true", help="Bypass GHOST_BUILD (include dist, build).")
    parser.add_argument("--include-lockfiles", action="store_true", help="Bypass REDACT_LOCKFILES.")
    parser.add_argument("--allow-secrets", action="store_true", help="DANGER: Bypass REDACT_SECRETS. May leak credentials.")
    
    args = parser.parse_args()

    if args.allow_secrets:
        print("\n\033[5;31;40m ⚠️  WARNING: SECRET REDACTION DISABLED. CREDENTIALS MAY BE LEAKED. ⚠️ \033[0m\n", file=sys.stderr)

    root_dir = Path.cwd()
    target_paths = [Path(p).resolve() for p in args.paths]

    telemetry = Telemetry()
    rules = build_rules(args)
    matcher = VisibilityMatcher(rules)
    
    scanner = RepoScanner(root_dir, matcher, telemetry)
    tree_root, included_files, redacted_files = scanner.scan(target_paths)

    renderer = RepoRenderer(root_dir)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as out_stream:
            renderer.render(tree_root, included_files, redacted_files, target_paths, out_stream)
    else:
        renderer.render(tree_root, included_files, redacted_files, target_paths, sys.stdout)

    telemetry.print_summary()


if __name__ == "__main__":
    main()

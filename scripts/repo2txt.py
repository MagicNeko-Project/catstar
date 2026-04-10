#!/usr/bin/env python3
"""
This script dumps the contents of a Git repository into a single file.
It utilizes a 4-Tier Visibility Spectrum to explicitly manage structural context vs.
content size, and formats the output with strict XML tags optimized for frontier LLMs.
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
    REDACTED = auto()  # Tier 2: Shown in Tree & Content block, text is stripped (SECRETS ONLY).
    INCLUDED = auto()  # Tier 3: Full Tree and Full Content.


# Language map for metadata blocks
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
GHOST_LOCKFILES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock", "poetry.lock", "Cargo.lock"]
REDACT_SECRETS = [".env*", "*.pem", "id_rsa", "id_ed25519", "*.key", "secrets.json", "credentials.xml"]


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def parse_size_limit(size_str: str | None) -> int | None:
    """Parses a size string like '2MB' or '500KB' into bytes."""
    if not size_str:
        return None
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMG]?B)$", size_str.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}. Use e.g. '2MB', '500KB', '1.5GB'.")
    
    val = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    return int(val * multipliers[unit])


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
    limit_reached: bool = False
    bytes_written: int = 0

    def print_summary(self):
        print("\n" + "="*50, file=sys.stderr)
        print(" SCAN TELEMETRY SUMMARY", file=sys.stderr)
        print("="*50, file=sys.stderr)
        print(f" Total Paths Scanned : {self.scanned_paths}", file=sys.stderr)
        print(f" Files Included      : {self.included_files}", file=sys.stderr)
        print(f" Paths Ghosted       : {self.ghosted_paths} (Tree Only)", file=sys.stderr)
        print(f" Files Redacted      : {self.redacted_files} (Metadata Only)", file=sys.stderr)
        print(f" Paths Pruned        : {self.pruned_paths} (Completely Ignored)", file=sys.stderr)
        
        output_mb = self.bytes_written / (1024 * 1024)
        print(f" Output Size         : {output_mb:.2f} MB", file=sys.stderr)

        if self.limit_reached:
            print("\n [!] SAFETY VALVE TRIGGERED", file=sys.stderr)
            print(" The user-defined size limit was reached. Output was cleanly truncated.", file=sys.stderr)

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

    def __init__(self, root_dir: Path, matcher: VisibilityMatcher, telemetry: Telemetry, file_types: list[str] | None):
        self.root_dir = root_dir
        self.matcher = matcher
        self.telemetry = telemetry
        # Ensure extensions start with a dot
        self.file_types = [t if t.startswith('.') else f".{t}" for t in file_types] if file_types else None

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
            # Check the sandbox whitelist if defined
            if self.file_types and file_path.suffix not in self.file_types:
                self.telemetry.pruned_paths += 1
                return

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

class SizeLimitReachedError(Exception):
    """Raised to cleanly halt rendering when max bytes limit is breached."""
    pass


class XMLRepoRenderer:
    """Renders the repository structure using strict XML boundaries for LLM contexts."""

    def __init__(self, root_dir: Path, telemetry: Telemetry, max_bytes: int | None):
        self.root_dir = root_dir
        self.telemetry = telemetry
        self.max_bytes = max_bytes
        self.stream: TextIO | None = None

    def _write(self, text: str):
        """Intercepts stream writes to track byte allocation and enforce safety limits."""
        if self.telemetry.limit_reached:
            return

        chunk_bytes = len(text.encode('utf-8'))
        
        if self.max_bytes and self.telemetry.bytes_written + chunk_bytes > self.max_bytes:
            self.telemetry.limit_reached = True
            # Force close the tags cleanly
            warning = "\n<warning>Extraction halted: Reached user-defined size limit. The context below this point is incomplete.</warning>\n</files>\n</repository>\n"
            self.stream.write(warning)
            raise SizeLimitReachedError()
        
        self.stream.write(text)
        self.telemetry.bytes_written += chunk_bytes

    def render(
        self, tree_root: DirectoryNode, included: list[Path], 
        redacted: list[tuple[Path, str]], target_paths: list[Path], out_stream: TextIO
    ):
        self.stream = out_stream
        
        normalized_paths = ", ".join(
            sorted(_safe_relative_posix(p, self.root_dir) for p in target_paths)
        )
        
        try:
            self._write("<repository>\n")
            
            # Phase 1: Header & System Note
            self._write("  <system_note>\n")
            self._write("    This is a read-only repository snapshot. Some files are marked as GHOSTED (shown in tree only to indicate architecture) or REDACTED (content hidden for security). Do not hallucinate missing content.\n")
            self._write("  </system_note>\n\n")
            
            self._write("  <metadata>\n")
            self._write(f"    <root>{self.root_dir.resolve()}</root>\n")
            self._write(f"    <included_paths>{normalized_paths}</included_paths>\n")
            self._write(f"    <date>{datetime.now(timezone.utc).isoformat()}</date>\n")
            self._write("  </metadata>\n\n")
            
            # Phase 2: Tree
            self._write("  <directory_tree>\n")
            lines = ["/"]
            self._render_tree_nodes(tree_root, lines)
            self._write("\n".join("    " + line for line in lines) + "\n")
            self._write("  </directory_tree>\n\n")

            # Phase 3: Files
            self._write("  <files>\n")

            for file_path, reason in redacted:
                self._render_redacted_file(file_path, reason)

            for file_path in included:
                self._render_included_file(file_path)

            self._write("  </files>\n")
            self._write("</repository>\n")

        except SizeLimitReachedError:
            pass # Gracefully halted by the write interceptor

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

    def _render_redacted_file(self, file_path: Path, reason: str):
        file_rel_path = _safe_relative_posix(file_path, self.root_dir)
        
        self._write(f'    <file path="{file_rel_path}">\n')
        self._write("      <metadata>\n")
        self._write(f"        <status>REDACTED: {reason}</status>\n")
        
        summary = "Content hidden by scanner to preserve context quality."
        if "SECURITY" in reason:
            summary = "This file was hidden by the scanner to prevent credential leakage. Assume standard environment variables, keys, or certs are defined here."
        self._write(f"        <summary>{summary}</summary>\n")
        self._write("      </metadata>\n")
        self._write("    </file>\n")

    def _render_included_file(self, file_path: Path):
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

        # Downgrade binaries to GHOSTED at runtime
        if is_binary:
            self.telemetry.ghosted_paths += 1
            self.telemetry.included_files -= 1
            return # Skip rendering entirely (it's already in the tree)

        self._write(f'    <file path="{file_rel_path}">\n')
        self._write("      <metadata>\n")
        lang = EXT_TO_LANG.get(file_path.suffix, "text")
        self._write(f"        <language>{lang}</language>\n")
        self._write(f"        <size_lines>{line_count}</size_lines>\n")
        self._write("      </metadata>\n")
        
        # Strict LLM XML blocks just use a clear content tag wrapper
        self._write("      <content>\n")
        if text:
            self._write(text)
            if not text.endswith("\n"):
                self._write("\n")
        self._write("      </content>\n")
        self._write("    </file>\n")


# ---------------------------------------------------------------------------
# CLI Assembly
# ---------------------------------------------------------------------------

def build_rules(args) -> list[Rule]:
    """Compiles the prioritized list of visibility rules following POLA."""
    rules: list[Rule] = []

    def append_patterns(patterns: list[str], vis: Visibility, reason: str | None = None):
        for p in patterns:
            rules.append(VisibilityMatcher.compile_pattern(p, vis, reason))

    # 1. Base Opinionated Defaults (Lowest Precedence Baseline)
    append_patterns(PRUNE_VCS, Visibility.PRUNED, "VCS SYSTEM")
    append_patterns(PRUNE_OS, Visibility.PRUNED, "OS SYSTEM")
    
    if not args.include_deps:
        append_patterns(GHOST_DEPS, Visibility.GHOSTED, "DEPENDENCY")
    if not args.include_build:
        append_patterns(GHOST_BUILD, Visibility.GHOSTED, "BUILD ARTIFACT")
    if not args.include_lockfiles:
        append_patterns(GHOST_LOCKFILES, Visibility.GHOSTED, "LOCKFILE")
    if not args.allow_secrets:
        append_patterns(REDACT_SECRETS, Visibility.REDACTED, "SECURITY RISK")

    # 2. Gitignore Integration (Overrides Defaults with Project Intent)
    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        try:
            with gitignore_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Standard gitignore patterns map to GHOSTED as requested.
                        rules.append(VisibilityMatcher.compile_pattern(line, Visibility.GHOSTED, ".gitignore"))
        except PermissionError:
            print(f"[warning] Permission denied reading .gitignore", file=sys.stderr)

    # 3. Dedicated LLM Exclusion Files (Overrides .gitignore)
    # The default .llmignore maps directly to PRUNED to eradicate context weight.
    exclusion_files = [Path(".llmignore")]
    if args.exclusion_file:
        exclusion_files.extend(Path(p) for p in args.exclusion_file)

    for ex_file in exclusion_files:
        if ex_file.exists():
            try:
                with ex_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            rules.append(VisibilityMatcher.compile_pattern(line, Visibility.PRUNED, f"Custom Exclusion ({ex_file.name})"))
            except PermissionError:
                print(f"[warning] Permission denied reading {ex_file.name}", file=sys.stderr)

    # 4. CLI Overrides (Highest Precedence - Absolute User Authority)
    if args.prune:
        append_patterns(args.prune, Visibility.PRUNED, "CLI MANUAL PRUNE")
    if args.ghost:
        append_patterns(args.ghost, Visibility.GHOSTED, "CLI MANUAL GHOST")
    if args.redact:
        append_patterns(args.redact, Visibility.REDACTED, "CLI MANUAL REDACT")

    return rules


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract repository context formatted in LLM-optimized XML, leveraging a Visibility Spectrum.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", nargs="+", help="One or more file or directory paths to include.")
    parser.add_argument("-o", "--output", type=str, help="Optional output file (defaults to stdout).")
    
    # Customization & Sandbox
    parser.add_argument("-t", "--file-types", type=str, nargs="*", help="Whitelist of file extensions to include (e.g., .py .md). All others are PRUNED.")
    parser.add_argument("-e", "--exclusion-file", type=str, nargs="*", help="Path(s) to custom .gitignore-style exclusion files (appended to .llmignore).")
    parser.add_argument("--max-size", type=str, help="Safety valve for maximum output size (e.g., '2MB', '500KB').")

    # Targeted Overrides
    parser.add_argument("--prune", type=str, nargs="*", help="Patterns to prune completely (Tier 0).")
    parser.add_argument("--ghost", type=str, nargs="*", help="Patterns to ghost in the tree (Tier 1).")
    parser.add_argument("--redact", type=str, nargs="*", help="Patterns to redact content from (Tier 2).")
    
    # Bypass Flags
    parser.add_argument("--include-deps", action="store_true", help="Bypass GHOST_DEPS (include node_modules, venv).")
    parser.add_argument("--include-build", action="store_true", help="Bypass GHOST_BUILD (include dist, build).")
    parser.add_argument("--include-lockfiles", action="store_true", help="Bypass GHOST_LOCKFILES.")
    parser.add_argument("--allow-secrets", action="store_true", help="DANGER: Bypass REDACT_SECRETS. May leak credentials.")
    
    args = parser.parse_args()

    try:
        max_bytes = parse_size_limit(args.max_size)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.allow_secrets:
        print("\n\033[5;31;40m ⚠️  WARNING: SECRET REDACTION DISABLED. CREDENTIALS MAY BE LEAKED. ⚠️ \033[0m\n", file=sys.stderr)

    root_dir = Path.cwd()
    target_paths = [Path(p).resolve() for p in args.paths]

    telemetry = Telemetry()
    rules = build_rules(args)
    matcher = VisibilityMatcher(rules)
    
    scanner = RepoScanner(root_dir, matcher, telemetry, args.file_types)
    tree_root, included_files, redacted_files = scanner.scan(target_paths)

    renderer = XMLRepoRenderer(root_dir, telemetry, max_bytes)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as out_stream:
            renderer.render(tree_root, included_files, redacted_files, target_paths, out_stream)
    else:
        renderer.render(tree_root, included_files, redacted_files, target_paths, sys.stdout)

    telemetry.print_summary()


if __name__ == "__main__":
    main()

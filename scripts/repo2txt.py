#!/usr/bin/env python3
"""
repo2txt: A pragmatic, LLM-optimized repository extraction tool.

This script utilizes a 4-Tier Visibility Spectrum to bundle a repository into
strict, mathematically bounded XML tags. It features robust safety mechanisms
including symlink loop protection, output file self-exclusion, binary pre-filtering,
and transactional stream truncation.

Author: Gemini CLI
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import TextIO

# ==============================================================================
# 1. CORE ENUMS & CONFIGURATIONS
# ==============================================================================

class Visibility(Enum):
    PRUNED = auto()    # Tier 0: Completely ignored. The void.
    GHOSTED = auto()   # Tier 1: Shown in Tree, omitted from content dump.
    REDACTED = auto()  # Tier 2: Shown in Tree & Content block, text is stripped.
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

# Opinionated Base Defaults
PRUNE_VCS = [".git/", ".svn/", ".hg/"]
PRUNE_OS = [".DS_Store", "Thumbs.db"]
GHOST_DEPS = ["node_modules/", "venv/", ".venv/", "env/", "vendor/", ".tox/", "bower_components/"]
GHOST_BUILD = ["dist/", "build/", "target/", "out/", "bin/", "__pycache__/", "*.pyc", "*.egg-info/", ".eggs/"]
GHOST_LOCKFILES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock", "poetry.lock", "Cargo.lock"]

# Static Binary Filters (Bypasses I/O open() entirely)
GHOST_MEDIA = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.ico", "*.webp", "*.pdf", "*.mp3", "*.mp4", "*.wav", "*.avi", "*.mkv", "*.mov"]
GHOST_COMPILED = ["*.exe", "*.dll", "*.so", "*.dylib", "*.class", "*.jar", "*.bin", "*.o", "*.a", "*.lib", "*.pyc", "*.pyd", "*.whl", "*.egg", "*.zip", "*.tar", "*.gz", "*.7z", "*.rar"]

# Strict Security
REDACT_SECRETS = [".env*", "*.pem", "id_rsa", "id_ed25519", "*.key", "secrets.json", "credentials.xml"]


# ==============================================================================
# 2. DATA STRUCTURES & UTILITIES
# ==============================================================================

def parse_size_to_bytes(size_str: str | None, default_bytes: int) -> int:
    """Parses a size string like '2MB' or '500KB' into integer bytes."""
    if not size_str:
        return default_bytes
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMG]?B)$", size_str.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}. Use e.g. '2MB', '500KB', '1.5GB'.")
    
    val = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    return int(val * multipliers[unit])


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
        print("\n" + "="*55, file=sys.stderr)
        print(" SCAN TELEMETRY SUMMARY", file=sys.stderr)
        print("="*55, file=sys.stderr)
        print(f" Total Paths Scanned : {self.scanned_paths}", file=sys.stderr)
        print(f" Files Included      : {self.included_files}", file=sys.stderr)
        print(f" Paths Ghosted       : {self.ghosted_paths} (Tree Only)", file=sys.stderr)
        print(f" Files Redacted      : {self.redacted_files} (Metadata Only)", file=sys.stderr)
        print(f" Paths Pruned        : {self.pruned_paths} (Completely Ignored)", file=sys.stderr)
        
        output_mb = self.bytes_written / (1024 * 1024)
        print(f" Output Size         : {output_mb:.2f} MB", file=sys.stderr)

        if self.limit_reached:
            print("\n [!] SAFETY VALVE TRIGGERED", file=sys.stderr)
            print(" The user-defined size limit was reached. Output cleanly truncated.", file=sys.stderr)

        if self.secrets_redacted > 0:
            print("\n [!] SECURITY NOTICE", file=sys.stderr)
            print(f" {self.secrets_redacted} secret/credential files were redacted.", file=sys.stderr)
            print(" Use --allow-secrets to override if absolutely necessary.", file=sys.stderr)
        print("="*55 + "\n", file=sys.stderr)


# ==============================================================================
# 3. INTELLIGENCE: MATCHER & FILE READER
# ==============================================================================

class VisibilityMatcher:
    """Engine that maps paths to their corresponding Visibility Spectrum tier."""

    def __init__(self, rules: list[Rule]):
        self.rules = rules

    @staticmethod
    def _norm_posix(p: str) -> str:
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        while "//" in p:
            p = p.replace("//", "/")
        return p.strip("/")

    @classmethod
    def compile_pattern(cls, raw: str, vis: Visibility, reason: str | None = None) -> Rule:
        """Translates a glob pattern into a compiled Rule object."""
        if raw.startswith("\x00"):
            pat = "!" + raw[1:]
        elif raw.startswith("!"):
            pat = raw[1:]
            vis = Visibility.INCLUDED
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

        return Rule(raw=raw, pattern=pat, regex=re.compile(regex), visibility=vis, anchored=anchored, dir_only=dir_only, reason=reason)

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
                
        for i in range(last_match_idx + 1, len(self.rules)):
            rule = self.rules[i]
            if rule.visibility in (Visibility.INCLUDED, Visibility.REDACTED):
                if not rule.anchored or any(c in rule.pattern for c in "*?[]"):
                    return False
                if (rule.pattern.startswith(path + "/") or path.startswith(rule.pattern + "/") or rule.pattern == path):
                    return False

        return True


class FileReader:
    """Resilient file reader handling encodings, null bytes, and permissions."""

    @staticmethod
    def read_text(file_path: Path) -> tuple[str | None, int, bool]:
        """Returns (text, line_count, is_binary)."""
        try:
            data = file_path.read_bytes()
        except PermissionError:
            print(f"[warning] Permission denied: {file_path}", file=sys.stderr)
            return None, 0, False

        # Null-Byte Binary Pre-Detection
        if b'\x00' in data:
            return None, 0, True

        # The Windows Encoding Cascade
        encodings = ['utf-8', 'utf-8-sig', 'latin-1']
        text = None
        for enc in encodings:
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            return None, 0, True # All decodes failed, fallback to binary

        line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        return text, line_count, False


# ==============================================================================
# 4. THE SCANNER
# ==============================================================================

class RepoScanner:
    """Traverses the filesystem, applies visibility rules, and enforces safeguards."""

    def __init__(
        self, root_dir: Path, matcher: VisibilityMatcher, telemetry: Telemetry, 
        file_types: list[str] | None, max_file_bytes: int, output_file: Path | None
    ):
        self.root_dir = root_dir
        self.matcher = matcher
        self.telemetry = telemetry
        self.max_file_bytes = max_file_bytes
        self.output_file = output_file.resolve() if output_file else None
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
            elif target.is_dir():
                self._traverse_directory(target, root_node, included_files, redacted_files)

        included_files.sort()
        redacted_files.sort(key=lambda x: x[0])
        return root_node, included_files, redacted_files

    def _traverse_directory(self, current_dir: Path, root_node: DirectoryNode, included: list[Path], redacted: list[tuple[Path, str]]):
        # Symlink Loop Protection
        if current_dir.is_symlink():
            self.telemetry.pruned_paths += 1
            return

        try:
            entries = list(current_dir.iterdir())
        except PermissionError:
            print(f"[warning] Permission denied: {current_dir}", file=sys.stderr)
            return

        rel_current = current_dir.relative_to(self.root_dir).as_posix() if current_dir != self.root_dir else "."
        
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
            self._traverse_directory(d, root_node, included, redacted)
        for f in files:
            self._process_file(f, root_node, included, redacted)

    def _process_file(self, file_path: Path, root_node: DirectoryNode, included: list[Path], redacted: list[tuple[Path, str]]):
        # "Eating Its Own Tail" Protection
        if self.output_file and file_path.resolve() == self.output_file:
            self.telemetry.pruned_paths += 1
            return

        # Symlink Check
        if file_path.is_symlink():
            self.telemetry.pruned_paths += 1
            return

        self.telemetry.scanned_paths += 1
        
        try:
            rel_f = file_path.relative_to(self.root_dir).as_posix()
        except ValueError:
            rel_f = Path(os.path.relpath(file_path, self.root_dir)).as_posix()

        vis, reason = self.matcher.get_visibility(rel_f)
        is_cli_override = (reason == "CLI MANUAL INCLUDE")
        
        if vis == Visibility.PRUNED:
            self.telemetry.pruned_paths += 1
            return
            
        if vis == Visibility.GHOSTED:
            self.telemetry.ghosted_paths += 1
            self._insert_into_tree(root_node, rel_f, is_file=True)
            return
            
        if vis == Visibility.REDACTED:
            self.telemetry.redacted_files += 1
            if reason and "SECURITY" in reason:
                self.telemetry.secrets_redacted += 1
            self._insert_into_tree(root_node, rel_f, is_file=True)
            redacted.append((file_path, reason or "USER OVERRIDE"))
            return
            
        if vis == Visibility.INCLUDED:
            # Check Sandbox Whitelist (unless explicitly included via -i)
            if self.file_types and file_path.suffix not in self.file_types and not is_cli_override:
                self.telemetry.pruned_paths += 1
                return

            # Per-File Token Shield
            try:
                f_size = file_path.stat().st_size
                if f_size > self.max_file_bytes and not is_cli_override:
                    self.telemetry.redacted_files += 1
                    self._insert_into_tree(root_node, rel_f, is_file=True)
                    mb_size = f_size / (1024 * 1024)
                    redacted.append((file_path, f"FILE TOO LARGE (> {mb_size:.1f} MB)"))
                    return
            except OSError:
                pass # Proceed to read attempt

            self.telemetry.included_files += 1
            self._insert_into_tree(root_node, rel_f, is_file=True)
            included.append(file_path)

    def _insert_into_tree(self, root: DirectoryNode, rel_path: str, is_file: bool):
        parts = [p for p in rel_path.split("/") if p]
        node = root
        for i, part in enumerate(parts):
            if i == len(parts) - 1 and is_file:
                node.files.add(part)
            else:
                if part not in node.directories:
                    node.directories[part] = DirectoryNode(part)
                node = node.directories[part]


# ==============================================================================
# 5. THE RENDERER
# ==============================================================================

class LimitReachedError(Exception): pass

class XMLRepoRenderer:
    """Renders XML output transactionally, ensuring unbreakable LLM tags."""

    def __init__(self, root_dir: Path, telemetry: Telemetry, max_bytes: int | None):
        self.root_dir = root_dir
        self.telemetry = telemetry
        self.max_bytes = max_bytes
        self.stream: TextIO | None = None

    def _transactional_write(self, text: str):
        """Writes text only if it won't exceed the global byte limit."""
        if self.telemetry.limit_reached:
            raise LimitReachedError()

        chunk_size = len(text.encode('utf-8'))
        
        if self.max_bytes and self.telemetry.bytes_written + chunk_size > self.max_bytes:
            self.telemetry.limit_reached = True
            # Cleanly truncate without broken XML states
            warning = "\n  <warning>Extraction halted: Reached user-defined size limit. The context below this point is incomplete.</warning>\n  </files>\n</repository>\n"
            self.stream.write(warning)
            raise LimitReachedError()
        
        self.stream.write(text)
        self.telemetry.bytes_written += chunk_size

    def render(self, tree_root: DirectoryNode, included: list[Path], redacted: list[tuple[Path, str]], target_paths: list[Path], out_stream: TextIO):
        self.stream = out_stream
        norm_paths = ", ".join(sorted(p.relative_to(self.root_dir).as_posix() if self.root_dir in p.parents else p.as_posix() for p in target_paths))
        
        try:
            # Phase 1: Context Setup
            self._transactional_write("<repository>\n")
            self._transactional_write("  <system_note>\n    This is a read-only repository snapshot. Some files are GHOSTED (in tree only) or REDACTED (content hidden). Do not hallucinate missing content.\n  </system_note>\n\n")
            
            self._transactional_write("  <metadata>\n")
            self._transactional_write(f"    <root>{self.root_dir.resolve()}</root>\n")
            self._transactional_write(f"    <included_paths>{norm_paths}</included_paths>\n")
            self._transactional_write(f"    <date>{datetime.now(timezone.utc).isoformat()}</date>\n")
            self._transactional_write("  </metadata>\n\n")
            
            # Phase 2: Directory Tree
            self._transactional_write("  <directory_tree>\n")
            lines = ["/"]
            self._render_tree_nodes(tree_root, lines)
            self._transactional_write("\n".join("    " + line for line in lines) + "\n")
            self._transactional_write("  </directory_tree>\n\n")

            # Phase 3: File Contents
            self._transactional_write("  <files>\n")

            for file_path, reason in redacted:
                self._transactional_write(self._build_redacted_xml(file_path, reason))

            for file_path in included:
                xml_chunk = self._build_included_xml(file_path)
                if xml_chunk:
                    self._transactional_write(xml_chunk)

            self._transactional_write("  </files>\n</repository>\n")

        except LimitReachedError:
            pass # Execution halted safely

    def _render_tree_nodes(self, node: DirectoryNode, lines: list[str], prefix: str = ""):
        dirs = sorted(node.directories.keys(), key=str.lower)
        files = sorted(list(node.files), key=str.lower)
        entries = [(d, True) for d in dirs] + [(f, False) for f in files]
        
        for idx, (name, is_dir) in enumerate(entries):
            is_last = (idx == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            if is_dir:
                lines.append(f"{prefix}{connector}{name}/")
                self._render_tree_nodes(node.directories[name], lines, prefix + ("    " if is_last else "│   "))
            else:
                lines.append(f"{prefix}{connector}{name}")

    def _build_redacted_xml(self, file_path: Path, reason: str) -> str:
        try: rel_path = file_path.relative_to(self.root_dir).as_posix()
        except ValueError: rel_path = file_path.as_posix()

        summary = "Content hidden by scanner."
        if "SECURITY" in reason: summary = "File hidden to prevent credential leakage."
        elif "LARGE" in reason: summary = "File exceeded maximum per-file token shield."

        return (
            f'    <file path="{rel_path}">\n'
            f'      <metadata>\n'
            f'        <status>REDACTED: {reason}</status>\n'
            f'        <summary>{summary}</summary>\n'
            f'      </metadata>\n'
            f'    </file>\n'
        )

    def _build_included_xml(self, file_path: Path) -> str | None:
        try: rel_path = file_path.relative_to(self.root_dir).as_posix()
        except ValueError: rel_path = file_path.as_posix()
        
        text, line_count, is_binary = FileReader.read_text(file_path)

        if is_binary:
            # Dynamic downgrade to GHOSTED (Tree Only)
            self.telemetry.ghosted_paths += 1
            self.telemetry.included_files -= 1
            return None 

        lang = EXT_TO_LANG.get(file_path.suffix, "text")
        
        # Unbreakable XML Boundaries (CDATA Escape)
        content = text or ""
        escaped_cdata = content.replace("]]>", "]]]]><![CDATA[>")

        return (
            f'    <file path="{rel_path}">\n'
            f'      <metadata>\n'
            f'        <language>{lang}</language>\n'
            f'        <size_lines>{line_count}</size_lines>\n'
            f'      </metadata>\n'
            f'      <content><![CDATA[\n{escaped_cdata}\n]]></content>\n'
            f'    </file>\n'
        )


# ==============================================================================
# 6. CLI ASSEMBLY & MAIN
# ==============================================================================

def build_rules(args) -> list[Rule]:
    """Compiles rules adhering to the POLA hierarchy."""
    rules: list[Rule] = []

    def append(patterns: list[str], vis: Visibility, reason: str | None = None):
        for p in patterns: rules.append(VisibilityMatcher.compile_pattern(p, vis, reason))

    # 1. Base Defaults
    append(PRUNE_VCS, Visibility.PRUNED, "VCS")
    append(PRUNE_OS, Visibility.PRUNED, "OS")
    append(GHOST_MEDIA, Visibility.GHOSTED, "MEDIA BINARY")
    append(GHOST_COMPILED, Visibility.GHOSTED, "COMPILED BINARY")
    
    if not args.include_deps: append(GHOST_DEPS, Visibility.GHOSTED, "DEPENDENCY")
    if not args.include_build: append(GHOST_BUILD, Visibility.GHOSTED, "BUILD ARTIFACT")
    if not args.include_lockfiles: append(GHOST_LOCKFILES, Visibility.GHOSTED, "LOCKFILE")
    if not args.allow_secrets: append(REDACT_SECRETS, Visibility.REDACTED, "SECURITY RISK")

    # 2. .gitignore
    p_git = Path(".gitignore")
    if p_git.exists():
        try:
            for line in p_git.read_text("utf-8").splitlines():
                if line.strip() and not line.startswith("#"):
                    rules.append(VisibilityMatcher.compile_pattern(line.strip(), Visibility.GHOSTED, ".gitignore"))
        except Exception: pass

    # 3. .llmignore / Exclude Files
    ex_files = [Path(".llmignore")]
    if args.exclusion_file: ex_files.extend(Path(p) for p in args.exclusion_file)
    for p_ex in ex_files:
        if p_ex.exists():
            try:
                for line in p_ex.read_text("utf-8").splitlines():
                    if line.strip() and not line.startswith("#"):
                        rules.append(VisibilityMatcher.compile_pattern(line.strip(), Visibility.PRUNED, p_ex.name))
            except Exception: pass

    # 4. CLI Overrides
    if args.prune: append(args.prune, Visibility.PRUNED, "CLI PRUNE")
    if args.ghost: append(args.ghost, Visibility.GHOSTED, "CLI GHOST")
    if args.redact: append(args.redact, Visibility.REDACTED, "CLI REDACT")
    
    # 5. The Ultimate Override
    if args.include: append(args.include, Visibility.INCLUDED, "CLI MANUAL INCLUDE")

    return rules


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a repository into LLM-optimized XML.")
    parser.add_argument("paths", nargs="+", help="Paths to include.")
    parser.add_argument("-o", "--output", type=str, help="Output file (defaults to stdout).")
    
    # Ergonomics & UX
    parser.add_argument("--dry-run", action="store_true", help="Calculate metrics without generating output.")
    parser.add_argument("--force", action="store_true", help="Bypass terminal flood prompts.")
    
    # Sandbox Limits
    parser.add_argument("--max-size", type=str, help="Global output limit (e.g., '2MB', '500KB').")
    parser.add_argument("--max-file-size", type=str, default="2MB", help="Per-file limit (default: 2MB). Oversized files are REDACTED.")
    parser.add_argument("-t", "--file-types", type=str, nargs="*", help="Whitelist extensions (e.g., .py .md).")
    parser.add_argument("-e", "--exclusion-file", type=str, nargs="*", help="Custom .llmignore files.")

    # Overrides
    parser.add_argument("-i", "--include", type=str, nargs="*", help="Ultimate Override: Force include paths.")
    parser.add_argument("--prune", type=str, nargs="*", help="Force PRUNE paths.")
    parser.add_argument("--ghost", type=str, nargs="*", help="Force GHOST paths.")
    parser.add_argument("--redact", type=str, nargs="*", help="Force REDACT paths.")
    parser.add_argument("--include-deps", action="store_true")
    parser.add_argument("--include-build", action="store_true")
    parser.add_argument("--include-lockfiles", action="store_true")
    parser.add_argument("--allow-secrets", action="store_true")
    
    args = parser.parse_args()

    # Terminal Flood Protection
    if not args.output and sys.stdout.isatty() and not args.force and not args.dry_run:
        print("\n[!] WARNING: No output file specified (-o).", file=sys.stderr)
        print("    You are about to dump the entire repository context directly to your terminal screen.", file=sys.stderr)
        resp = input("    Are you sure you want to proceed? [y/N]: ")
        if resp.strip().lower() != 'y':
            print("Aborted.", file=sys.stderr)
            sys.exit(0)

    try:
        max_bytes = parse_size_to_bytes(args.max_size, 0) if args.max_size else None
        max_file_bytes = parse_size_to_bytes(args.max_file_size, 2 * 1024 * 1024)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    root_dir = Path.cwd()
    target_paths = [Path(p).resolve() for p in args.paths]
    output_path = Path(args.output).resolve() if args.output else None

    telemetry = Telemetry()
    rules = build_rules(args)
    matcher = VisibilityMatcher(rules)
    
    scanner = RepoScanner(root_dir, matcher, telemetry, args.file_types, max_file_bytes, output_path)
    tree_root, included_files, redacted_files = scanner.scan(target_paths)

    if not args.dry_run:
        renderer = XMLRepoRenderer(root_dir, telemetry, max_bytes)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as out_stream:
                renderer.render(tree_root, included_files, redacted_files, target_paths, out_stream)
        else:
            renderer.render(tree_root, included_files, redacted_files, target_paths, sys.stdout)

    telemetry.print_summary()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Git repository archival utility.

Backs up complete Git repositories into verified standalone bundle files
organized by repository path and month with restic-style retention management.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlparse

TIMESTAMP_FILENAME_PATTERN = re.compile(r"^(\d{8})_(\d{6})(?:_(\d+))?\.bundle$")
MONTH_DIRECTORY_PATTERN = re.compile(r"^\d{6}$")
INLINE_COMMENT_PATTERN = re.compile(r"\s+#.*$")
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
MONTH_FORMAT = "%Y%m"

PeriodKey = TypeVar("PeriodKey")


@dataclass(frozen=True)
class ArchiveBundle:
    """Represents a point-in-time Git bundle archive."""

    file_path: Path
    timestamp: datetime
    size_in_bytes: int


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention rule configuration modeled after restic forget."""

    keep_last: int | None = None
    keep_daily: int | None = None
    keep_weekly: int | None = None
    keep_monthly: int | None = None
    keep_yearly: int | None = None

    @property
    def is_active(self) -> bool:
        """Determines whether any retention limits are active."""
        return any(
            c is not None
            for c in (
                self.keep_last,
                self.keep_daily,
                self.keep_weekly,
                self.keep_monthly,
                self.keep_yearly,
            )
        )


@dataclass(frozen=True)
class RepositoryExecutionSummary:
    """Execution status and statistics for an archived repository."""

    repository_identifier: str
    target_relative_path: Path
    bundle_created: bool
    skipped_unchanged: bool
    bundles_pruned_count: int
    error_message: str | None = None


def format_file_size(size_in_bytes: int) -> str:
    """Formats raw byte count into a human-readable string with units."""
    scaled = float(size_in_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if scaled < 1024.0 or unit == "TB":
            return f"{int(scaled)} B" if unit == "B" else f"{scaled:.1f} {unit}"
        scaled /= 1024.0
    return f"{scaled:.1f} TB"


def run_git_command(
    arguments: list[str],
    working_directory: Path | None = None,
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Executes a git command with standard options and error reporting."""
    cmd = ["git"]
    if working_directory is not None:
        cmd.extend(["-C", str(working_directory)])
    cmd.extend(arguments)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        cmd, capture_output=capture_output, text=True, check=check, env=env
    )


def is_remote_repository_url(source_address: str) -> bool:
    """Determines whether the source string is a remote Git URL."""
    remote_schemes = ("http://", "https://", "git://", "ssh://", "file://")
    if any(source_address.startswith(s) for s in remote_schemes):
        return True
    if re.match(r"^[a-zA-Z]:[\\/]", source_address) or source_address.startswith(
        ("\\\\", "//")
    ):
        return False
    if Path(source_address).exists():
        return False
    if ":" in source_address and not source_address.startswith(("/", ".")):
        host, path = source_address.split(":", 1)
        if len(host) > 1 and "/" not in host and "\\" not in host and path.strip():
            return True
    return False


def parse_remote_repository_relative_path(remote_url: str) -> Path:
    """Extracts the org/repo relative filesystem path from a remote URL."""
    cleaned = remote_url.strip().removesuffix(".git").rstrip("/")
    if ":" in cleaned and not any(
        cleaned.startswith(s) for s in ("http://", "https://", "git://", "ssh://")
    ):
        _, path_part = cleaned.split(":", 1)
        segs = [s for s in path_part.strip("/").split("/") if s]
        if segs:
            return Path(*segs)

    parsed = urlparse(cleaned)
    segs = [s for s in parsed.path.strip("/").split("/") if s]
    if not segs:
        raise ValueError(f"Unable to extract repository path from URL: {remote_url}")
    return Path(*segs)


def resolve_local_repository_relative_path(repository_path: Path) -> Path:
    """Resolves relative path for a local repo, preferring org/repo from origin URL."""
    try:
        out = run_git_command(
            ["remote", "get-url", "origin"], working_directory=repository_path
        )
        if url := out.stdout.strip():
            return parse_remote_repository_relative_path(url)
    except (subprocess.CalledProcessError, ValueError):
        pass

    try:
        remotes_out = run_git_command(["remote"], working_directory=repository_path)
        for r in (m.strip() for m in remotes_out.stdout.splitlines() if m.strip()):
            try:
                out = run_git_command(
                    ["remote", "get-url", r], working_directory=repository_path
                )
                if url := out.stdout.strip():
                    return parse_remote_repository_relative_path(url)
            except (subprocess.CalledProcessError, ValueError):
                continue
    except subprocess.CalledProcessError:
        pass

    return Path(repository_path.name)


def resolve_repository_destination_path(source_identifier: str) -> Path:
    """Resolves relative destination path (<org>/<repo>) for a repository source."""
    if is_remote_repository_url(source_identifier):
        return parse_remote_repository_relative_path(source_identifier)
    local_path = Path(source_identifier).resolve()
    return (
        resolve_local_repository_relative_path(local_path)
        if local_path.exists()
        else Path(local_path.name)
    )


def deduplicate_repository_sources(sources: Sequence[str]) -> list[str]:
    """Deduplicates repository sources by resolved destination path."""
    deduped: list[str] = []
    seen: set[Path] = set()
    for src in sources:
        try:
            dest = resolve_repository_destination_path(src)
        except (ValueError, OSError, subprocess.CalledProcessError):
            dest = Path(src.strip().rstrip("/"))
        if dest not in seen:
            seen.add(dest)
            deduped.append(src)
    return deduped


def parse_repository_list_file(source: str | Path, is_stdin: bool = False) -> list[str]:
    """Parses repository list file or stdin, stripping comments and whitespace."""
    if is_stdin or str(source) == "-":
        lines = sys.stdin.read().splitlines()
    else:
        file_path = Path(source).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Repository list file not found: {file_path}")
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as err:
            raise OSError(
                f"Failed to read repository list file '{file_path}': {err}"
            ) from err

    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if cleaned := INLINE_COMMENT_PATTERN.sub("", stripped).strip():
            result.append(cleaned)
    return result


def _atomic_write_file(target_path: Path, content: str) -> None:
    """Writes content to target_path atomically using a temporary file."""
    tmp = target_path.parent / f".{target_path.name}.tmp_{os.getpid()}"
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target_path)


def update_or_write_repository_list_file(
    target_path: Path,
    candidate_sources: Sequence[str],
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Writes or updates repository list file with candidate sources."""
    if target_path.exists():
        existing = parse_repository_list_file(target_path)
        existing_dests = {resolve_repository_destination_path(r) for r in existing}
        to_append: list[str] = []
        for candidate in candidate_sources:
            try:
                dest = resolve_repository_destination_path(candidate)
            except (ValueError, OSError, subprocess.CalledProcessError):
                dest = Path(candidate.strip().rstrip("/"))
            if dest not in existing_dests:
                existing_dests.add(dest)
                to_append.append(candidate)

        if not to_append:
            if verbose:
                print(f"Repository list file is already up to date: {target_path}")
            return 0

        if dry_run:
            print(f"Would append {len(to_append)} repositories to {target_path}")
            return len(to_append)

        try:
            curr = target_path.read_text(encoding="utf-8", errors="replace")
            if curr and not curr.endswith("\n"):
                curr += "\n"
            _atomic_write_file(target_path, curr + "\n".join(to_append) + "\n")
        except OSError as err:
            raise OSError(
                f"Failed to update repository list file '{target_path}': {err}"
            ) from err

        if verbose:
            print(f"Appended {len(to_append)} new repositories to {target_path}")
        return len(to_append)

    deduped = deduplicate_repository_sources(candidate_sources)
    if dry_run:
        print(f"Would write {len(deduped)} repositories to {target_path}")
        return len(deduped)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(deduped) + ("\n" if deduped else "")
        _atomic_write_file(target_path, content)
    except OSError as err:
        raise OSError(
            f"Failed to create repository list file '{target_path}': {err}"
        ) from err

    if verbose:
        print(f"Wrote {len(deduped)} repositories to {target_path}")
    return len(deduped)


def inspect_local_repository_cleanliness(repository_path: Path) -> bool:
    """Verifies working tree cleanliness of a local repository."""
    try:
        bare = run_git_command(
            ["rev-parse", "--is-bare-repository"], working_directory=repository_path
        )
        if bare.stdout.strip() == "true":
            return True
    except subprocess.CalledProcessError:
        return True

    try:
        status = run_git_command(
            ["status", "--porcelain"], working_directory=repository_path
        )
        if status.stdout.strip():
            sys.stderr.write(
                f"Warning: Repository '{repository_path}' has uncommitted changes "
                "or untracked files; archiving committed refs and stashes only.\n"
            )
            return False
    except subprocess.CalledProcessError:
        pass
    return True


def fetch_repository_references(repository_path: Path) -> dict[str, str]:
    """Retrieves all references and commit hashes from a Git repository."""
    try:
        out = run_git_command(["show-ref", "--head"], working_directory=repository_path)
    except subprocess.CalledProcessError as err:
        if err.returncode == 1:
            return {}
        raise

    refs: dict[str, str] = {}
    for line in out.stdout.splitlines():
        if len(parts := line.strip().split(maxsplit=1)) == 2:
            refs[parts[1]] = parts[0]

    try:
        wt_out = run_git_command(
            ["rev-parse", "--git-path", "worktrees"], working_directory=repository_path
        )
        wt_dir = Path(wt_out.stdout.strip())
        if not wt_dir.is_absolute():
            wt_dir = repository_path / wt_dir
        if wt_dir.is_dir():
            for entry in wt_dir.iterdir():
                if entry.is_dir() and (entry / "HEAD").is_file():
                    ref_name = f"worktrees/{entry.name}/HEAD"
                    rev_out = run_git_command(
                        ["rev-parse", ref_name], working_directory=repository_path
                    )
                    refs[ref_name] = rev_out.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        pass

    return refs


def fetch_bundle_references(bundle_path: Path) -> dict[str, str]:
    """Extracts reference names and commit hashes directly from a Git bundle."""
    out = run_git_command(["bundle", "list-heads", str(bundle_path)])
    refs: dict[str, str] = {}
    for line in out.stdout.splitlines():
        if len(parts := line.strip().split(maxsplit=1)) == 2:
            refs[parts[1]] = parts[0]
    return refs


def is_repository_unchanged(repository_path: Path, latest_bundle_path: Path) -> bool:
    """Compares current repository references with the latest archived bundle."""
    if not latest_bundle_path.is_file():
        return False
    try:
        bundle_refs = fetch_bundle_references(latest_bundle_path)
        repo_refs = fetch_repository_references(repository_path)
        return bool(repo_refs) and bundle_refs == repo_refs
    except (subprocess.CalledProcessError, OSError):
        return False


def verify_bundle_integrity(
    bundle_path: Path, working_directory: Path | None = None
) -> None:
    """Verifies that a Git bundle is valid and complete."""
    if working_directory is not None:
        run_git_command(
            ["bundle", "verify", str(bundle_path)], working_directory=working_directory
        )
        return

    try:
        run_git_command(["bundle", "verify", str(bundle_path)])
    except subprocess.CalledProcessError as err:
        if "need a repository to verify a bundle" in err.stderr:
            with tempfile.TemporaryDirectory(
                prefix="git_archivist_verify_"
            ) as ephemeral:
                run_git_command(["init", "--bare", ephemeral])
                run_git_command(
                    ["bundle", "verify", str(bundle_path)],
                    working_directory=Path(ephemeral),
                )
        else:
            raise


def update_latest_symlink(
    repository_archive_directory: Path,
    target_bundle_path: Path,
    leaf_name: str,
    dry_run: bool,
) -> None:
    """Atomically creates or updates repo_name.bundle symlink."""
    parent_dir = repository_archive_directory.parent
    symlink_path = parent_dir / f"{leaf_name}.bundle"
    target_rel = (
        Path(repository_archive_directory.name)
        / target_bundle_path.parent.name
        / target_bundle_path.name
    )

    if dry_run:
        print(f"Would update symlink: {symlink_path.name} -> {target_rel}")
        return

    parent_dir.mkdir(parents=True, exist_ok=True)
    tmp_link = parent_dir / f"{leaf_name}.bundle.tmp_{os.getpid()}"
    if tmp_link.is_symlink() or tmp_link.exists():
        tmp_link.unlink()

    tmp_link.symlink_to(target_rel)
    tmp_link.replace(symlink_path)


def collect_repository_bundles(
    repository_archive_directory: Path,
) -> list[ArchiveBundle]:
    """Discovers all archived .bundle files within monthly subdirectories."""
    bundles: list[ArchiveBundle] = []
    if not repository_archive_directory.is_dir():
        return bundles

    for child in repository_archive_directory.iterdir():
        if child.is_dir() and MONTH_DIRECTORY_PATTERN.match(child.name):
            for candidate in child.glob("*.bundle"):
                if candidate.is_symlink():
                    continue
                if match := TIMESTAMP_FILENAME_PATTERN.match(candidate.name):
                    try:
                        ts = datetime.strptime(
                            f"{match.group(1)}_{match.group(2)}", TIMESTAMP_FORMAT
                        ).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    bundles.append(
                        ArchiveBundle(
                            file_path=candidate,
                            timestamp=ts,
                            size_in_bytes=candidate.stat().st_size,
                        )
                    )

    bundles.sort(key=lambda b: (b.timestamp, b.file_path.name), reverse=True)
    return bundles


def collect_newest_bundle_per_period(
    sorted_bundles: list[ArchiveBundle],
    retention_limit: int | None,
    extract_period_key: Callable[[datetime], PeriodKey],
) -> list[ArchiveBundle]:
    """Selects the newest bundle for each unique time period up to retention_limit."""
    if retention_limit is None or retention_limit <= 0:
        return []

    newest: dict[PeriodKey, ArchiveBundle] = {}
    for bundle in sorted_bundles:
        key = extract_period_key(bundle.timestamp)
        if key not in newest:
            newest[key] = bundle

    return list(newest.values())[:retention_limit]


def evaluate_retention_candidates(
    bundles: list[ArchiveBundle],
    policy: RetentionPolicy,
) -> tuple[set[ArchiveBundle], set[ArchiveBundle]]:
    """Evaluates archive bundles against retention policies modeled after restic forget."""
    if not policy.is_active or not bundles:
        return set(bundles), set()

    kept: set[ArchiveBundle] = set()

    if policy.keep_last is not None and policy.keep_last > 0:
        kept.update(bundles[: policy.keep_last])

    kept.update(
        collect_newest_bundle_per_period(
            bundles, policy.keep_daily, lambda ts: ts.date()
        )
    )
    kept.update(
        collect_newest_bundle_per_period(
            bundles,
            policy.keep_weekly,
            lambda ts: (ts.isocalendar().year, ts.isocalendar().week),
        )
    )
    kept.update(
        collect_newest_bundle_per_period(
            bundles, policy.keep_monthly, lambda ts: (ts.year, ts.month)
        )
    )
    kept.update(
        collect_newest_bundle_per_period(
            bundles, policy.keep_yearly, lambda ts: ts.year
        )
    )

    return kept, set(bundles) - kept


def apply_retention_policy(
    repository_archive_directory: Path,
    leaf_name: str,
    policy: RetentionPolicy,
    dry_run: bool,
    verbose: bool,
) -> int:
    """Executes retention evaluation, removing expired archives and cleaning empty dirs."""
    if not policy.is_active:
        return 0

    bundles = collect_repository_bundles(repository_archive_directory)
    if not bundles:
        return 0

    kept, prunes = evaluate_retention_candidates(bundles, policy)
    if not prunes:
        if verbose:
            print(f"Retention policy: all {len(kept)} bundles retained.")
        return 0

    for bundle in sorted(prunes, key=lambda b: b.timestamp):
        rel_path = bundle.file_path.relative_to(repository_archive_directory)
        size_str = format_file_size(bundle.size_in_bytes)
        if dry_run:
            print(
                f"Would prune: {rel_path} ({size_str}, {bundle.timestamp.strftime('%Y-%m-%d %H:%M:%S')})"
            )
        else:
            bundle.file_path.unlink()
            if verbose:
                print(f"Pruned archive: {rel_path}")

            month_dir = bundle.file_path.parent
            if month_dir.is_dir() and not any(month_dir.iterdir()):
                month_dir.rmdir()

    symlink_path = repository_archive_directory.parent / f"{leaf_name}.bundle"
    if symlink_path.is_symlink():
        broken = False
        try:
            target = (symlink_path.parent / os.readlink(symlink_path)).resolve()
            if not target.exists():
                broken = True
        except OSError:
            broken = True

        if broken:
            if kept:
                newest = max(kept, key=lambda b: b.timestamp)
                update_latest_symlink(
                    repository_archive_directory,
                    newest.file_path,
                    leaf_name,
                    dry_run=dry_run,
                )
            elif not dry_run:
                symlink_path.unlink()

    return len(prunes)


def synchronize_remote_mirror(
    remote_url: str,
    mirror_directory: Path,
    verbose: bool,
) -> None:
    """Synchronizes a bare mirror repository for remote URLs."""
    if mirror_directory.exists():
        try:
            bare = run_git_command(
                ["rev-parse", "--is-bare-repository"],
                working_directory=mirror_directory,
            )
            if bare.stdout.strip() == "true":
                if verbose:
                    print(f"Updating existing bare mirror: {mirror_directory}")
                run_git_command(
                    ["remote", "update", "--prune"],
                    working_directory=mirror_directory,
                    capture_output=not verbose,
                )
                return
        except subprocess.CalledProcessError:
            pass
        shutil.rmtree(mirror_directory)

    if verbose:
        print(f"Cloning bare mirror from {remote_url} to {mirror_directory}...")
    mirror_directory.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--mirror", "--bare"]
    if verbose:
        args.append("--progress")
    args.extend([remote_url, str(mirror_directory)])
    run_git_command(args, capture_output=not verbose)


def archive_single_repository(
    source_identifier: str,
    destination_root: Path,
    retention_policy: RetentionPolicy,
    force: bool,
    dry_run: bool,
    keep_temp_repo: bool,
    custom_temp_directory: Path | None,
    verbose: bool,
) -> RepositoryExecutionSummary:
    """Processes a single repository, creating a verified bundle and applying retention."""
    is_remote = is_remote_repository_url(source_identifier)

    if is_remote:
        rel_repo_path = parse_remote_repository_relative_path(source_identifier)
        leaf_name = rel_repo_path.name
        working_git_path = None
    else:
        local_path = Path(source_identifier).resolve()
        if not local_path.exists():
            raise FileNotFoundError(f"Local repository does not exist: {local_path}")
        try:
            run_git_command(["rev-parse", "--git-dir"], working_directory=local_path)
        except subprocess.CalledProcessError as err:
            raise ValueError(
                f"Path is not a valid Git repository: {local_path}"
            ) from err

        inspect_local_repository_cleanliness(local_path)
        rel_repo_path = resolve_local_repository_relative_path(local_path)
        leaf_name = rel_repo_path.name
        working_git_path = local_path

    repo_archive_dir = destination_root / rel_repo_path
    canonical_symlink = repo_archive_dir.parent / f"{leaf_name}.bundle"

    print(f"Processing repository: {source_identifier} -> {rel_repo_path}")

    temp_mirror_dir: Path | None = None
    if is_remote:
        if custom_temp_directory is not None:
            base_temp = custom_temp_directory.resolve()
        elif keep_temp_repo:
            base_temp = Path.home() / ".cache" / "git_archivist"
        else:
            base_temp = Path(tempfile.gettempdir()) / "git_archivist_repos"

        temp_mirror_dir = (base_temp / rel_repo_path).with_suffix(".git")
        synchronize_remote_mirror(source_identifier, temp_mirror_dir, verbose=verbose)
        working_git_path = temp_mirror_dir

    bundle_created = False
    skipped_unchanged = False

    try:
        if not force and is_repository_unchanged(working_git_path, canonical_symlink):
            print(
                f"  Repository '{rel_repo_path}' is unchanged; skipping bundle creation."
            )
            skipped_unchanged = True
        else:
            now = datetime.now(timezone.utc)
            month_folder = now.strftime(MONTH_FORMAT)
            base_ts_name = now.strftime(TIMESTAMP_FORMAT)
            target_bundle = repo_archive_dir / month_folder / f"{base_ts_name}.bundle"

            counter = 1
            while target_bundle.exists():
                target_bundle = (
                    repo_archive_dir / month_folder / f"{base_ts_name}_{counter}.bundle"
                )
                counter += 1

            if dry_run:
                print(
                    f"  Would create bundle: {target_bundle.relative_to(destination_root)}"
                )
                update_latest_symlink(
                    repo_archive_dir, target_bundle, leaf_name, dry_run=True
                )
                bundle_created = True
            else:
                target_bundle.parent.mkdir(parents=True, exist_ok=True)
                if verbose:
                    print(
                        f"  Creating bundle: {target_bundle.relative_to(destination_root)}..."
                    )

                bundle_args = ["bundle", "create", str(target_bundle), "--all"]
                if verbose:
                    bundle_args.append("--progress")
                run_git_command(
                    bundle_args,
                    working_directory=working_git_path,
                    capture_output=not verbose,
                )

                if verbose:
                    print("  Verifying bundle integrity...")
                verify_bundle_integrity(
                    target_bundle, working_directory=working_git_path
                )

                update_latest_symlink(
                    repo_archive_dir, target_bundle, leaf_name, dry_run=False
                )
                size_str = format_file_size(target_bundle.stat().st_size)
                print(f"  Archived successfully: {target_bundle.name} ({size_str})")
                bundle_created = True

        pruned_count = apply_retention_policy(
            repository_archive_directory=repo_archive_dir,
            leaf_name=leaf_name,
            policy=retention_policy,
            dry_run=dry_run,
            verbose=verbose,
        )
        if pruned_count > 0:
            action_text = "Would prune" if dry_run else "Pruned"
            print(f"  Retention: {action_text} {pruned_count} historical bundles.")

    finally:
        if (
            is_remote
            and temp_mirror_dir is not None
            and not keep_temp_repo
            and temp_mirror_dir.exists()
        ):
            if verbose:
                print(f"  Removing temporary mirror: {temp_mirror_dir}")
            shutil.rmtree(temp_mirror_dir)

    return RepositoryExecutionSummary(
        repository_identifier=source_identifier,
        target_relative_path=rel_repo_path,
        bundle_created=bundle_created,
        skipped_unchanged=skipped_unchanged,
        bundles_pruned_count=pruned_count,
    )


def list_archived_repositories(destination_root: Path) -> None:
    """Lists all archived repositories and their snapshot bundles in destination."""
    if not destination_root.is_dir():
        print(f"Destination directory does not exist: {destination_root}")
        return

    discovered: list[Path] = []
    for candidate in destination_root.glob("**/*"):
        if (
            candidate.is_dir()
            and not MONTH_DIRECTORY_PATTERN.match(candidate.name)
            and any(
                sub.is_dir() and MONTH_DIRECTORY_PATTERN.match(sub.name)
                for sub in candidate.iterdir()
            )
        ):
            discovered.append(candidate)

    if not discovered:
        print(f"No git archives found in: {destination_root}")
        return

    discovered.sort(key=lambda p: str(p.relative_to(destination_root)))

    print(f"Archived Repositories in {destination_root}:")
    print("=" * 80)

    for repo_dir in discovered:
        rel_repo = repo_dir.relative_to(destination_root)
        bundles = collect_repository_bundles(repo_dir)
        leaf_name = repo_dir.name
        symlink_path = repo_dir.parent / f"{leaf_name}.bundle"

        symlink_target = ""
        if symlink_path.is_symlink():
            try:
                symlink_target = os.readlink(symlink_path)
            except OSError:
                symlink_target = "(broken)"

        total_bytes = sum(b.size_in_bytes for b in bundles)
        total_size_str = format_file_size(total_bytes)

        print(f"\nRepository: {rel_repo}")
        if symlink_target:
            print(
                f"  Latest symlink: {symlink_path.relative_to(destination_root)} -> {symlink_target}"
            )
        print(f"  Snapshots ({len(bundles)} total, {total_size_str}):")

        for bundle in bundles:
            rel_bundle = bundle.file_path.relative_to(repo_dir)
            target_rel = str(Path(repo_dir.name) / rel_bundle)
            is_latest = target_rel == symlink_target
            marker = " [latest]" if is_latest else ""
            ts_str = bundle.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            size_str = format_file_size(bundle.size_in_bytes)
            print(f"    {rel_bundle!s:<28} {size_str:>10}  {ts_str}{marker}")

    print("\n" + "=" * 80)


def ensure_destination_available(destination: Path, dry_run: bool = False) -> None:
    """Ensures destination exists and is writable, or can be created with parents=False."""
    if destination.exists():
        if not destination.is_dir():
            raise NotADirectoryError(f"Destination is not a directory: {destination}")
        if not os.access(destination, os.W_OK):
            raise PermissionError(
                f"Destination directory is not writable: {destination}"
            )
        return

    try:
        if not dry_run:
            destination.mkdir(parents=False, exist_ok=True)
        else:
            parent = destination.parent
            if not parent.exists() or not parent.is_dir():
                raise FileNotFoundError(
                    f"Destination parent directory does not exist: {parent}"
                )
            if not os.access(parent, os.W_OK):
                raise PermissionError(
                    f"Destination parent directory is not writable: {parent}"
                )
    except (FileNotFoundError, PermissionError, OSError) as error:
        raise OSError(
            f"Destination directory does not exist and cannot be created: {error}"
        ) from error


def build_argument_parser() -> argparse.ArgumentParser:
    """Constructs the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="git_archivist.py",
        description="Archive Git repositories into verified bundles with restic-style retention management.",
    )

    parser.add_argument(
        "repositories",
        nargs="*",
        metavar="REPOSITORY",
        help="Local repository directories or remote Git clone URLs (HTTPS/SSH) to archive.",
    )
    parser.add_argument(
        "-i",
        "--input-file",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to a text file containing repository URLs/paths (one per line), or '-' for standard input.",
    )
    parser.add_argument(
        "--write-input-file",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="Write or update repository list file with deduplicated repositories. Defaults to -i file if PATH is omitted.",
    )
    parser.add_argument(
        "-d",
        "--destination",
        type=Path,
        required=True,
        metavar="PATH",
        help="Target root directory where archives will be organized and stored.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force creation of a new bundle even if repository refs are unchanged.",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Simulate archival and retention actions without modifying the filesystem.",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List all archived repositories and their bundle snapshots in the destination.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed progress logging.",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Base directory for temporary clone mirrors (defaults to system temp or user cache).",
    )
    parser.add_argument(
        "--keep-temp-repo",
        action="store_true",
        help="Preserve temporary bare clones instead of deleting them after archival.",
    )

    retention_group = parser.add_argument_group(
        "Retention Options (restic forget style)",
        "Configure automated pruning of historical bundle archives. Disabled if none specified.",
    )
    retention_group.add_argument(
        "--keep-last",
        type=int,
        metavar="N",
        help="Keep the N most recent bundles.",
    )
    retention_group.add_argument(
        "--keep-daily",
        type=int,
        metavar="N",
        help="Keep the most recent bundle for each of the last N days.",
    )
    retention_group.add_argument(
        "--keep-weekly",
        type=int,
        metavar="N",
        help="Keep the most recent bundle for each of the last N weeks.",
    )
    retention_group.add_argument(
        "--keep-monthly",
        type=int,
        metavar="N",
        help="Keep the most recent bundle for each of the last N months.",
    )
    retention_group.add_argument(
        "--keep-yearly",
        type=int,
        metavar="N",
        help="Keep the most recent bundle for each of the last N years.",
    )

    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Main program entry point."""
    parser = build_argument_parser()
    parsed_args = parser.parse_args(arguments)

    destination_root = parsed_args.destination.resolve()

    try:
        ensure_destination_available(destination_root, dry_run=parsed_args.dry_run)
    except (NotADirectoryError, PermissionError, OSError) as error:
        sys.stderr.write(f"Error: {error}\n")
        return 1

    if parsed_args.list:
        list_archived_repositories(destination_root)
        return 0

    file_repositories: list[str] = []
    if parsed_args.input_file is not None:
        try:
            file_repositories = parse_repository_list_file(
                parsed_args.input_file,
                is_stdin=(parsed_args.input_file == "-"),
            )
        except (FileNotFoundError, OSError, PermissionError) as error:
            sys.stderr.write(f"Error: {error}\n")
            return 1

    raw_repositories = list(parsed_args.repositories) + file_repositories
    combined_repositories = deduplicate_repository_sources(raw_repositories)

    if not combined_repositories:
        parser.error(
            "At least one repository path or URL must be specified via arguments or -i/--input-file unless --list is used."
        )

    if parsed_args.write_input_file is not None:
        target_write_string = parsed_args.write_input_file
        if target_write_string == "":
            if parsed_args.input_file is None:
                sys.stderr.write(
                    "Error: --write-input-file requires an explicit PATH when -i/--input-file is omitted.\n"
                )
                return 1
            if parsed_args.input_file == "-":
                sys.stderr.write(
                    "Error: Cannot write to standard input; specify an explicit PATH for --write-input-file.\n"
                )
                return 1
            target_write_path = Path(parsed_args.input_file).resolve()
        else:
            target_write_path = Path(target_write_string).resolve()

        try:
            update_or_write_repository_list_file(
                target_path=target_write_path,
                candidate_sources=combined_repositories,
                dry_run=parsed_args.dry_run,
                verbose=parsed_args.verbose,
            )
        except (OSError, PermissionError) as error:
            sys.stderr.write(
                f"Error writing repository list file '{target_write_path}': {error}\n"
            )
            return 1

    retention_policy = RetentionPolicy(
        keep_last=parsed_args.keep_last,
        keep_daily=parsed_args.keep_daily,
        keep_weekly=parsed_args.keep_weekly,
        keep_monthly=parsed_args.keep_monthly,
        keep_yearly=parsed_args.keep_yearly,
    )

    summaries: list[RepositoryExecutionSummary] = []

    for repository_source in combined_repositories:
        try:
            summary = archive_single_repository(
                source_identifier=repository_source,
                destination_root=destination_root,
                retention_policy=retention_policy,
                force=parsed_args.force,
                dry_run=parsed_args.dry_run,
                keep_temp_repo=parsed_args.keep_temp_repo,
                custom_temp_directory=parsed_args.temp_dir,
                verbose=parsed_args.verbose,
            )
            summaries.append(summary)
        except (
            subprocess.CalledProcessError,
            OSError,
            ValueError,
            FileNotFoundError,
        ) as error:
            sys.stderr.write(f"Error processing '{repository_source}': {error}\n")
            summaries.append(
                RepositoryExecutionSummary(
                    repository_identifier=repository_source,
                    target_relative_path=Path(repository_source),
                    bundle_created=False,
                    skipped_unchanged=False,
                    bundles_pruned_count=0,
                    error_message=str(error),
                )
            )

    created_count = sum(1 for s in summaries if s.bundle_created)
    skipped_count = sum(1 for s in summaries if s.skipped_unchanged)
    failed_count = sum(1 for s in summaries if s.error_message is not None)

    print("\n" + "=" * 80)
    print("Archival Batch Summary:")
    print(f"  Total repositories: {len(summaries)}")
    print(f"  Bundles created:    {created_count}")
    print(f"  Skipped unchanged:  {skipped_count}")
    print(f"  Failed:             {failed_count}")
    print("=" * 80)

    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Git repository archival utility.

Backs up complete Git repositories (all branches, tags, and commits) into
verified standalone bundle files organized by repository path and month.
Includes change detection to avoid duplicate archives, temp repository reuse,
and a retention policy engine modeled after restic forget.
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
            criterion is not None
            for criterion in (
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
    units = ("B", "KB", "MB", "GB", "TB")
    scaled_size = float(size_in_bytes)
    for unit in units:
        if scaled_size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(scaled_size)} B"
            return f"{scaled_size:.1f} {unit}"
        scaled_size /= 1024.0
    return f"{scaled_size:.1f} TB"


def run_git_command(
    arguments: list[str],
    working_directory: Path | None = None,
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Executes a git command with standard options and error reporting."""
    command = ["git"]
    if working_directory is not None:
        command.extend(["-C", str(working_directory)])
    command.extend(arguments)

    return subprocess.run(
        command,
        capture_output=capture_output,
        text=True,
        check=check,
    )


def is_remote_repository_url(source_address: str) -> bool:
    """Determines whether the source string is a remote Git URL."""
    remote_schemes = ("http://", "https://", "git://", "ssh://", "file://")
    if any(source_address.startswith(scheme) for scheme in remote_schemes):
        return True

    # Windows drive letter (e.g. C:\repo or D:/repo) is always a local path
    if re.match(r"^[a-zA-Z]:[\\/]", source_address):
        return False

    # Windows UNC network share path (e.g. \\server\share)
    if source_address.startswith(("\\\\", "//")):
        return False

    # Existing local filesystem entries are never remote URLs
    if Path(source_address).exists():
        return False

    # Identify SCP-style addresses (e.g. git@github.com:org/repo.git or host.com:org/repo.git)
    if ":" in source_address and not source_address.startswith(("/", ".")):
        host_segment, path_segment = source_address.split(":", 1)
        is_valid_scp_host = (
            len(host_segment) > 1
            and "/" not in host_segment
            and "\\" not in host_segment
        )
        if is_valid_scp_host and bool(path_segment.strip()):
            return True

    return False


def parse_remote_repository_relative_path(remote_url: str) -> Path:
    """Extracts the org/repo relative filesystem path from a remote URL."""
    cleaned_url = remote_url.strip().removesuffix(".git").rstrip("/")

    # Handle SCP-style addresses (git@host:org/repo)
    if ":" in cleaned_url and not any(
        cleaned_url.startswith(scheme)
        for scheme in ("http://", "https://", "git://", "ssh://")
    ):
        _, path_part = cleaned_url.split(":", 1)
        path_segments = [seg for seg in path_part.strip("/").split("/") if seg]
        if path_segments:
            return Path(*path_segments)

    # Handle standard URLs
    parsed_url = urlparse(cleaned_url)
    raw_path_segments = [seg for seg in parsed_url.path.strip("/").split("/") if seg]
    if not raw_path_segments:
        raise ValueError(f"Unable to extract repository path from URL: {remote_url}")

    return Path(*raw_path_segments)


def resolve_local_repository_relative_path(repository_path: Path) -> Path:
    """
    Resolves the relative path for a local repository.

    Prefers extracting org/repo from the remote origin URL if configured,
    falling back to the local directory name.
    """
    try:
        remote_output = run_git_command(
            ["remote", "get-url", "origin"],
            working_directory=repository_path,
        )
        origin_url = remote_output.stdout.strip()
        if origin_url:
            return parse_remote_repository_relative_path(origin_url)
    except (subprocess.CalledProcessError, ValueError):
        pass

    # Check any other remote if origin was not present
    try:
        remotes_output = run_git_command(
            ["remote"],
            working_directory=repository_path,
        )
        remote_names = [
            name for name in remotes_output.stdout.splitlines() if name.strip()
        ]
        for remote_name in remote_names:
            try:
                remote_url_output = run_git_command(
                    ["remote", "get-url", remote_name],
                    working_directory=repository_path,
                )
                remote_url = remote_url_output.stdout.strip()
                if remote_url:
                    return parse_remote_repository_relative_path(remote_url)
            except (subprocess.CalledProcessError, ValueError):
                continue
    except subprocess.CalledProcessError:
        pass

    return Path(repository_path.name)


def inspect_local_repository_cleanliness(repository_path: Path) -> bool:
    """
    Verifies working tree cleanliness of a local repository.

    Warns on stderr if uncommitted or untracked changes are detected.
    """
    try:
        bare_check = run_git_command(
            ["rev-parse", "--is-bare-repository"],
            working_directory=repository_path,
        )
        if bare_check.stdout.strip() == "true":
            return True
    except subprocess.CalledProcessError:
        return True

    try:
        status_output = run_git_command(
            ["status", "--porcelain"],
            working_directory=repository_path,
        )
        if status_output.stdout.strip():
            sys.stderr.write(
                f"Warning: Repository '{repository_path}' has uncommitted changes "
                "or untracked files; archiving committed refs and stashes only.\n"
            )
            return False
    except subprocess.CalledProcessError:
        pass

    return True


def fetch_repository_references(repository_path: Path) -> dict[str, str]:
    """Retrieves all references and their commit hashes from a Git repository."""
    try:
        show_ref_output = run_git_command(
            ["show-ref", "--head"],
            working_directory=repository_path,
        )
    except subprocess.CalledProcessError as process_error:
        # Exit code 1 from show-ref indicates an empty repository with no refs
        if process_error.returncode == 1:
            return {}
        raise

    references_map: dict[str, str] = {}
    for line in show_ref_output.stdout.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        parts = line_stripped.split(maxsplit=1)
        if len(parts) == 2:
            commit_hash, reference_name = parts
            references_map[reference_name] = commit_hash

    # Discover active worktree HEADs which git bundle --all packages
    try:
        git_path_output = run_git_command(
            ["rev-parse", "--git-path", "worktrees"],
            working_directory=repository_path,
        )
        worktrees_directory = Path(git_path_output.stdout.strip())
        if not worktrees_directory.is_absolute():
            worktrees_directory = repository_path / worktrees_directory

        if worktrees_directory.is_dir():
            for worktree_entry in worktrees_directory.iterdir():
                if worktree_entry.is_dir() and (worktree_entry / "HEAD").is_file():
                    worktree_ref_name = f"worktrees/{worktree_entry.name}/HEAD"
                    rev_parse_output = run_git_command(
                        ["rev-parse", worktree_ref_name],
                        working_directory=repository_path,
                    )
                    references_map[worktree_ref_name] = rev_parse_output.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        pass

    return references_map


def fetch_bundle_references(bundle_path: Path) -> dict[str, str]:
    """Extracts reference names and commit hashes directly from a Git bundle."""
    list_heads_output = run_git_command(
        ["bundle", "list-heads", str(bundle_path)],
    )

    references_map: dict[str, str] = {}
    for line in list_heads_output.stdout.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        parts = line_stripped.split(maxsplit=1)
        if len(parts) == 2:
            commit_hash, reference_name = parts
            references_map[reference_name] = commit_hash

    return references_map


def is_repository_unchanged(repository_path: Path, latest_bundle_path: Path) -> bool:
    """Compares current repository references with the latest archived bundle."""
    if not latest_bundle_path.is_file():
        return False

    try:
        bundle_references = fetch_bundle_references(latest_bundle_path)
        repository_references = fetch_repository_references(repository_path)
        if not repository_references:
            return False
        return bundle_references == repository_references
    except (subprocess.CalledProcessError, OSError):
        return False


def verify_bundle_integrity(
    bundle_path: Path, working_directory: Path | None = None
) -> None:
    """Verifies that a Git bundle is valid and complete."""
    if working_directory is not None:
        run_git_command(
            ["bundle", "verify", str(bundle_path)],
            working_directory=working_directory,
        )
        return

    try:
        run_git_command(["bundle", "verify", str(bundle_path)])
    except subprocess.CalledProcessError as process_error:
        if "need a repository to verify a bundle" in process_error.stderr:
            with tempfile.TemporaryDirectory(
                prefix="git_archivist_verify_"
            ) as ephemeral_repo:
                run_git_command(["init", "--bare", ephemeral_repo])
                run_git_command(
                    ["bundle", "verify", str(bundle_path)],
                    working_directory=Path(ephemeral_repo),
                )
        else:
            raise


def update_latest_symlink(
    repository_archive_directory: Path,
    target_bundle_path: Path,
    leaf_name: str,
    dry_run: bool,
) -> None:
    """
    Atomically creates or updates the canonical repo_name.bundle symlink
    one directory above repository_archive_directory.

    Uses a relative symlink target (e.g. repo/202609/20260902_223000.bundle)
    so the archive directory can be moved safely.
    """
    symlink_parent_directory = repository_archive_directory.parent
    symlink_path = symlink_parent_directory / f"{leaf_name}.bundle"
    relative_target = (
        Path(repository_archive_directory.name)
        / target_bundle_path.parent.name
        / target_bundle_path.name
    )

    if dry_run:
        print(f"Would update symlink: {symlink_path.name} -> {relative_target}")
        return

    symlink_parent_directory.mkdir(parents=True, exist_ok=True)
    temporary_symlink_path = (
        symlink_parent_directory / f"{leaf_name}.bundle.tmp_{os.getpid()}"
    )

    if temporary_symlink_path.is_symlink() or temporary_symlink_path.exists():
        temporary_symlink_path.unlink()

    temporary_symlink_path.symlink_to(relative_target)
    temporary_symlink_path.replace(symlink_path)


def collect_repository_bundles(
    repository_archive_directory: Path,
) -> list[ArchiveBundle]:
    """
    Discovers all archived .bundle files within monthly subdirectories.

    Returns the archives sorted chronologically descending (newest first).
    """
    discovered_bundles: list[ArchiveBundle] = []

    if not repository_archive_directory.is_dir():
        return discovered_bundles

    for child_entry in repository_archive_directory.iterdir():
        if child_entry.is_dir() and MONTH_DIRECTORY_PATTERN.match(child_entry.name):
            for candidate_file in child_entry.glob("*.bundle"):
                if candidate_file.is_symlink():
                    continue
                match = TIMESTAMP_FILENAME_PATTERN.match(candidate_file.name)
                if match:
                    timestamp_string = f"{match.group(1)}_{match.group(2)}"
                    try:
                        parsed_timestamp = datetime.strptime(
                            timestamp_string, TIMESTAMP_FORMAT
                        ).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue

                    file_size = candidate_file.stat().st_size
                    discovered_bundles.append(
                        ArchiveBundle(
                            file_path=candidate_file,
                            timestamp=parsed_timestamp,
                            size_in_bytes=file_size,
                        )
                    )

    # Sort descending: newest bundle first
    discovered_bundles.sort(
        key=lambda item: (item.timestamp, item.file_path.name), reverse=True
    )
    return discovered_bundles


def collect_newest_bundle_per_period(
    sorted_bundles: list[ArchiveBundle],
    retention_limit: int | None,
    extract_period_key: Callable[[datetime], PeriodKey],
) -> list[ArchiveBundle]:
    """Selects the newest bundle for each unique time period up to retention_limit."""
    if retention_limit is None or retention_limit <= 0:
        return []

    newest_bundle_per_period: dict[PeriodKey, ArchiveBundle] = {}
    for bundle in sorted_bundles:
        period_key = extract_period_key(bundle.timestamp)
        if period_key not in newest_bundle_per_period:
            newest_bundle_per_period[period_key] = bundle

    return list(newest_bundle_per_period.values())[:retention_limit]


def evaluate_retention_candidates(
    bundles: list[ArchiveBundle],
    policy: RetentionPolicy,
) -> tuple[set[ArchiveBundle], set[ArchiveBundle]]:
    """
    Evaluates archive bundles against retention policies modeled after restic forget.

    Returns a tuple of (kept_bundles, prune_candidates).
    """
    if not policy.is_active or not bundles:
        return set(bundles), set()

    kept_bundles: set[ArchiveBundle] = set()

    # Rule 1: Keep last N snapshots
    if policy.keep_last is not None and policy.keep_last > 0:
        kept_bundles.update(bundles[: policy.keep_last])

    # Rule 2: Keep daily snapshots
    kept_bundles.update(
        collect_newest_bundle_per_period(
            bundles, policy.keep_daily, lambda timestamp: timestamp.date()
        )
    )

    # Rule 3: Keep weekly snapshots
    kept_bundles.update(
        collect_newest_bundle_per_period(
            bundles,
            policy.keep_weekly,
            lambda timestamp: (
                timestamp.isocalendar().year,
                timestamp.isocalendar().week,
            ),
        )
    )

    # Rule 4: Keep monthly snapshots
    kept_bundles.update(
        collect_newest_bundle_per_period(
            bundles,
            policy.keep_monthly,
            lambda timestamp: (timestamp.year, timestamp.month),
        )
    )

    # Rule 5: Keep yearly snapshots
    kept_bundles.update(
        collect_newest_bundle_per_period(
            bundles, policy.keep_yearly, lambda timestamp: timestamp.year
        )
    )

    prune_candidates = set(bundles) - kept_bundles
    return kept_bundles, prune_candidates


def apply_retention_policy(
    repository_archive_directory: Path,
    leaf_name: str,
    policy: RetentionPolicy,
    dry_run: bool,
    verbose: bool,
) -> int:
    """
    Executes retention evaluation, removing expired archives and cleaning empty directories.

    Returns the count of pruned bundles.
    """
    if not policy.is_active:
        return 0

    all_bundles = collect_repository_bundles(repository_archive_directory)
    if not all_bundles:
        return 0

    kept_bundles, prune_candidates = evaluate_retention_candidates(all_bundles, policy)
    if not prune_candidates:
        if verbose:
            print(f"Retention policy: all {len(kept_bundles)} bundles retained.")
        return 0

    # Sort prune candidates chronologically for readable logging
    sorted_prune_list = sorted(prune_candidates, key=lambda item: item.timestamp)

    for bundle in sorted_prune_list:
        relative_display_path = bundle.file_path.relative_to(
            repository_archive_directory
        )
        formatted_size = format_file_size(bundle.size_in_bytes)
        if dry_run:
            print(
                f"Would prune: {relative_display_path} "
                f"({formatted_size}, {bundle.timestamp.strftime('%Y-%m-%d %H:%M:%S')})"
            )
        else:
            bundle.file_path.unlink()
            if verbose:
                print(f"Pruned archive: {relative_display_path}")

            # Prune parent monthly directory if now empty
            monthly_parent_directory = bundle.file_path.parent
            if monthly_parent_directory.is_dir() and not any(
                monthly_parent_directory.iterdir()
            ):
                monthly_parent_directory.rmdir()

    # Re-evaluate latest symlink health
    symlink_path = repository_archive_directory.parent / f"{leaf_name}.bundle"
    if symlink_path.is_symlink():
        symlink_broken = False
        try:
            target_path = (symlink_path.parent / os.readlink(symlink_path)).resolve()
            if not target_path.exists():
                symlink_broken = True
        except OSError:
            symlink_broken = True

        if symlink_broken:
            if kept_bundles:
                remaining_newest = max(kept_bundles, key=lambda item: item.timestamp)
                update_latest_symlink(
                    repository_archive_directory,
                    remaining_newest.file_path,
                    leaf_name,
                    dry_run=dry_run,
                )
            elif not dry_run:
                symlink_path.unlink()

    return len(prune_candidates)


def synchronize_remote_mirror(
    remote_url: str,
    mirror_directory: Path,
    verbose: bool,
) -> None:
    """
    Synchronizes a bare mirror repository for remote URLs.

    If an existing mirror exists, updates it incrementally; otherwise clones fresh.
    """
    if mirror_directory.exists():
        is_bare = False
        try:
            bare_check = run_git_command(
                ["rev-parse", "--is-bare-repository"],
                working_directory=mirror_directory,
            )
            is_bare = bare_check.stdout.strip() == "true"
        except subprocess.CalledProcessError:
            is_bare = False

        if is_bare:
            if verbose:
                print(f"Updating existing bare mirror: {mirror_directory}")
            run_git_command(
                ["remote", "update", "--prune"],
                working_directory=mirror_directory,
                capture_output=not verbose,
            )
            return

        # Existing directory is not a valid bare repo; recreate
        shutil.rmtree(mirror_directory)

    if verbose:
        print(f"Cloning bare mirror from {remote_url} to {mirror_directory}...")
    mirror_directory.parent.mkdir(parents=True, exist_ok=True)
    clone_arguments = ["clone", "--mirror", "--bare"]
    if verbose:
        clone_arguments.append("--progress")
    clone_arguments.extend([remote_url, str(mirror_directory)])
    run_git_command(clone_arguments, capture_output=not verbose)


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

    # 1. Resolve repository path and leaf identifier
    if is_remote:
        relative_repo_path = parse_remote_repository_relative_path(source_identifier)
        leaf_name = relative_repo_path.name
        source_is_local = False
    else:
        local_repo_path = Path(source_identifier).resolve()
        if not local_repo_path.exists():
            raise FileNotFoundError(
                f"Local repository does not exist: {local_repo_path}"
            )

        # Verify it is a git directory
        try:
            run_git_command(
                ["rev-parse", "--git-dir"], working_directory=local_repo_path
            )
        except subprocess.CalledProcessError as err:
            raise ValueError(
                f"Path is not a valid Git repository: {local_repo_path}"
            ) from err

        inspect_local_repository_cleanliness(local_repo_path)
        relative_repo_path = resolve_local_repository_relative_path(local_repo_path)
        leaf_name = relative_repo_path.name
        source_is_local = True

    repository_archive_directory = destination_root / relative_repo_path
    canonical_symlink_path = repository_archive_directory.parent / f"{leaf_name}.bundle"

    print(f"Processing repository: {source_identifier} -> {relative_repo_path}")

    # 2. Prepare working Git directory (local directly, or mirror clone for remote)
    temp_mirror_directory: Path | None = None
    working_git_path: Path

    if source_is_local:
        working_git_path = Path(source_identifier).resolve()
    else:
        if custom_temp_directory is not None:
            base_temp = custom_temp_directory.resolve()
        elif keep_temp_repo:
            base_temp = Path.home() / ".cache" / "git_archivist"
        else:
            base_temp = Path(tempfile.gettempdir()) / "git_archivist_repos"

        temp_mirror_directory = (base_temp / relative_repo_path).with_suffix(".git")
        synchronize_remote_mirror(
            source_identifier,
            temp_mirror_directory,
            verbose=verbose,
        )
        working_git_path = temp_mirror_directory

    bundle_created = False
    skipped_unchanged = False

    try:
        # 3. Check for unchanged state
        if not force and is_repository_unchanged(
            working_git_path, canonical_symlink_path
        ):
            print(
                f"  Repository '{relative_repo_path}' is unchanged; skipping bundle creation."
            )
            skipped_unchanged = True
        else:
            # 4. Construct target destination path
            current_time = datetime.now(timezone.utc)
            month_folder_name = current_time.strftime(MONTH_FORMAT)
            base_timestamp_name = current_time.strftime(TIMESTAMP_FORMAT)
            timestamp_file_name = f"{base_timestamp_name}.bundle"
            target_bundle_path = (
                repository_archive_directory / month_folder_name / timestamp_file_name
            )
            collision_counter = 1
            while target_bundle_path.exists():
                timestamp_file_name = (
                    f"{base_timestamp_name}_{collision_counter}.bundle"
                )
                target_bundle_path = (
                    repository_archive_directory
                    / month_folder_name
                    / timestamp_file_name
                )
                collision_counter += 1

            if dry_run:
                print(
                    f"  Would create bundle: {target_bundle_path.relative_to(destination_root)}"
                )
                update_latest_symlink(
                    repository_archive_directory,
                    target_bundle_path,
                    leaf_name,
                    dry_run=True,
                )
                bundle_created = True
            else:
                target_bundle_path.parent.mkdir(parents=True, exist_ok=True)
                if verbose:
                    print(
                        f"  Creating bundle: {target_bundle_path.relative_to(destination_root)}..."
                    )

                bundle_arguments = [
                    "bundle",
                    "create",
                    str(target_bundle_path),
                    "--all",
                ]
                if verbose:
                    bundle_arguments.append("--progress")
                run_git_command(
                    bundle_arguments,
                    working_directory=working_git_path,
                    capture_output=not verbose,
                )

                if verbose:
                    print("  Verifying bundle integrity...")
                verify_bundle_integrity(
                    target_bundle_path, working_directory=working_git_path
                )

                update_latest_symlink(
                    repository_archive_directory,
                    target_bundle_path,
                    leaf_name,
                    dry_run=False,
                )
                bundle_size = target_bundle_path.stat().st_size
                print(
                    f"  Archived successfully: {target_bundle_path.name} "
                    f"({format_file_size(bundle_size)})"
                )
                bundle_created = True

        # 5. Apply retention policy
        pruned_count = apply_retention_policy(
            repository_archive_directory=repository_archive_directory,
            leaf_name=leaf_name,
            policy=retention_policy,
            dry_run=dry_run,
            verbose=verbose,
        )
        if pruned_count > 0:
            action_text = "Would prune" if dry_run else "Pruned"
            print(f"  Retention: {action_text} {pruned_count} historical bundles.")

    finally:
        # 6. Clean up temporary mirror if requested
        if (
            is_remote
            and temp_mirror_directory is not None
            and not keep_temp_repo
            and temp_mirror_directory.exists()
        ):
            if verbose:
                print(f"  Removing temporary mirror: {temp_mirror_directory}")
            shutil.rmtree(temp_mirror_directory)

    return RepositoryExecutionSummary(
        repository_identifier=source_identifier,
        target_relative_path=relative_repo_path,
        bundle_created=bundle_created,
        skipped_unchanged=skipped_unchanged,
        bundles_pruned_count=pruned_count,
    )


def list_archived_repositories(destination_root: Path) -> None:
    """Lists all archived repositories and their snapshot bundles in destination."""
    if not destination_root.is_dir():
        print(f"Destination directory does not exist: {destination_root}")
        return

    # Find all directories that contain monthly archive folders
    discovered_repos: list[Path] = []
    for candidate_dir in destination_root.glob("**/*"):
        if not candidate_dir.is_dir() or MONTH_DIRECTORY_PATTERN.match(
            candidate_dir.name
        ):
            continue
        has_monthly_folder = any(
            sub.is_dir() and MONTH_DIRECTORY_PATTERN.match(sub.name)
            for sub in candidate_dir.iterdir()
        )
        if has_monthly_folder:
            discovered_repos.append(candidate_dir)

    if not discovered_repos:
        print(f"No git archives found in: {destination_root}")
        return

    # Sort repositories alphabetically by relative path
    discovered_repos.sort(key=lambda p: str(p.relative_to(destination_root)))

    print(f"Archived Repositories in {destination_root}:")
    print("=" * 80)

    for repo_directory in discovered_repos:
        relative_repo = repo_directory.relative_to(destination_root)
        bundles = collect_repository_bundles(repo_directory)
        leaf_name = repo_directory.name
        symlink_path = repo_directory.parent / f"{leaf_name}.bundle"

        symlink_target_name = ""
        if symlink_path.is_symlink():
            try:
                symlink_target_name = os.readlink(symlink_path)
            except OSError:
                symlink_target_name = "(broken)"

        total_bytes = sum(b.size_in_bytes for b in bundles)
        total_size_string = format_file_size(total_bytes)

        print(f"\nRepository: {relative_repo}")
        if symlink_target_name:
            print(
                f"  Latest symlink: {symlink_path.relative_to(destination_root)} -> {symlink_target_name}"
            )
        print(f"  Snapshots ({len(bundles)} total, {total_size_string}):")

        for bundle in bundles:
            relative_bundle_path = bundle.file_path.relative_to(repo_directory)
            bundle_target_relative = str(
                Path(repo_directory.name) / relative_bundle_path
            )
            is_latest = bundle_target_relative == symlink_target_name
            latest_marker = " [latest]" if is_latest else ""
            timestamp_display = bundle.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            size_display = format_file_size(bundle.size_in_bytes)
            print(
                f"    {relative_bundle_path!s:<28} {size_display:>10}  {timestamp_display}{latest_marker}"
            )

    print("\n" + "=" * 80)


def ensure_destination_available(destination: Path, dry_run: bool = False) -> None:
    """Ensures the destination exists and is writable, or can be created with parents=False."""
    if destination.exists():
        if not destination.is_dir():
            raise NotADirectoryError(f"Destination is not a directory: {destination}")
        if not os.access(destination, os.W_OK):
            raise PermissionError(
                f"Destination directory is not writable: {destination}"
            )
        return

    # If destination does not exist, it must be creatable directly inside an existing parent
    try:
        if not dry_run:
            destination.mkdir(parents=False, exist_ok=True)
        else:
            parent_directory = destination.parent
            if not parent_directory.exists() or not parent_directory.is_dir():
                raise FileNotFoundError(
                    f"Destination parent directory does not exist: {parent_directory}"
                )
            if not os.access(parent_directory, os.W_OK):
                raise PermissionError(
                    f"Destination parent directory is not writable: {parent_directory}"
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

    # Handle list action
    if parsed_args.list:
        list_archived_repositories(destination_root)
        return 0

    if not parsed_args.repositories:
        parser.error(
            "At least one repository path or URL must be specified unless --list is used."
        )

    retention_policy = RetentionPolicy(
        keep_last=parsed_args.keep_last,
        keep_daily=parsed_args.keep_daily,
        keep_weekly=parsed_args.keep_weekly,
        keep_monthly=parsed_args.keep_monthly,
        keep_yearly=parsed_args.keep_yearly,
    )

    summaries: list[RepositoryExecutionSummary] = []

    for repository_source in parsed_args.repositories:
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

    # Print batch summary
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

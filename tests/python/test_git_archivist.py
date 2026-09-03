"""Unit and integration tests for Git repository archival utility."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.git_archivist import (
    ArchiveBundle,
    RetentionPolicy,
    apply_retention_policy,
    collect_repository_bundles,
    evaluate_retention_candidates,
    inspect_local_repository_cleanliness,
    is_remote_repository_url,
    main,
    parse_remote_repository_relative_path,
    resolve_local_repository_relative_path,
    update_latest_symlink,
    verify_bundle_integrity,
)


class TestGitArchivist(unittest.TestCase):
    """Test suite covering parsing, bundling, change detection, and retention."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_directory.name)
        self.repo_directory = self.root_path / "test_repo"
        self.repo_directory.mkdir()
        self.destination_directory = self.root_path / "archives"
        self.destination_directory.mkdir()

        # Initialize local test repo
        self._run_git(["init", str(self.repo_directory)])
        self._run_git(
            ["config", "user.email", "test@example.com"],
            cwd=self.repo_directory,
        )
        self._run_git(
            ["config", "user.name", "Test Archivist"],
            cwd=self.repo_directory,
        )
        self._run_git(
            ["config", "commit.gpgsign", "false"],
            cwd=self.repo_directory,
        )

        (self.repo_directory / "README.md").write_text("# Test Repo\n")
        self._run_git(["add", "."], cwd=self.repo_directory)
        self._run_git(["commit", "-m", "Initial commit"], cwd=self.repo_directory)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def _run_git(
        self, arguments: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        command = ["git"]
        if cwd is not None:
            command.extend(["-C", str(cwd)])
        command.extend(arguments)
        return subprocess.run(command, capture_output=True, text=True, check=True)

    def test_url_and_path_parsing(self) -> None:
        """Tests org/repo extraction from URLs and local repos."""
        https_url = "https://github.com/example-org/sample-repo.git"
        self.assertEqual(
            parse_remote_repository_relative_path(https_url),
            Path("example-org/sample-repo"),
        )

        ssh_url = "git@github.com:example-org/sample-repo.git"
        self.assertEqual(
            parse_remote_repository_relative_path(ssh_url),
            Path("example-org/sample-repo"),
        )

        nested_gitlab_url = "https://gitlab.com/group/subgroup/project.git"
        self.assertEqual(
            parse_remote_repository_relative_path(nested_gitlab_url),
            Path("group/subgroup/project"),
        )

        self.assertTrue(is_remote_repository_url(https_url))
        self.assertTrue(is_remote_repository_url(ssh_url))
        self.assertFalse(is_remote_repository_url(str(self.repo_directory)))
        self.assertFalse(is_remote_repository_url("C:\\Projects\\repo.git"))

    def test_local_repo_with_remote_origin(self) -> None:
        """Tests that local repo uses origin remote's org/repo when available."""
        self._run_git(
            ["remote", "add", "origin", "https://github.com/my-org/core-lib.git"],
            cwd=self.repo_directory,
        )
        resolved_path = resolve_local_repository_relative_path(self.repo_directory)
        self.assertEqual(resolved_path, Path("my-org/core-lib"))

    def test_archive_creation_and_symlink(self) -> None:
        """Tests bundle creation, verify integrity, and symlink creation."""
        self._run_git(
            ["remote", "add", "origin", "https://github.com/my-org/core-lib.git"],
            cwd=self.repo_directory,
        )

        exit_code = main(
            ["-d", str(self.destination_directory), str(self.repo_directory)]
        )
        self.assertEqual(exit_code, 0)

        archive_directory = self.destination_directory / "my-org/core-lib"
        self.assertTrue(archive_directory.is_dir())

        symlink_path = archive_directory.parent / "core-lib.bundle"
        self.assertTrue(symlink_path.is_symlink())
        self.assertTrue(symlink_path.is_file())

        bundles = collect_repository_bundles(archive_directory)
        self.assertEqual(len(bundles), 1)

        # Verify bundle can be cloned
        restore_directory = self.root_path / "restored"
        self._run_git(["clone", str(symlink_path), str(restore_directory)])
        self.assertTrue((restore_directory / "README.md").is_file())

    def test_unchanged_repository_detection(self) -> None:
        """Tests that running archival again skips bundle creation if unchanged."""
        self._run_git(
            ["remote", "add", "origin", "https://github.com/my-org/core-lib.git"],
            cwd=self.repo_directory,
        )

        exit_code_first = main(
            ["-d", str(self.destination_directory), str(self.repo_directory)]
        )
        self.assertEqual(exit_code_first, 0)

        archive_directory = self.destination_directory / "my-org/core-lib"
        bundles_first = collect_repository_bundles(archive_directory)
        self.assertEqual(len(bundles_first), 1)

        # Second run without changes -> should skip
        exit_code_second = main(
            ["-d", str(self.destination_directory), str(self.repo_directory)]
        )
        self.assertEqual(exit_code_second, 0)
        bundles_second = collect_repository_bundles(archive_directory)
        self.assertEqual(len(bundles_second), 1)

        # Run with --force -> should create a second bundle
        exit_code_forced = main(
            [
                "-d",
                str(self.destination_directory),
                "-f",
                str(self.repo_directory),
            ]
        )
        self.assertEqual(exit_code_forced, 0)
        bundles_third = collect_repository_bundles(archive_directory)
        self.assertEqual(len(bundles_third), 2)

    def test_retention_policy_evaluation(self) -> None:
        """Tests restic-style retention policy logic."""
        now = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
        bundles = [
            ArchiveBundle(
                file_path=Path(f"b{index}"),
                timestamp=now - timedelta(days=index),
                size_in_bytes=1000,
            )
            for index in range(10)
        ]

        policy = RetentionPolicy(keep_last=3)
        kept, pruned = evaluate_retention_candidates(bundles, policy)
        self.assertEqual(len(kept), 3)
        self.assertEqual(len(pruned), 7)
        self.assertEqual(kept, set(bundles[:3]))

        # Daily policy
        daily_policy = RetentionPolicy(keep_daily=5)
        kept_daily, pruned_daily = evaluate_retention_candidates(bundles, daily_policy)
        self.assertEqual(len(kept_daily), 5)
        self.assertEqual(len(pruned_daily), 5)

    def test_retention_pruning_and_directory_cleanup(self) -> None:
        """Tests physical pruning of bundles and cleanup of empty monthly directories."""
        archive_directory = self.destination_directory / "my-org/dummy"
        month1 = archive_directory / "202601"
        month1.mkdir(parents=True)
        file1 = month1 / "20260101_100000.bundle"
        file1.write_text("bundle1")

        month2 = archive_directory / "202602"
        month2.mkdir()
        file2 = month2 / "20260201_100000.bundle"
        file2.write_text("bundle2")

        update_latest_symlink(archive_directory, file2, "dummy", dry_run=False)
        self.assertTrue((archive_directory.parent / "dummy.bundle").is_symlink())

        policy = RetentionPolicy(keep_last=1)
        pruned_count = apply_retention_policy(
            repository_archive_directory=archive_directory,
            leaf_name="dummy",
            policy=policy,
            dry_run=False,
            verbose=False,
        )

        self.assertEqual(pruned_count, 1)
        self.assertFalse(file1.exists())
        self.assertFalse(month1.exists())
        self.assertTrue(file2.exists())
        self.assertTrue(month2.exists())

    def test_remote_url_simulation(self) -> None:
        """Tests cloning from a remote URL (simulated with local bare repo)."""
        bare_repo_directory = self.root_path / "upstream.git"
        self._run_git(
            ["clone", "--bare", str(self.repo_directory), str(bare_repo_directory)]
        )

        remote_url = f"file://{bare_repo_directory}"
        exit_code = main(["-d", str(self.destination_directory), remote_url])
        self.assertEqual(exit_code, 0)

        # Verify bundled repo exists
        leaf_name = bare_repo_directory.stem
        found_bundles = list(
            self.destination_directory.glob(f"**/{leaf_name}/**/*.bundle")
        )
        self.assertGreaterEqual(len(found_bundles), 1)

    def test_keep_temp_repo_and_update(self) -> None:
        """Tests --keep-temp-repo and incremental update."""
        bare_repo_directory = self.root_path / "upstream.git"
        self._run_git(
            ["clone", "--bare", str(self.repo_directory), str(bare_repo_directory)]
        )

        custom_temp = self.root_path / "custom_temp"
        custom_temp.mkdir()
        remote_url = f"file://{bare_repo_directory}"

        exit_code = main(
            [
                "-d",
                str(self.destination_directory),
                "--keep-temp-repo",
                "--temp-dir",
                str(custom_temp),
                remote_url,
            ]
        )
        self.assertEqual(exit_code, 0)

        # Temporary mirror should still exist
        cloned_mirrors = list(custom_temp.glob("**/*.git"))
        self.assertEqual(len(cloned_mirrors), 1)

        # Push a new commit to bare repo
        (self.repo_directory / "new_file.txt").write_text("new content")
        self._run_git(["add", "."], cwd=self.repo_directory)
        self._run_git(["commit", "-m", "Second commit"], cwd=self.repo_directory)
        self._run_git(
            ["push", str(bare_repo_directory), "master"],
            cwd=self.repo_directory,
        )

        # Archive again with --keep-temp-repo (should fetch deltas incrementally)
        exit_code_updated = main(
            [
                "-d",
                str(self.destination_directory),
                "--keep-temp-repo",
                "--temp-dir",
                str(custom_temp),
                remote_url,
            ]
        )
        self.assertEqual(exit_code_updated, 0)

    def test_dry_run_creates_no_files(self) -> None:
        """Tests that --dry-run produces output but creates no files or symlinks."""
        self._run_git(
            ["remote", "add", "origin", "https://github.com/dry-org/dry-repo.git"],
            cwd=self.repo_directory,
        )
        exit_code = main(
            [
                "-d",
                str(self.destination_directory),
                "-n",
                str(self.repo_directory),
            ]
        )
        self.assertEqual(exit_code, 0)
        created_files = list(self.destination_directory.glob("**/*"))
        self.assertEqual(len(created_files), 0)

    def test_dirty_repo_warning(self) -> None:
        """Tests that a dirty working tree generates a warning but still archives committed refs."""
        self._run_git(
            ["remote", "add", "origin", "https://github.com/dirty-org/dirty-repo.git"],
            cwd=self.repo_directory,
        )
        (self.repo_directory / "untracked.txt").write_text("untracked")

        clean = inspect_local_repository_cleanliness(self.repo_directory)
        self.assertFalse(clean)

        exit_code = main(
            ["-d", str(self.destination_directory), str(self.repo_directory)]
        )
        self.assertEqual(exit_code, 0)
        archive_directory = self.destination_directory / "dirty-org/dirty-repo"
        self.assertTrue((archive_directory.parent / "dirty-repo.bundle").is_symlink())

    def test_list_archives(self) -> None:
        """Tests that --list runs without error and discovers archives."""
        self._run_git(
            ["remote", "add", "origin", "https://github.com/my-org/core-lib.git"],
            cwd=self.repo_directory,
        )
        main(["-d", str(self.destination_directory), str(self.repo_directory)])

        exit_code = main(["-d", str(self.destination_directory), "--list"])
        self.assertEqual(exit_code, 0)

    def test_detached_head_and_special_refs(self) -> None:
        """Tests detached HEAD, nested branch names, and annotated tags."""
        self._run_git(
            ["remote", "add", "origin", "https://github.com/my-org/complex-repo.git"],
            cwd=self.repo_directory,
        )
        first_commit_hash = self._run_git(
            ["rev-parse", "HEAD"], cwd=self.repo_directory
        ).stdout.strip()

        # Branch with slashes
        self._run_git(
            ["checkout", "-b", "feature/deep/nested-branch"],
            cwd=self.repo_directory,
        )
        (self.repo_directory / "feature.txt").write_text("feature branch")
        self._run_git(["add", "."], cwd=self.repo_directory)
        self._run_git(["commit", "-m", "feature commit"], cwd=self.repo_directory)

        # Annotated tag
        self._run_git(
            ["tag", "-a", "v1.0.0-rc1", "-m", "Release candidate 1"],
            cwd=self.repo_directory,
        )

        # Detach HEAD
        self._run_git(["checkout", first_commit_hash], cwd=self.repo_directory)

        exit_code = main(
            ["-d", str(self.destination_directory), str(self.repo_directory)]
        )
        self.assertEqual(exit_code, 0)

        symlink = self.destination_directory / "my-org/complex-repo.bundle"
        self.assertTrue(symlink.is_symlink() and symlink.is_file())

        restored_directory = self.root_path / "restored_complex"
        self._run_git(["clone", str(symlink), str(restored_directory)])
        tags = self._run_git(["tag", "-l"], cwd=restored_directory).stdout.strip()
        self.assertIn("v1.0.0-rc1", tags)

    def test_empty_repo_without_commits(self) -> None:
        """Tests that a repo without commits fails gracefully without crash."""
        empty_repo = self.root_path / "empty_repo"
        empty_repo.mkdir()
        self._run_git(["init", str(empty_repo)])
        self._run_git(
            ["remote", "add", "origin", "https://github.com/my-org/empty-repo.git"],
            cwd=empty_repo,
        )

        exit_code = main(["-d", str(self.destination_directory), str(empty_repo)])
        self.assertEqual(exit_code, 1)

    def test_partial_batch_failures(self) -> None:
        """Tests that batch execution continues when one repository fails."""
        second_repo = self.root_path / "second_repo"
        second_repo.mkdir()
        self._run_git(["init", str(second_repo)])
        self._run_git(["config", "user.email", "test@example.com"], cwd=second_repo)
        self._run_git(["config", "user.name", "Tester"], cwd=second_repo)
        self._run_git(["config", "commit.gpgsign", "false"], cwd=second_repo)
        self._run_git(
            ["remote", "add", "origin", "https://github.com/my-org/second-repo.git"],
            cwd=second_repo,
        )
        (second_repo / "file.txt").write_text("content")
        self._run_git(["add", "."], cwd=second_repo)
        self._run_git(["commit", "-m", "init"], cwd=second_repo)

        missing_repo = self.root_path / "non_existent_repo"

        exit_code = main(
            [
                "-d",
                str(self.destination_directory),
                str(self.repo_directory),
                str(missing_repo),
                str(second_repo),
            ]
        )
        self.assertEqual(exit_code, 1)
        self.assertTrue(
            (self.destination_directory / "my-org/second-repo.bundle").is_symlink()
        )

    def test_corrupted_bundle_detection(self) -> None:
        """Tests that bundle verification rejects corrupted files."""
        corrupt_bundle = self.root_path / "corrupt.bundle"
        corrupt_bundle.write_bytes(b"not a valid git bundle header\n")

        with self.assertRaises(subprocess.CalledProcessError):
            verify_bundle_integrity(
                corrupt_bundle, working_directory=self.repo_directory
            )

    def test_fail_fast_on_unavailable_destination(self) -> None:
        """Tests fail-fast when destination cannot be reached or created."""
        # 1. Missing parent hierarchy (parents=False violation)
        missing_parent = self.root_path / "nonexistent_parent" / "archives"
        self.assertEqual(main(["-d", str(missing_parent), str(self.repo_directory)]), 1)

        # 2. Existing regular file instead of directory
        file_dest = self.root_path / "existing_file.txt"
        file_dest.write_text("regular file")
        self.assertEqual(main(["-d", str(file_dest), str(self.repo_directory)]), 1)

        # 3. Read-only non-writable directory
        readonly_dest = self.root_path / "readonly_dest"
        readonly_dest.mkdir()
        os.chmod(readonly_dest, 0o555)
        try:
            self.assertEqual(
                main(["-d", str(readonly_dest), str(self.repo_directory)]), 1
            )
        finally:
            os.chmod(readonly_dest, 0o755)


if __name__ == "__main__":
    unittest.main()

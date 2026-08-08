import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.agy import (
    ReleaseManifest,
    calculate_file_sha512,
    detect_host_platform,
    download_and_verify_package,
    download_file,
    extract_binary,
    fetch_release_manifest,
    get_installed_version,
    main,
    verify_path_env,
)


class TestAgyInstaller(unittest.TestCase):
    """Unit test suite for the agy installer script."""

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    @patch("pathlib.Path.glob", return_value=[])
    def test_detect_host_platform_linux_amd64(
        self, mock_glob: MagicMock, mock_machine: MagicMock, mock_system: MagicMock
    ) -> None:
        """Verifies Linux x86_64 glibc platform detection."""
        platform_id = detect_host_platform()
        self.assertEqual(platform_id, "linux_amd64")

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="aarch64")
    @patch(
        "pathlib.Path.glob",
        side_effect=lambda pattern: (
            [Path("/lib/ld-musl-aarch64.so.1")] if "musl" in pattern else []
        ),
    )
    def test_detect_host_platform_linux_arm64_musl(
        self, mock_glob: MagicMock, mock_machine: MagicMock, mock_system: MagicMock
    ) -> None:
        """Verifies Linux arm64 musl platform detection."""
        platform_id = detect_host_platform()
        self.assertEqual(platform_id, "linux_arm64_musl")

    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    def test_detect_host_platform_darwin_arm64(
        self, mock_machine: MagicMock, mock_system: MagicMock
    ) -> None:
        """Verifies macOS arm64 platform detection."""
        platform_id = detect_host_platform()
        self.assertEqual(platform_id, "darwin_arm64")

    @patch("platform.system", return_value="Windows")
    @patch("platform.machine", return_value="AMD64")
    def test_detect_host_platform_unsupported(
        self, mock_machine: MagicMock, mock_system: MagicMock
    ) -> None:
        """Verifies failure on unsupported platforms."""
        with self.assertRaises(RuntimeError):
            detect_host_platform()

    @patch("urllib.request.urlopen")
    def test_fetch_release_manifest_success(self, mock_urlopen: MagicMock) -> None:
        """Verifies fetching and parsing a valid manifest."""
        sample_sha512 = "a" * 128
        payload = {
            "version": "1.2.3",
            "url": "https://example.com/agy.tar.gz",
            "sha512": sample_sha512,
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        manifest = fetch_release_manifest(
            "https://example.com/manifests", "linux_amd64"
        )
        self.assertEqual(
            manifest,
            ReleaseManifest(
                version="1.2.3",
                download_url="https://example.com/agy.tar.gz",
                sha512=sample_sha512,
            ),
        )

    @patch("urllib.request.urlopen")
    def test_fetch_release_manifest_invalid_url_scheme(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Verifies manifest parsing rejects non-HTTPS URLs."""
        payload = {
            "version": "1.2.3",
            "url": "http://insecure-example.com/agy.tar.gz",
            "sha512": "a" * 128,
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with self.assertRaises(RuntimeError):
            fetch_release_manifest("https://example.com/manifests", "linux_amd64")

    def test_calculate_file_sha512(self) -> None:
        """Verifies accurate SHA-512 calculation for file contents."""
        content = b"Hello, Antigravity CLI!"
        expected_hash = hashlib.sha512(content).hexdigest().lower()

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        try:
            computed_hash = calculate_file_sha512(temp_path)
            self.assertEqual(computed_hash, expected_hash)
        finally:
            temp_path.unlink(missing_ok=True)

    @patch("pathlib.Path.is_file", return_value=True)
    @patch("os.access", return_value=True)
    @patch("subprocess.run")
    def test_get_installed_version_regex_match(
        self, mock_run: MagicMock, mock_access: MagicMock, mock_is_file: MagicMock
    ) -> None:
        """Verifies version extraction from metadata-rich stdout."""
        mock_proc = MagicMock()
        mock_proc.stdout = "antigravity v1.2.3 (commit 8a9f2b, built 2026-08-08)\n"
        mock_run.return_value = mock_proc

        version = get_installed_version(Path("/tmp/agy"))
        self.assertEqual(version, "1.2.3")

    def test_extract_binary_from_nested_tarfile(self) -> None:
        """Verifies extraction of binary nested inside a tarball subfolder."""
        binary_content = b"#!/bin/sh\necho 1.2.3"
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "payload.tar.gz"
            dest_binary = Path(temp_dir) / "bin" / "agy"

            with tarfile.open(archive_path, "w:gz") as tar:
                tarinfo = tarfile.TarInfo(name="agy-v1.2.3/antigravity")
                tarinfo.size = len(binary_content)
                tar.addfile(tarinfo, io.BytesIO(binary_content))

            extract_binary(archive_path, dest_binary)

            self.assertTrue(dest_binary.is_file())
            self.assertEqual(dest_binary.read_bytes(), binary_content)
            self.assertTrue(os.access(dest_binary, os.X_OK))

    def test_extract_binary_direct_file(self) -> None:
        """Verifies direct copy of non-tar executable file."""
        binary_content = b"#!/bin/sh\necho direct"
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "source_exec"
            dest_binary = Path(temp_dir) / "bin" / "agy"
            source_file.write_bytes(binary_content)

            extract_binary(source_file, dest_binary)

            self.assertTrue(dest_binary.is_file())
            self.assertEqual(dest_binary.read_bytes(), binary_content)
            self.assertTrue(os.access(dest_binary, os.X_OK))

    @patch("urllib.request.urlopen")
    def test_download_file_success(self, mock_urlopen: MagicMock) -> None:
        """Verifies download_file writes streamed content to destination."""
        content = b"streamed bytes"
        mock_response = MagicMock()
        mock_response.read.side_effect = [content, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            dest = Path(temp_dir) / "downloaded"
            download_file("https://example.com/file", dest)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_bytes(), content)

    @patch("scripts.agy.download_file")
    @patch("scripts.agy.calculate_file_sha512", return_value="bad_hash")
    def test_download_and_verify_package_mismatch_cleans_file(
        self, mock_calc_hash: MagicMock, mock_download: MagicMock
    ) -> None:
        """Verifies download_and_verify_package deletes destination on checksum mismatch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "corrupt.pkg"
            target_path.write_bytes(b"bad content")

            with self.assertRaises(RuntimeError):
                download_and_verify_package(
                    "https://example.com/pkg", target_path, "expected_hash"
                )

            self.assertFalse(target_path.exists())

    @patch("scripts.agy.detect_host_platform", return_value="linux_amd64")
    @patch("scripts.agy.fetch_release_manifest")
    @patch("scripts.agy.get_installed_version", return_value="1.2.3")
    @patch("builtins.print")
    def test_main_check_up_to_date(
        self,
        mock_print: MagicMock,
        mock_get_version: MagicMock,
        mock_fetch_manifest: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Verifies main --check flow when binary is up to date."""
        mock_fetch_manifest.return_value = ReleaseManifest(
            version="1.2.3",
            download_url="https://example.com/agy.tar.gz",
            sha512="a" * 128,
        )

        main(["--check"])
        mock_print.assert_called_with("Up-to-date! Current installed version is 1.2.3.")

    @patch("builtins.print")
    def test_verify_path_env_not_in_path(self, mock_print: MagicMock) -> None:
        """Verifies warning when directory is not present in PATH environment variable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir) / "custom_bin"
            test_path.mkdir()
            with patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
                verify_path_env(test_path)
                mock_print.assert_called()

    @patch("scripts.agy.detect_host_platform", return_value="linux_amd64")
    @patch("scripts.agy.fetch_release_manifest")
    @patch("scripts.agy.download_and_verify_package")
    @patch("builtins.print")
    def test_main_download_only(
        self,
        mock_print: MagicMock,
        mock_dl_verify: MagicMock,
        mock_fetch_manifest: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Verifies main --download flow saves package to target directory using release filename."""
        sample_sha512 = "a" * 128
        mock_fetch_manifest.return_value = ReleaseManifest(
            version="1.2.3",
            download_url="https://example.com/agy-1.2.3-linux_amd64.tar.gz",
            sha512=sample_sha512,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            expected_file = (target_dir / "agy-1.2.3-linux_amd64.tar.gz").resolve()
            main(["--download", str(target_dir)])

            mock_dl_verify.assert_called_once_with(
                "https://example.com/agy-1.2.3-linux_amd64.tar.gz",
                expected_file,
                sample_sha512,
            )
            mock_print.assert_called_with(
                f"Successfully downloaded and verified package at {expected_file}",
                file=sys.stderr,
            )

    @patch("scripts.agy.detect_host_platform", return_value="linux_amd64")
    @patch("scripts.agy.fetch_release_manifest")
    @patch("scripts.agy.download_and_verify_package")
    @patch("builtins.print")
    def test_main_download_aliases(
        self,
        mock_print: MagicMock,
        mock_dl_verify: MagicMock,
        mock_fetch_manifest: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Verifies --output-dir and --download-only aliases work identically to --download."""
        sample_sha512 = "a" * 128
        mock_fetch_manifest.return_value = ReleaseManifest(
            version="1.2.3",
            download_url="https://example.com/agy-1.2.3-linux_amd64.tar.gz",
            sha512=sample_sha512,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            expected_file = (target_dir / "agy-1.2.3-linux_amd64.tar.gz").resolve()

            main(["--output-dir", str(target_dir)])
            mock_dl_verify.assert_called_with(
                "https://example.com/agy-1.2.3-linux_amd64.tar.gz",
                expected_file,
                sample_sha512,
            )

            main(["--download-only", str(target_dir)])
            mock_dl_verify.assert_called_with(
                "https://example.com/agy-1.2.3-linux_amd64.tar.gz",
                expected_file,
                sample_sha512,
            )

    @patch("scripts.agy.detect_host_platform", return_value="linux_amd64")
    @patch("scripts.agy.fetch_release_manifest")
    @patch("scripts.agy.download_and_verify_package")
    @patch("builtins.print")
    def test_main_download_no_arg_infers_filename(
        self,
        mock_print: MagicMock,
        mock_dl_verify: MagicMock,
        mock_fetch_manifest: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Verifies --download without argument auto-infers current directory and release filename."""
        sample_sha512 = "a" * 128
        mock_fetch_manifest.return_value = ReleaseManifest(
            version="1.2.3",
            download_url="https://example.com/releases/agy-1.2.3-linux_amd64.tar.gz",
            sha512=sample_sha512,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                main(["--download"])
                expected_path = (
                    Path(temp_dir) / "agy-1.2.3-linux_amd64.tar.gz"
                ).resolve()
                mock_dl_verify.assert_called_once_with(
                    "https://example.com/releases/agy-1.2.3-linux_amd64.tar.gz",
                    expected_path,
                    sample_sha512,
                )
            finally:
                os.chdir(old_cwd)

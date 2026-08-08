#!/usr/bin/env python3
"""Fetch, verify, and install CLI binary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DEFAULT_MANIFEST_BASE_URL: Final[str] = (
    "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests"
)
TARGET_BINARY: Final[str] = "agy"
ARCHIVE_BINARY: Final[str] = "antigravity"
HTTP_USER_AGENT: Final[str] = os.environ.get("AGY_USER_AGENT", "CLI-Installer/1.0")
READ_BUFFER_SIZE: Final[int] = 65536


def get_default_install_dir() -> Path:
    """Return default binary installation directory."""
    return Path.home() / ".local" / "bin"


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    download_url: str
    sha512: str


def detect_host_platform() -> str:
    """Detect operating system, architecture, and libc type for platform identifier."""
    sys_name = platform.system().lower()
    machine = platform.machine().lower()

    if sys_name == "linux":
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        else:
            raise RuntimeError(
                f"Unsupported Linux architecture '{machine}'. Only x86_64 and arm64 are supported."
            )

        is_musl = (
            any(Path("/lib").glob("*musl*"))
            or any(Path("/usr/lib").glob("*musl*"))
            or any(Path("/lib64").glob("*musl*"))
        )
        return f"linux_{arch}_musl" if is_musl else f"linux_{arch}"

    if sys_name == "darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
        return f"darwin_{arch}"

    raise RuntimeError(f"Unsupported operating system '{sys_name}'.")


def fetch_release_manifest(
    manifest_base_url: str,
    platform_id: str,
    timeout_seconds: int = 30,
) -> ReleaseManifest:
    """Fetch and parse release manifest for host platform."""
    url = f"{manifest_base_url}/{platform_id}.json"
    request = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as err:
        raise RuntimeError(
            f"Failed to fetch release manifest from '{url}': {err}"
        ) from err
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Invalid manifest JSON from '{url}': {err}") from err

    version = payload.get("version")
    download_url = payload.get("url")
    sha512 = payload.get("sha512")

    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("Release manifest missing valid 'version' field.")
    if not isinstance(download_url, str) or not download_url.startswith("https://"):
        raise RuntimeError("Release manifest missing valid HTTPS 'url' field.")
    if not isinstance(sha512, str) or len(sha512.strip()) != 128:
        raise RuntimeError(
            "Release manifest missing valid 128-character SHA-512 checksum."
        )

    return ReleaseManifest(
        version=version.strip(),
        download_url=download_url.strip(),
        sha512=sha512.strip().lower(),
    )


def calculate_file_sha512(file_path: Path) -> str:
    """Compute SHA-512 checksum of a file."""
    hasher = hashlib.sha512()
    with file_path.open("rb") as stream:
        if hasattr(hashlib, "file_digest"):
            return hashlib.file_digest(stream, "sha512").hexdigest().lower()
        for chunk in iter(lambda: stream.read(READ_BUFFER_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def download_file(url: str, destination: Path, timeout_seconds: int = 30) -> None:
    """Download network resource to destination file path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})

    try:
        with (
            urllib.request.urlopen(request, timeout=timeout_seconds) as response,
            destination.open("wb") as out_file,
        ):
            shutil.copyfileobj(response, out_file)
    except urllib.error.URLError as err:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed for '{url}': {err}") from err


def download_and_verify_package(
    download_url: str,
    destination: Path,
    expected_sha512: str,
    timeout_seconds: int = 30,
) -> None:
    """Download file and verify its checksum, removing destination on failure."""
    download_file(download_url, destination, timeout_seconds=timeout_seconds)
    computed_sha512 = calculate_file_sha512(destination)
    if computed_sha512 != expected_sha512:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise RuntimeError(
            f"Checksum mismatch!\n  Expected:   {expected_sha512}\n  Calculated: {computed_sha512}"
        )


def extract_binary(package_path: Path, destination_binary: Path) -> None:
    """Extract binary from tar.gz or copy direct executable atomically."""
    destination_binary.parent.mkdir(parents=True, exist_ok=True)
    temp_target = destination_binary.with_name(
        f".{destination_binary.name}.tmp.{os.getpid()}"
    )

    try:
        if tarfile.is_tarfile(package_path):
            with tarfile.open(package_path, "r:*") as archive:
                member_file = None
                for member in archive.getmembers():
                    if Path(member.name).name == ARCHIVE_BINARY and member.isreg():
                        member_file = archive.extractfile(member)
                        break
                if member_file is None:
                    raise RuntimeError(
                        f"Archive '{package_path}' does not contain regular file binary '{ARCHIVE_BINARY}'."
                    )
                with temp_target.open("wb") as out_file:
                    shutil.copyfileobj(member_file, out_file)
        else:
            shutil.copyfile(package_path, temp_target)

        temp_target.chmod(0o755)
        temp_target.replace(destination_binary)
    finally:
        if temp_target.exists():
            temp_target.unlink(missing_ok=True)


def get_installed_version(target_binary: Path) -> str | None:
    """Retrieve installed binary version string, or None if missing or unexecutable."""
    binary_path = target_binary.expanduser().resolve()
    if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
        return None

    try:
        proc = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        output = (proc.stdout or proc.stderr).strip()
        match = re.search(r"v?(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.]+)?)", output)
        if match:
            return match.group(1)
    except (subprocess.SubprocessError, OSError):
        pass

    return None


def verify_path_env(install_dir: Path) -> None:
    """Warn user if target directory is not present in PATH."""
    try:
        resolved = install_dir.expanduser().resolve()
        path_entries = [
            Path(entry).expanduser().resolve()
            for entry in os.environ.get("PATH", "").split(os.pathsep)
            if entry.strip()
        ]
        if resolved not in path_entries:
            print(
                f"Notice: '{resolved}' is not in your $PATH.\n"
                f"Add it to your shell configuration (e.g. ~/.bashrc or ~/.zshrc):\n"
                f'  export PATH="{resolved}:$PATH"',
                file=sys.stderr,
            )
    except OSError:
        pass


def handle_download_mode(manifest: ReleaseManifest, target_dir: Path | None) -> None:
    """Download release package to target directory using default upstream release filename."""
    dest_dir = (target_dir or Path(".")).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(manifest.download_url).name or f"agy-{manifest.version}.tar.gz"
    destination = dest_dir / filename

    print(
        f"Downloading version {manifest.version} package to {destination}...",
        file=sys.stderr,
    )
    download_and_verify_package(manifest.download_url, destination, manifest.sha512)
    print(
        f"Successfully downloaded and verified package at {destination}",
        file=sys.stderr,
    )


def handle_check_mode(manifest: ReleaseManifest, current_version: str | None) -> None:
    """Execute version checking workflow."""
    if current_version is None:
        print(f"Not installed. Latest version available: {manifest.version}")
    elif current_version == manifest.version:
        print(f"Up-to-date! Current installed version is {current_version}.")
    else:
        print(
            f"Update available: {current_version} -> {manifest.version}\n"
            f"Run without '--check' to upgrade."
        )


def handle_install_mode(
    manifest: ReleaseManifest,
    target_dir: Path,
    target_binary: Path,
    current_version: str | None,
    force: bool,
) -> None:
    """Execute binary download, verification, and installation workflow."""
    if current_version == manifest.version and not force:
        print(f"CLI binary is already up to date ({current_version}).")
        return

    print(f"Installing version {manifest.version} to {target_binary}...")
    with tempfile.TemporaryDirectory(prefix="agy_install_") as temp_dir:
        staged_pkg = Path(temp_dir) / "package"
        download_and_verify_package(manifest.download_url, staged_pkg, manifest.sha512)
        extract_binary(staged_pkg, target_binary)

    print(f"Successfully installed to {target_binary}")
    verify_path_env(target_dir)


def build_parser(default_dir: Path) -> argparse.ArgumentParser:
    """Construct command-line argument parser with strict operational modes."""
    parser = argparse.ArgumentParser(
        description="Download, verify, and install the CLI binary."
    )
    parser.add_argument(
        "-d",
        "--target-dir",
        type=Path,
        default=default_dir,
        help=f"Target directory for binary installation (default: {default_dir}).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force re-installation even if already up to date.",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-i",
        "--install",
        action="store_true",
        help="Fetch, verify, and install binary into target directory.",
    )
    mode_group.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="Check for updates without downloading or installing.",
    )
    mode_group.add_argument(
        "-o",
        "--output-dir",
        "--download",
        "--download-only",
        dest="download_dir",
        nargs="?",
        const=Path("."),
        type=Path,
        metavar="DIR",
        help="Download package without installing. Optionally specify destination directory (default: current directory).",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    env_manifest_url = os.environ.get(
        "AGY_MANIFEST_BASE_URL", DEFAULT_MANIFEST_BASE_URL
    )
    env_target_dir = os.environ.get("AGY_INSTALL_DIR")
    default_dir = Path(env_target_dir) if env_target_dir else get_default_install_dir()

    parser = build_parser(default_dir)

    raw_args = argv if argv is not None else sys.argv[1:]
    if not raw_args:
        parser.print_help()
        return

    args = parser.parse_args(argv)

    if args.download_dir and (args.force or args.target_dir != default_dir):
        parser.error(
            "--download/--output-dir cannot be combined with --target-dir or --force."
        )

    target_dir: Path = args.target_dir.expanduser().resolve()
    target_binary = target_dir / TARGET_BINARY

    try:
        platform_id = detect_host_platform()
        manifest = fetch_release_manifest(env_manifest_url, platform_id)

        if args.download_dir:
            handle_download_mode(manifest, args.download_dir)
        elif args.check:
            current_version = get_installed_version(target_binary)
            handle_check_mode(manifest, current_version)
        elif args.install or args.force or args.target_dir != default_dir:
            current_version = get_installed_version(target_binary)
            handle_install_mode(
                manifest, target_dir, target_binary, current_version, args.force
            )
        else:
            parser.print_help()

    except (RuntimeError, OSError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
A tool to mirror a directory structure while recursively extracting zip files.
This script walks a source directory and copies all files to a destination,
but if it encounters a zip file, it extracts its contents into a folder
instead of copying the zip file itself. It then recursively handles any
zip files found within the extracted content.
"""

import argparse
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a zip member attempts directory traversal or sibling folder bypass."""


class SizeLimitExceededError(ValueError):
    """Raised when cumulative extraction size exceeds configured max-size."""


def parse_size_to_bytes(size_str: str | int | None, default_bytes: int = 0) -> int:
    """Parses a human-readable size string into bytes.

    Args:
        size_str: The size string (e.g., '2MB', '500KB') or integer bytes.
        default_bytes: The fallback value if size_str is None.

    Returns:
        The size in bytes.

    Raises:
        ValueError: If the string format is invalid.
    """
    if size_str is None:
        return default_bytes
    if isinstance(size_str, int):
        return size_str
    if isinstance(size_str, str) and size_str.isdigit():
        return int(size_str)

    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMG]?B)$", size_str.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(
            f"Invalid size format: {size_str}. Use e.g., '2MB', '500KB', '1.5GB'."
        )

    val = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    return int(val * multipliers[unit])


class ZipSyncer:
    """
    Handles mirroring of directories with recursive zip extraction.
    """

    def __init__(
        self,
        verbose: bool = False,
        max_depth: int | None = None,
        max_size: str | int | None = None,
    ):
        self.verbose = verbose
        self.max_depth = max_depth
        self.max_size_bytes = (
            parse_size_to_bytes(max_size, 0) if max_size is not None else None
        )
        self.total_bytes = 0

    def _log(self, message: str):
        """Prints a message if verbose mode is enabled."""
        if self.verbose:
            print(message)

    def _add_size(self, size: int, source_info: str = ""):
        """Tracks cumulative extraction size and enforces maximum size limit."""
        if (
            self.max_size_bytes is not None
            and self.total_bytes + size > self.max_size_bytes
        ):
            msg = (
                f"Error: Exceeded cumulative extraction size limit "
                f"({self.total_bytes + size} > {self.max_size_bytes} bytes)"
            )
            if source_info:
                msg += f" while processing {source_info}"
            print(msg, file=sys.stderr)
            raise SizeLimitExceededError(msg)
        self.total_bytes += size

    @staticmethod
    def _sanitize_zip_path(target_dir: Path, relative_path: str) -> Path:
        """
        Prevents Zip Slip / Zip Bomb attacks by ensuring the extracted path
        is within the target directory.

        Args:
            target_dir: The directory where the zip is being extracted.
            relative_path: The path of the member within the zip.

        Returns:
            The resolved Path to the destination.

        Raises:
            PathTraversalError: If the path is outside the target directory.
        """
        destination = (target_dir / relative_path).resolve()
        target_dir_resolved = target_dir.resolve()

        if not destination.is_relative_to(target_dir_resolved):
            raise PathTraversalError(
                f"Malicious path detected in zip file: {relative_path}"
            )

        return destination

    def _safe_extract(self, zip_file: Path, extract_dir: Path):
        """
        Safely extracts a zip file to a directory, checking for malicious paths.

        Args:
            zip_file: Path to the zip file.
            extract_dir: Path to the directory for extraction.
        """
        with zipfile.ZipFile(zip_file, "r") as zf:
            for member in zf.infolist():
                try:
                    # Security check for paths
                    self._sanitize_zip_path(extract_dir, member.filename)
                    if not member.is_dir():
                        self._add_size(
                            member.file_size,
                            source_info=f"{member.filename} in {zip_file}",
                        )
                    zf.extract(member, extract_dir)
                except PathTraversalError as e:
                    print(
                        f"Skipping malicious entry {member.filename} in {zip_file}: {e}"
                    )

    def recursive_explode_zips(self, directory: Path, current_depth: int = 1):
        """
        Recursively walks a directory and extracts any zip files found.
        The original zip file is deleted after successful extraction.

        Args:
            directory: The directory to process.
            current_depth: Current depth of nested extraction.
        """
        zip_files = []
        for root, _, files in os.walk(directory):
            root_path = Path(root)
            for file in files:
                file_path = root_path / file
                if zipfile.is_zipfile(file_path):
                    zip_files.append(file_path)

        for file_path in zip_files:
            if not file_path.exists():
                continue

            if self.max_depth is not None and current_depth > self.max_depth:
                msg = (
                    f"Warning: Skipping {file_path}: "
                    f"exceeds maximum nested extraction depth ({current_depth} > {self.max_depth})"
                )
                print(msg, file=sys.stderr)
                self._log(msg)
                continue

            extract_dir = file_path.parent / file_path.stem
            self._log(f"  Nested extraction: {file_path} -> {extract_dir}")

            try:
                extract_dir.mkdir(parents=True, exist_ok=True)
                self._safe_extract(file_path, extract_dir)

                # Remove the nested zip file
                file_path.unlink()

                # Recursively process newly extracted directory for further nested zips
                self.recursive_explode_zips(
                    extract_dir, current_depth=current_depth + 1
                )
            except (zipfile.BadZipFile, OSError) as e:
                print(
                    f"Error processing nested zip {file_path}: {e}",
                    file=sys.stderr,
                )

    def sync(self, src_root: Path, dest_root: Path):
        """
        Walks the source directory and mirrors it to the destination directory.
        Copies normal files and extracts zip files.

        Args:
            src_root: The source directory.
            dest_root: The destination directory.
        """
        if not src_root.exists():
            print(
                f"Error: Source directory {src_root} does not exist.", file=sys.stderr
            )
            return

        self.total_bytes = 0

        # Create destination if it doesn't exist
        dest_root.mkdir(parents=True, exist_ok=True)

        for root, dirs, files in os.walk(src_root):
            root_path = Path(root)
            rel_path = root_path.relative_to(src_root)
            current_dest_dir = dest_root / rel_path

            # Ensure directory structure exists in destination
            current_dest_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                src_file = root_path / file

                if zipfile.is_zipfile(src_file):
                    # For Zip files: Extract instead of Copy
                    target_folder_name = src_file.stem
                    target_extract_path = current_dest_dir / target_folder_name

                    print(f"Extracting: {src_file} -> {target_extract_path}")

                    try:
                        target_extract_path.mkdir(parents=True, exist_ok=True)
                        self._safe_extract(src_file, target_extract_path)

                        # Post-process the extracted folder to handle nested zips
                        self.recursive_explode_zips(
                            target_extract_path, current_depth=1
                        )
                    except (zipfile.BadZipFile, OSError) as e:
                        print(f"Failed to extract {src_file}: {e}", file=sys.stderr)
                else:
                    # For Regular files: Copy
                    dest_file = current_dest_dir / file
                    self._log(f"Copying: {src_file} -> {dest_file}")
                    try:
                        file_size = src_file.stat().st_size
                        self._add_size(file_size, source_info=str(src_file))
                        shutil.copy2(src_file, dest_file)
                    except OSError as e:
                        print(f"Failed to copy {src_file}: {e}", file=sys.stderr)


def main():
    """Main entry point for the zipsync tool."""
    parser = argparse.ArgumentParser(
        description="Mirror a directory while recursively extracting zip files."
    )
    parser.add_argument("source", help="Source directory to mirror")
    parser.add_argument("destination", help="Destination directory")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum nested archive extraction depth limit",
    )
    parser.add_argument(
        "--max-size",
        type=str,
        default=None,
        help="Maximum total cumulative extraction size (e.g., '50MB', '500KB')",
    )

    args = parser.parse_args()

    source_dir = Path(args.source)
    destination_dir = Path(args.destination)

    try:
        syncer = ZipSyncer(
            verbose=args.verbose, max_depth=args.max_depth, max_size=args.max_size
        )

        print(f"Starting sync from {source_dir} to {destination_dir}...")
        syncer.sync(source_dir, destination_dir)
        print("Sync complete.")
    except (ValueError, SizeLimitExceededError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

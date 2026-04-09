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
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Optional


class ZipSyncer:
    """
    Handles mirroring of directories with recursive zip extraction.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _log(self, message: str):
        """Prints a message if verbose mode is enabled."""
        if self.verbose:
            print(message)

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
            ValueError: If the path is outside the target directory.
        """
        destination = (target_dir / relative_path).resolve()
        target_dir_resolved = target_dir.resolve()

        if not str(destination).startswith(str(target_dir_resolved)):
            raise ValueError(f"Malicious path detected in zip file: {relative_path}")

        return destination

    def _safe_extract(self, zip_file: Path, extract_dir: Path):
        """
        Safely extracts a zip file to a directory, checking for malicious paths.

        Args:
            zip_file: Path to the zip file.
            extract_dir: Path to the directory for extraction.
        """
        with zipfile.ZipFile(zip_file, 'r') as zf:
            for member in zf.namelist():
                try:
                    # Security check for paths
                    self._sanitize_zip_path(extract_dir, member)
                    zf.extract(member, extract_dir)
                except ValueError as e:
                    print(f"Skipping malicious entry {member} in {zip_file}: {e}")

    def recursive_explode_zips(self, directory: Path):
        """
        Recursively walks a directory and extracts any zip files found.
        The original zip file is deleted after successful extraction.

        Args:
            directory: The directory to process.
        """
        # topdown=True allows us to modify 'dirs' to visit newly created folders
        for root, dirs, files in os.walk(directory, topdown=True):
            root_path = Path(root)

            for file in files:
                file_path = root_path / file

                if zipfile.is_zipfile(file_path):
                    # Define new directory name (remove .zip extension)
                    extract_dir = root_path / file_path.stem
                    self._log(f"  Nested extraction: {file_path} -> {extract_dir}")

                    try:
                        extract_dir.mkdir(parents=True, exist_ok=True)
                        self._safe_extract(file_path, extract_dir)
                        
                        # Remove the nested zip file
                        file_path.unlink()

                        # Add the new directory to dirs so os.walk visits it
                        dirs.append(extract_dir.name)
                    except Exception as e:
                        print(f"Error processing nested zip {file_path}: {e}")

    def sync(self, src_root: Path, dest_root: Path):
        """
        Walks the source directory and mirrors it to the destination directory.
        Copies normal files and extracts zip files.

        Args:
            src_root: The source directory.
            dest_root: The destination directory.
        """
        if not src_root.exists():
            print(f"Error: Source directory {src_root} does not exist.", file=sys.stderr)
            return

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
                        self.recursive_explode_zips(target_extract_path)
                    except Exception as e:
                        print(f"Failed to extract {src_file}: {e}")
                else:
                    # For Regular files: Copy
                    dest_file = current_dest_dir / file
                    self._log(f"Copying: {src_file} -> {dest_file}")
                    try:
                        shutil.copy2(src_file, dest_file)
                    except Exception as e:
                        print(f"Failed to copy {src_file}: {e}")


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

    args = parser.parse_args()

    source_dir = Path(args.source)
    destination_dir = Path(args.destination)

    syncer = ZipSyncer(verbose=args.verbose)
    
    print(f"Starting sync from {source_dir} to {destination_dir}...")
    syncer.sync(source_dir, destination_dir)
    print("Sync complete.")


if __name__ == "__main__":
    main()

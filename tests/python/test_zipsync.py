import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.zipsync import (
    SizeLimitExceededError,
    ZipSyncer,
    parse_size_to_bytes,
)


class TestZipSync(unittest.TestCase):
    def test_parse_size_to_bytes(self):
        self.assertEqual(parse_size_to_bytes("500KB"), 512000)
        self.assertEqual(parse_size_to_bytes("10MB"), 10485760)
        self.assertEqual(parse_size_to_bytes("2GB"), 2147483648)
        self.assertEqual(parse_size_to_bytes("100B"), 100)
        self.assertEqual(parse_size_to_bytes("1.5GB"), int(1.5 * 1024**3))
        self.assertEqual(parse_size_to_bytes(1024), 1024)
        self.assertEqual(parse_size_to_bytes("1024"), 1024)
        self.assertEqual(parse_size_to_bytes(None, default_bytes=50), 50)

        with self.assertRaises(ValueError):
            parse_size_to_bytes("invalid_size")

    def test_sibling_directory_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_dir = tmp_path / "src"
            dest_dir = tmp_path / "target"
            sibling_dir = tmp_path / "target_sibling"

            src_dir.mkdir()
            dest_dir.mkdir()
            sibling_dir.mkdir()

            # Create a zip containing a sibling directory traversal entry
            zip_path = src_dir / "test.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("safe.txt", "safe content")
                # Attempt to write to sibling directory target_sibling
                zf.writestr("../target_sibling/evil.txt", "evil content")

            syncer = ZipSyncer(verbose=True)

            stderr_io = io.StringIO()
            with patch("sys.stderr", stderr_io):
                syncer.sync(src_dir, dest_dir)

            # Check safe file extracted
            safe_extracted = dest_dir / "test" / "safe.txt"
            self.assertTrue(safe_extracted.exists())
            self.assertEqual(safe_extracted.read_text(), "safe content")

            # Check evil file NOT written in sibling directory
            evil_sibling = sibling_dir / "evil.txt"
            self.assertFalse(evil_sibling.exists())

    def test_max_depth_enforcement(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_dir = tmp_path / "src"
            dest_dir = tmp_path / "dest"
            src_dir.mkdir()

            # Create level2 zip: contains file.txt
            level2_io = io.BytesIO()
            with zipfile.ZipFile(level2_io, "w") as z2:
                z2.writestr("deep.txt", "deep content")
            level2_data = level2_io.getvalue()

            # Create level1 zip: contains level2.zip
            level1_io = io.BytesIO()
            with zipfile.ZipFile(level1_io, "w") as z1:
                z1.writestr("level2.zip", level2_data)
                z1.writestr("level1_safe.txt", "level1 content")
            level1_data = level1_io.getvalue()

            # Create top zip: contains level1.zip
            top_zip = src_dir / "top.zip"
            with zipfile.ZipFile(top_zip, "w") as z0:
                z0.writestr("level1.zip", level1_data)
                z0.writestr("top_safe.txt", "top content")

            # Sync with max_depth=1
            # top.zip is depth 0. level1.zip extracted at depth 1. level2.zip inside level1 is depth 2 (skips level2.zip)
            syncer = ZipSyncer(max_depth=1)

            stderr_io = io.StringIO()
            with patch("sys.stderr", stderr_io):
                syncer.sync(src_dir, dest_dir)

            # top.zip extracted to dest/top/
            top_extracted = dest_dir / "top"
            self.assertTrue((top_extracted / "top_safe.txt").exists())

            # level1.zip extracted to dest/top/level1/
            level1_extracted = top_extracted / "level1"
            self.assertTrue((level1_extracted / "level1_safe.txt").exists())

            # level2.zip inside level1 was depth 2 > max_depth 1, so level2.zip should be skipped and NOT extracted to level1/level2/
            level2_extracted_folder = level1_extracted / "level2"
            self.assertFalse((level2_extracted_folder / "deep.txt").exists())
            # level2.zip file should still exist unextracted
            self.assertTrue((level1_extracted / "level2.zip").exists())

            # Warning should be logged to stderr
            self.assertIn(
                "exceeds maximum nested extraction depth", stderr_io.getvalue()
            )

    def test_max_size_exceeded_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src_dir = tmp_path / "src"
            dest_dir = tmp_path / "dest"
            src_dir.mkdir()

            # Create a 2KB file in source
            large_file = src_dir / "large.bin"
            large_file.write_bytes(b"A" * 2048)

            syncer = ZipSyncer(max_size="1KB")

            stderr_io = io.StringIO()
            with (
                patch("sys.stderr", stderr_io),
                self.assertRaises(SizeLimitExceededError),
            ):
                syncer.sync(src_dir, dest_dir)

            self.assertIn(
                "Exceeded cumulative extraction size limit", stderr_io.getvalue()
            )


if __name__ == "__main__":
    unittest.main()

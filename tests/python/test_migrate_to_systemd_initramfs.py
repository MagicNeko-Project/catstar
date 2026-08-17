"""Unit tests for Arch Linux systemd-based initramfs migration script."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_to_systemd_initramfs import (
    AtomicTransactionManager,
    BootloaderMigrator,
    HookMigrator,
    SignalManager,
    SystemDiagnostics,
)


class TestHookMigrator(unittest.TestCase):
    """Test hook parsing and translation logic."""

    def test_parse_hooks_standard(self) -> None:
        conf = """
# mkinitcpio.conf
HOOKS=(base udev autodetect modconf kms keyboard keymap consolefont block encrypt lvm2 filesystems fsck)
"""
        hooks = HookMigrator.parse_hooks(conf)
        expected = [
            "base",
            "udev",
            "autodetect",
            "modconf",
            "kms",
            "keyboard",
            "keymap",
            "consolefont",
            "block",
            "encrypt",
            "lvm2",
            "filesystems",
            "fsck",
        ]
        self.assertEqual(hooks, expected)

    def test_parse_hooks_missing_raises_value_error(self) -> None:
        conf = "# No hooks line here"
        with self.assertRaises(ValueError):
            HookMigrator.parse_hooks(conf)

    def test_translate_hooks_standard_ext4(self) -> None:
        old_hooks = [
            "base",
            "udev",
            "autodetect",
            "modconf",
            "kms",
            "keyboard",
            "keymap",
            "consolefont",
            "block",
            "encrypt",
            "filesystems",
            "fsck",
            "shutdown",
        ]
        plan = HookMigrator.translate_hooks(old_hooks, root_fstype="ext4")

        self.assertIn("systemd", plan.proposed_hooks)
        self.assertNotIn("base", plan.proposed_hooks)
        self.assertNotIn("udev", plan.proposed_hooks)
        self.assertIn("sd-vconsole", plan.proposed_hooks)
        self.assertNotIn("keymap", plan.proposed_hooks)
        self.assertNotIn("consolefont", plan.proposed_hooks)
        self.assertIn("sd-encrypt", plan.proposed_hooks)
        self.assertNotIn("encrypt", plan.proposed_hooks)
        self.assertIn("sd-shutdown", plan.proposed_hooks)
        self.assertNotIn("shutdown", plan.proposed_hooks)
        self.assertIn("fsck", plan.proposed_hooks)

    def test_translate_hooks_btrfs_omits_fsck(self) -> None:
        old_hooks = ["base", "udev", "autodetect", "btrfs", "filesystems", "fsck"]
        plan = HookMigrator.translate_hooks(old_hooks, root_fstype="btrfs")

        self.assertNotIn("fsck", plan.proposed_hooks)
        self.assertTrue(
            any(a.action == "DROPPED" and a.original == "fsck" for a in plan.actions)
        )

    def test_translate_hooks_custom_hook_retained(self) -> None:
        old_hooks = ["base", "udev", "my_custom_hook", "filesystems"]
        plan = HookMigrator.translate_hooks(old_hooks, root_fstype="ext4")

        self.assertIn("my_custom_hook", plan.proposed_hooks)


class TestBootloaderMigrator(unittest.TestCase):
    """Test bootloader parameter audit and rw -> ro transformation."""

    def test_audit_config_systemd_boot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = Path(tmpdir) / "loader/entries/arch.conf"
            conf_path.parent.mkdir(parents=True, exist_ok=True)
            conf_path.write_text("title Arch Linux\noptions root=UUID=123 rw quiet\n")

            target = BootloaderMigrator.audit_config(conf_path)
            self.assertTrue(target.needs_update)
            self.assertIn("ro quiet", target.proposed_content)
            self.assertNotIn("rw", target.proposed_content)

    def test_audit_config_grub(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            grub_path = Path(tmpdir) / "grub"
            grub_path.write_text('GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 rw quiet"\n')

            target = BootloaderMigrator.audit_config(grub_path)
            self.assertTrue(target.needs_update)
            self.assertIn("loglevel=3 ro quiet", target.proposed_content)

    def test_audit_config_already_ro(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            conf_path = Path(tmpdir) / "loader/entries/arch.conf"
            conf_path.parent.mkdir(parents=True, exist_ok=True)
            conf_path.write_text("title Arch Linux\noptions root=UUID=123 ro quiet\n")

            target = BootloaderMigrator.audit_config(conf_path)
            self.assertFalse(target.needs_update)
            self.assertEqual(target.original_content, target.proposed_content)


class TestSystemDiagnostics(unittest.TestCase):
    """Test kernel version inferencing."""

    def test_infer_pkgbase(self) -> None:
        self.assertEqual(SystemDiagnostics._infer_pkgbase("6.6.1-arch1-1"), "linux")
        self.assertEqual(SystemDiagnostics._infer_pkgbase("6.6.1-lts"), "linux-lts")
        self.assertEqual(SystemDiagnostics._infer_pkgbase("6.6.1-zen1-1"), "linux-zen")
        self.assertEqual(
            SystemDiagnostics._infer_pkgbase("6.6.1-hardened1"), "linux-hardened"
        )


class TestAtomicTransactionManager(unittest.TestCase):
    """Test transaction preparation, staging, backup, and commit."""

    def test_transaction_commit_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_file = root / "config.conf"
            target_file.write_text("HOOKS=(base udev)\n")

            backup_dir = root / "backups" / "session1"
            txn = AtomicTransactionManager(backup_dir=backup_dir)

            new_content = "HOOKS=(systemd)\n"
            txn.stage_update(target_file, new_content)
            txn.prepare_and_backup()

            manifest_path = backup_dir / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text())
            self.assertIn(str(target_file.resolve()), manifest)

            sig_mgr = SignalManager()
            txn.commit(sig_mgr)
            self.assertEqual(target_file.read_text(), new_content)

            txn.rollback()
            self.assertEqual(target_file.read_text(), "HOOKS=(base udev)\n")


if __name__ == "__main__":
    unittest.main()

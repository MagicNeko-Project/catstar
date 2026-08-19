#!/usr/bin/env python3
"""
Arch Linux systemd-based Initramfs & Bootloader Migration Tool
==============================================================
Production-grade migration utility to transition Arch Linux systems from
legacy BusyBox/udev initramfs hooks to native systemd-based hooks and
migrate bootloader kernel command-line parameters from 'rw' to canonical 'ro'.
"""

import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import ClassVar

# Configuration Constants
DEFAULT_CONF_PATH = Path("/etc/mkinitcpio.conf")
BACKUP_DIR = Path("/var/backups/mkinitcpio-systemd-migration")


class ExitCode(IntEnum):
    SUCCESS = 0
    ERROR_GENERIC = 1
    ERROR_USAGE = 2
    USER_CANCELLED = 3
    PRIVILEGE_REQUIRED = 4
    VALIDATION_FAILED = 5
    PREFLIGHT_FAILED = 6


class Theme:
    """Zero-dependency terminal styler respecting TTY and NO_COLOR standard."""

    _NO_COLOR = bool(os.environ.get("NO_COLOR"))
    _FORCE_COLOR = bool(
        os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE")
    )
    _IS_TTY = sys.stdout.isatty() or _FORCE_COLOR
    ENABLED = _IS_TTY and not _NO_COLOR

    RESET = "\033[0m" if ENABLED else ""
    BOLD = "\033[1m" if ENABLED else ""
    DIM = "\033[2m" if ENABLED else ""

    HEADER = "\033[95m" if ENABLED else ""
    BLUE = "\033[94m" if ENABLED else ""
    CYAN = "\033[96m" if ENABLED else ""
    GREEN = "\033[92m" if ENABLED else ""
    YELLOW = "\033[93m" if ENABLED else ""
    RED = "\033[91m" if ENABLED else ""
    GRAY = "\033[90m" if ENABLED else ""

    UNICODE = sys.stdout.encoding and sys.stdout.encoding.lower().startswith("utf")
    CHECK = "✔" if UNICODE else "[+]"
    CROSS = "✖" if UNICODE else "[X]"
    INFO = "ℹ" if UNICODE else "[*]"
    WARN = "⚠" if UNICODE else "[!]"
    ARROW = "➜" if UNICODE else "->"
    BULLET = "•" if UNICODE else "*"

    @classmethod
    def disable(cls):
        cls.ENABLED = False
        cls.RESET = cls.BOLD = cls.DIM = ""
        cls.HEADER = cls.BLUE = cls.CYAN = cls.GREEN = cls.YELLOW = cls.RED = (
            cls.GRAY
        ) = ""


def log_info(msg: str) -> None:
    print(f"{Theme.BLUE}[INFO]{Theme.RESET} {msg}")


def log_success(msg: str) -> None:
    print(f"{Theme.GREEN}[SUCCESS]{Theme.RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"{Theme.YELLOW}[WARN]{Theme.RESET} {msg}")


def log_error(msg: str) -> None:
    print(f"{Theme.RED}[ERROR]{Theme.RESET} {msg}", file=sys.stderr)


def log_step(msg: str) -> None:
    print(f"\n{Theme.BOLD}{Theme.CYAN}==> {msg}{Theme.RESET}")


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class KernelInfo:
    kver: str
    pkgbase: str
    modules_dir: Path
    vmlinuz_path: Path | None = None


@dataclass
class HookAction:
    original: str | None
    migrated: str | None
    action: str  # "PRESERVED", "REPLACED", "DROPPED", "ADDED"
    rationale: str


@dataclass
class HookTranslationPlan:
    current_hooks: list[str]
    proposed_hooks: list[str]
    actions: list[HookAction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class BootloaderTarget:
    path: Path
    needs_update: bool
    original_content: str
    proposed_content: str
    bootloader_type: str


@dataclass
class ValidationResult:
    image_path: Path
    preset_type: str
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    embedded_hooks: list[str] = field(default_factory=list)


# ============================================================================
# Signal & Critical Section Management
# ============================================================================


class SignalManager:
    """Coordinates clean shutdowns and protects critical write sections."""

    def __init__(self):
        self._handlers: list[Callable[[], None]] = []
        self._in_critical_section: bool = False
        self._deferred_signal: int | None = None

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, self._handle_signal)

    def register_cleanup_handler(self, fn: Callable[[], None]) -> None:
        self._handlers.append(fn)

    def _handle_signal(self, signum: int, frame) -> None:
        sig_name = signal.Signals(signum).name
        if self._in_critical_section:
            self._deferred_signal = signum
            log_warn(
                f"Received {sig_name} during critical operation. Deferring until safe..."
            )
            return

        log_error(f"Received {sig_name}. Executing emergency rollback and cleanup...")
        self._execute_cleanup()
        sys.exit(128 + signum)

    def _execute_cleanup(self) -> None:
        for handler in reversed(self._handlers):
            try:
                handler()
            except Exception as e:  # noqa: BLE001
                log_error(f"Cleanup handler error: {e}")

    class CriticalSection:
        def __init__(self, manager: "SignalManager"):
            self.mgr = manager

        def __enter__(self):
            self.mgr._in_critical_section = True
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.mgr._in_critical_section = False
            if self.mgr._deferred_signal is not None:
                sig = self.mgr._deferred_signal
                self.mgr._deferred_signal = None
                self.mgr._handle_signal(sig, None)

    def critical_section(self) -> "CriticalSection":
        return self.CriticalSection(self)


global_signal_mgr = SignalManager()


# ============================================================================
# System Diagnostics & Kernel Resolution
# ============================================================================


class SystemDiagnostics:
    """Non-destructive environment and kernel discovery."""

    MODULES_BASE = Path("/usr/lib/modules")
    BOOT_DIR = Path("/boot")

    @staticmethod
    def verify_arch_linux() -> None:
        os_release = Path("/etc/os-release")
        if not os_release.exists():
            raise RuntimeError(
                "Cannot detect Linux distribution (/etc/os-release not found)."
            )
        content = os_release.read_text(encoding="utf-8")
        if not (
            "ID=arch" in content
            or "ID_LIKE=arch" in content
            or 'ID_LIKE="arch"' in content
        ):
            raise RuntimeError(
                "This script is specifically designed for Arch Linux and Arch-based distributions."
            )

    @staticmethod
    def verify_dependencies() -> None:
        required_bins = ["mkinitcpio", "lsinitcpio", "systemctl", "findmnt"]
        missing = [b for b in required_bins if shutil.which(b) is None]
        if missing:
            raise RuntimeError(
                f"Missing required utilities in PATH: {', '.join(missing)}"
            )

    @classmethod
    def discover_installed_kernels(cls) -> dict[str, KernelInfo]:
        installed: dict[str, KernelInfo] = {}
        if not cls.MODULES_BASE.exists():
            return installed

        for entry in cls.MODULES_BASE.iterdir():
            if not entry.is_dir():
                continue
            if (
                not (entry / "modules.dep").exists()
                and not (entry / "modules.dep.bin").exists()
            ):
                continue

            kver = entry.name
            pkgbase_file = entry / "pkgbase"
            if pkgbase_file.is_file():
                pkgbase = pkgbase_file.read_text(encoding="utf-8").strip()
            else:
                pkgbase = cls._infer_pkgbase(kver)

            vmlinuz = cls._find_vmlinuz(pkgbase, entry)
            info = KernelInfo(
                kver=kver, pkgbase=pkgbase, modules_dir=entry, vmlinuz_path=vmlinuz
            )
            installed[pkgbase] = info
            installed[kver] = info
        return installed

    @classmethod
    def resolve_target_kernel(cls, custom_kernel: str | None = None) -> KernelInfo:
        installed = cls.discover_installed_kernels()
        if not installed:
            raise RuntimeError(
                "No valid kernel module directories found in /usr/lib/modules"
            )

        if custom_kernel:
            clean_k = custom_kernel.removesuffix(".preset")
            if clean_k in installed:
                return installed[clean_k]
            if (cls.MODULES_BASE / custom_kernel).is_dir():
                return KernelInfo(
                    kver=custom_kernel,
                    pkgbase=cls._infer_pkgbase(custom_kernel),
                    modules_dir=cls.MODULES_BASE / custom_kernel,
                )
            raise RuntimeError(
                f"Specified kernel '{custom_kernel}' not found in /usr/lib/modules"
            )

        running_kver = os.uname().release
        if running_kver in installed:
            return installed[running_kver]

        # Handle post 'pacman -Syu' where running uname -r is removed from /lib/modules
        inferred = cls._infer_pkgbase(running_kver)
        if inferred in installed:
            return installed[inferred]

        unique = {k.kver: k for k in installed.values()}
        return next(iter(unique.values()))

    @staticmethod
    def _infer_pkgbase(kver: str) -> str:
        if "-lts612" in kver:
            return "linux-lts612"
        if "-lts" in kver:
            return "linux-lts"
        if "-zen" in kver:
            return "linux-zen"
        if "-hardened" in kver:
            return "linux-hardened"
        if "-arch" in kver:
            return "linux"
        return kver

    @classmethod
    def _find_vmlinuz(cls, pkgbase: str, modules_dir: Path) -> Path | None:
        candidates = [
            cls.BOOT_DIR / f"vmlinuz-{pkgbase}",
            cls.BOOT_DIR / f"vmlinuz-{pkgbase}.efi",
            modules_dir / "vmlinuz",
            cls.BOOT_DIR / "vmlinuz-linux",
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    @staticmethod
    def get_root_filesystem_type() -> str:
        try:
            res = subprocess.run(
                ["findmnt", "-n", "-o", "FSTYPE", "/"],
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip().lower()
        except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
            return "unknown"

    @staticmethod
    def get_kernel_cmdline() -> str:
        cmdline_path = Path("/proc/cmdline")
        if cmdline_path.exists():
            return cmdline_path.read_text(encoding="utf-8").strip()
        return ""


# ============================================================================
# Pre-Flight Safety Guard
# ============================================================================


class PreflightSafetyGuard:
    """Validates mounts, permissions, inodes, and disk space margins."""

    MIN_BOOT_FREE_MB = 100.0
    MIN_TMP_FREE_MB = 100.0

    @staticmethod
    def get_mount_options(path: Path) -> list[str]:
        resolved = path.resolve()
        best_match = ""
        best_opts: list[str] = []
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4:
                        mp = parts[1]
                        opts = parts[3].split(",")
                        if str(resolved).startswith(mp) and len(mp) > len(best_match):
                            best_match = mp
                            best_opts = opts
        except (OSError, ValueError):
            pass
        return best_opts

    @classmethod
    def verify_mount_writable(cls, target_dir: Path, probe_write: bool = True) -> None:
        opts = cls.get_mount_options(target_dir)
        if "ro" in opts:
            raise PermissionError(
                f"Filesystem at '{target_dir}' is mounted READ-ONLY (ro). Cannot proceed."
            )

        # Only probe write if running as root (or testing writeable temp)
        if probe_write and os.geteuid() == 0:
            try:
                with tempfile.NamedTemporaryFile(
                    "w", dir=target_dir, prefix=".probe_write_"
                ) as tf:
                    tf.write("sre_probe")
                    tf.flush()
            except OSError as e:
                raise PermissionError(
                    f"Directory '{target_dir}' failed write probe test: {e}"
                ) from e

    @classmethod
    def verify_disk_space(
        cls, boot_dir: Path = Path("/boot"), tmp_dir: Path = Path("/tmp")
    ) -> None:
        boot_usage = shutil.disk_usage(boot_dir)
        boot_free_mb = boot_usage.free / (1024 * 1024)

        existing_images = list(boot_dir.glob("initramfs-*.img")) + list(
            boot_dir.glob("*.efi")
        )
        total_existing_bytes = sum(
            img.stat().st_size for img in existing_images if img.is_file()
        )
        required_boot_mb = max(
            cls.MIN_BOOT_FREE_MB, (total_existing_bytes * 1.5) / (1024 * 1024)
        )

        if boot_free_mb < required_boot_mb:
            raise RuntimeError(
                f"Insufficient free space on {boot_dir}: {boot_free_mb:.1f} MB available, "
                f"at least {required_boot_mb:.1f} MB required."
            )

        # Inode check (only relevant on filesystems with inode tables where f_files > 0; FAT32/exFAT has f_files=0)
        statvfs = os.statvfs(boot_dir)
        if statvfs.f_files > 0 and statvfs.f_favail < 20:
            raise RuntimeError(
                f"Insufficient free inodes on {boot_dir}: only {statvfs.f_favail} inodes free."
            )

        tmp_usage = shutil.disk_usage(tmp_dir)
        tmp_free_mb = tmp_usage.free / (1024 * 1024)
        if tmp_free_mb < cls.MIN_TMP_FREE_MB:
            raise RuntimeError(
                f"Insufficient space in {tmp_dir} for dry-run testing: {tmp_free_mb:.1f} MB available."
            )


# ============================================================================
# Hook Translation Engine
# ============================================================================


class HookMigrator:
    """Parses, translates, and constructs mkinitcpio HOOKS arrays."""

    @staticmethod
    def parse_hooks(conf_content: str) -> list[str]:
        # Match all active (uncommented) HOOKS=(...) definitions
        matches = list(
            re.finditer(r"^\s*HOOKS=\(([^)]*)\)", conf_content, re.MULTILINE)
        )
        if not matches:
            raise ValueError(
                "Could not locate active 'HOOKS=(...)' definition in configuration."
            )
        # Bash executes top-down and honors the LAST defined variable in scope
        active_match = matches[-1]
        raw_content = active_match.group(1)

        try:
            raw_hooks = shlex.split(raw_content, comments=True)
        except ValueError:
            raw_hooks = [
                h.strip("'\" \t")
                for h in raw_content.split()
                if not h.strip().startswith("#")
            ]

        return [h.strip("'\" \t") for h in raw_hooks if h.strip("'\" \t")]

    @classmethod
    def update_hooks_in_config(cls, conf_content: str, new_hooks: list[str]) -> str:
        matches = list(
            re.finditer(r"^\s*HOOKS=\(([^)]*)\)", conf_content, re.MULTILINE)
        )
        if not matches:
            raise ValueError(
                "Could not locate active 'HOOKS=(...)' definition in configuration."
            )
        last_match = matches[-1]
        hooks_str = f"HOOKS=({' '.join(new_hooks)})"
        start, end = last_match.span()
        return conf_content[:start] + hooks_str + conf_content[end:]

    @classmethod
    def translate_hooks(
        cls, old_hooks: list[str], root_fstype: str = "", cmdline: str = ""
    ) -> HookTranslationPlan:
        old_set = set(old_hooks)
        new_hooks: list[str] = []
        added_set: set[str] = set()
        actions: list[HookAction] = []
        notes: list[str] = []

        def add_h(h: str):
            if h not in added_set:
                new_hooks.append(h)
                added_set.add(h)

        # 1. Base emergency shell & systemd PID 1 early userspace
        if "base" in old_set:
            add_h("base")
            actions.append(
                HookAction(
                    "base",
                    "base",
                    "PRESERVED",
                    "Provides emergency BusyBox utilities for systemd-sulogin-shell",
                )
            )
            notes.append("Retained 'base' hook for emergency rescue shell utilities.")

        add_h("systemd")
        if "udev" in old_set:
            actions.append(
                HookAction(
                    "udev",
                    "systemd",
                    "REPLACED",
                    "Integrated into systemd PID 1 initrd",
                )
            )
            notes.append("Replaced legacy 'udev' with 'systemd'.")
        elif "systemd" not in old_set:
            actions.append(
                HookAction(
                    None, "systemd", "ADDED", "Native systemd PID 1 early userspace"
                )
            )

        # 2. autodetect & microcode
        if "autodetect" in old_set:
            add_h("autodetect")
            actions.append(
                HookAction(
                    "autodetect",
                    "autodetect",
                    "PRESERVED",
                    "Shrinks initramfs to host hardware modules",
                )
            )
        if "microcode" in old_set:
            add_h("microcode")
            actions.append(
                HookAction(
                    "microcode",
                    "microcode",
                    "PRESERVED",
                    "Early uncompressed CPU microcode loading",
                )
            )
        if "modconf" in old_set:
            add_h("modconf")
            actions.append(
                HookAction(
                    "modconf",
                    "modconf",
                    "PRESERVED",
                    "Module configuration and blacklists",
                )
            )
        if "kms" in old_set:
            add_h("kms")
            actions.append(
                HookAction("kms", "kms", "PRESERVED", "Early graphics DRM modesetting")
            )
        if "keyboard" in old_set:
            add_h("keyboard")
            actions.append(
                HookAction(
                    "keyboard",
                    "keyboard",
                    "PRESERVED",
                    "Input keyboard drivers for early userspace",
                )
            )

        # 3. Console & Virtual Terminal
        if "keymap" in old_set or "consolefont" in old_set or "sd-vconsole" in old_set:
            add_h("sd-vconsole")
            if "keymap" in old_set:
                actions.append(
                    HookAction(
                        "keymap",
                        "sd-vconsole",
                        "REPLACED",
                        "Native /etc/vconsole.conf keymap setup",
                    )
                )
            if "consolefont" in old_set:
                actions.append(
                    HookAction(
                        "consolefont", None, "DROPPED", "Consolidated into sd-vconsole"
                    )
                )
            notes.append("Replaced 'keymap' / 'consolefont' with native 'sd-vconsole'.")

        # 4. Encryption
        if "encrypt" in old_set or "sd-encrypt" in old_set:
            add_h("sd-encrypt")
            if "encrypt" in old_set:
                actions.append(
                    HookAction(
                        "encrypt",
                        "sd-encrypt",
                        "REPLACED",
                        "systemd-cryptsetup with TPM2/FIDO2 & rd.luks support",
                    )
                )
                notes.append("Replaced 'encrypt' with 'sd-encrypt'.")

        # 5. Core Storage Layers
        if "block" in old_set:
            add_h("block")
            actions.append(
                HookAction("block", "block", "PRESERVED", "Block device driver modules")
            )
        if "mdadm_udev" in old_set or "mdadm" in old_set:
            add_h("mdadm_udev")
            actions.append(
                HookAction(
                    "mdadm_udev" if "mdadm_udev" in old_set else "mdadm",
                    "mdadm_udev",
                    "PRESERVED",
                    "Software RAID assembly",
                )
            )
        if "lvm2" in old_set or "sd-lvm2" in old_set:
            add_h("lvm2")
            actions.append(
                HookAction(
                    "lvm2",
                    "lvm2",
                    "PRESERVED",
                    "LVM2 volume discovery with systemd udev rules",
                )
            )
        if "btrfs" in old_set:
            add_h("btrfs")
            actions.append(
                HookAction("btrfs", "btrfs", "PRESERVED", "Multi-device Btrfs scanning")
            )
        if "zfs" in old_set:
            add_h("zfs")
            actions.append(
                HookAction("zfs", "zfs", "PRESERVED", "ZFS root import and mounting")
            )

        # 6. Unmapped custom hooks
        known_hooks = {
            "base",
            "udev",
            "autodetect",
            "microcode",
            "modconf",
            "kms",
            "keyboard",
            "keymap",
            "consolefont",
            "sd-vconsole",
            "encrypt",
            "sd-encrypt",
            "block",
            "mdadm",
            "mdadm_udev",
            "lvm2",
            "sd-lvm2",
            "btrfs",
            "zfs",
            "resume",
            "shutdown",
            "sd-shutdown",
            "fsck",
            "filesystems",
        }
        for h in old_hooks:
            if h not in known_hooks and h not in added_set:
                add_h(h)
                actions.append(
                    HookAction(h, h, "PRESERVED", "Custom user hook retained")
                )
                notes.append(f"Preserved custom hook: '{h}'.")

        # 7. Filesystems
        if "filesystems" in old_set:
            add_h("filesystems")
            actions.append(
                HookAction(
                    "filesystems",
                    "filesystems",
                    "PRESERVED",
                    "Kernel filesystem drivers",
                )
            )

        # 8. Shutdown hook
        if "shutdown" in old_set or "sd-shutdown" in old_set:
            add_h("sd-shutdown")
            actions.append(
                HookAction(
                    "shutdown" if "shutdown" in old_set else "sd-shutdown",
                    "sd-shutdown",
                    "REPLACED" if "shutdown" in old_set else "PRESERVED",
                    "Clean unmount and crypto detachment on shutdown",
                )
            )
            notes.append("Configured 'sd-shutdown' for clean poweroff/reboot pivot.")

        # 9. FSCK Handling (Replaced entirely by systemd-fsck-root on ro root)
        if "fsck" in old_set:
            actions.append(
                HookAction(
                    "fsck",
                    None,
                    "DROPPED",
                    "Replaced by native systemd-fsck-root.service on 'ro' root",
                )
            )
            notes.append(
                "Dropped redundant 'fsck' hook (systemd-fsck handles root checks natively)."
            )

        return HookTranslationPlan(
            current_hooks=old_hooks,
            proposed_hooks=new_hooks,
            actions=actions,
            notes=notes,
        )


# ============================================================================
# Bootloader Migrator
# ============================================================================


class BootloaderMigrator:
    """Discovers, audits, and transforms bootloader parameters from 'rw' to 'ro'."""

    @staticmethod
    def find_bootloader_configs() -> list[Path]:
        candidates: list[Path] = []
        for d in [
            Path("/boot/loader/entries"),
            Path("/efi/loader/entries"),
            Path("/boot/efi/loader/entries"),
        ]:
            if d.exists() and d.is_dir():
                candidates.extend(sorted(d.glob("*.conf")))

        for p in [Path("/etc/kernel/cmdline"), Path("/etc/cmdline")]:
            if p.exists() and p.is_file():
                candidates.append(p)
        cmd_d = Path("/etc/cmdline.d")
        if cmd_d.exists() and cmd_d.is_dir():
            candidates.extend(sorted(cmd_d.glob("*.conf")))

        grub_def = Path("/etc/default/grub")
        if grub_def.exists() and grub_def.is_file():
            candidates.append(grub_def)

        for p in [
            Path("/boot/limine.cfg"),
            Path("/boot/limine/limine.cfg"),
            Path("/boot/limine.conf"),
            Path("/boot/refind_linux.conf"),
        ]:
            if p.exists() and p.is_file():
                candidates.append(p)

        unique: list[Path] = []
        for c in candidates:
            if c not in unique:
                unique.append(c)
        return unique

    @classmethod
    def audit_config(cls, path: Path) -> BootloaderTarget:
        content = path.read_text(encoding="utf-8")
        bl_type = "unknown"

        def replacer(m):
            line = m.group(0)
            tokens = line.split()
            new_tokens = []
            has_ro = "ro" in tokens
            for t in tokens:
                if t == "rw":
                    if not has_ro and "ro" not in new_tokens:
                        new_tokens.append("ro")
                else:
                    new_tokens.append(t)
            return " ".join(new_tokens)

        if path.suffix == ".conf" and "loader/entries" in str(path):
            bl_type = "systemd-boot"
            new_content = re.sub(
                r"^(\s*options\s+.*)$", replacer, content, flags=re.MULTILINE
            )
        elif path.name == "grub":
            bl_type = "GRUB"
            new_content = re.sub(
                r"^(\s*GRUB_CMDLINE_LINUX(?:_DEFAULT)?=.*)$",
                replacer,
                content,
                flags=re.MULTILINE,
            )
        elif "cmdline" in path.name:
            bl_type = "UKI / Cmdline"
            new_content = replacer(re.match(r".*", content))
        else:
            bl_type = "Generic Bootloader"
            new_content = re.sub(
                r"(\boptions\b.*?\b|\bcmdline.*?\b)rw(\b|$)", r"\g<1>ro\2", content
            )

        needs_update = content != new_content
        return BootloaderTarget(
            path=path,
            needs_update=needs_update,
            original_content=content,
            proposed_content=new_content,
            bootloader_type=bl_type,
        )


# ============================================================================
# ACID Multi-File Atomic Transaction Manager
# ============================================================================


@dataclass
class FileUpdateOp:
    target_path: Path
    new_content: str
    temp_path: Path | None = None
    backup_path: Path | None = None
    original_stat: os.stat_result | None = None


class AtomicTransactionManager:
    """2-Phase Multi-File Transaction Coordinator with POSIX fsync and VFAT safety."""

    def __init__(self, backup_dir: Path):
        self.backup_dir = backup_dir
        self.operations: list[FileUpdateOp] = []
        self.staged_temps: list[Path] = []

    def stage_update(self, target_path: Path, new_content: str) -> None:
        self.operations.append(
            FileUpdateOp(target_path=target_path.resolve(), new_content=new_content)
        )

    def prepare_and_backup(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        manifest = {}

        for op in self.operations:
            target = op.target_path
            if not target.exists():
                raise FileNotFoundError(f"Target file does not exist: {target}")

            op.original_stat = target.stat()
            safe_name = str(target).replace("/", "_").strip("_")
            b_path = self.backup_dir / safe_name
            shutil.copy2(target, b_path)
            op.backup_path = b_path
            manifest[str(target)] = safe_name

            parent_dir = target.parent
            with tempfile.NamedTemporaryFile(
                "w",
                dir=parent_dir,
                prefix=".tmp_trans_",
                delete=False,
                encoding="utf-8",
            ) as tf:
                op.temp_path = Path(tf.name)
                self.staged_temps.append(op.temp_path)
                tf.write(op.new_content)
                tf.flush()
                os.fsync(tf.fileno())

            # Handle VFAT/ESP permissions defensively
            try:
                os.chmod(op.temp_path, op.original_stat.st_mode)
            except OSError:
                pass
            try:
                os.chown(op.temp_path, op.original_stat.st_uid, op.original_stat.st_gid)
            except OSError:
                pass

        (self.backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        latest = self.backup_dir.parent / "backup_latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(self.backup_dir.name)

    def commit(self, signal_mgr: SignalManager) -> None:
        with signal_mgr.critical_section():
            applied: list[FileUpdateOp] = []
            try:
                for op in self.operations:
                    if op.temp_path is None or not op.temp_path.exists():
                        raise RuntimeError(f"Staged file missing for {op.target_path}")
                    os.replace(op.temp_path, op.target_path)
                    applied.append(op)
                    if op.temp_path in self.staged_temps:
                        self.staged_temps.remove(op.temp_path)

                    try:
                        dir_fd = os.open(
                            str(op.target_path.parent), os.O_RDONLY | os.O_DIRECTORY
                        )
                        try:
                            os.fsync(dir_fd)
                        finally:
                            os.close(dir_fd)
                    except OSError:
                        pass
            except Exception as e:
                log_error(f"Commit error: {e}. Executing emergency rollback...")
                for op in reversed(applied):
                    if op.backup_path and op.backup_path.exists():
                        shutil.copy2(op.backup_path, op.target_path)
                self.cleanup_temp_files()
                raise

    def rollback(self) -> None:
        log_warn("Restoring configuration files from backup snapshot...")
        for op in reversed(self.operations):
            if op.backup_path and op.backup_path.exists():
                shutil.copy2(op.backup_path, op.target_path)
                log_info(f"Restored: {op.target_path}")
        self.cleanup_temp_files()

    def cleanup_temp_files(self) -> None:
        for p in self.staged_temps:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        self.staged_temps.clear()


# ============================================================================
# Empirical Image Validator
# ============================================================================


class RobustImageValidator:
    """Deep empirical inspection of generated initramfs images."""

    MANDATORY_SYSTEMD_PATHS: ClassVar[list[str]] = [
        "init",
        "usr/lib/systemd/systemd",
        "usr/lib/systemd/systemd-journald",
        "usr/lib/systemd/system/initrd.target",
        "usr/lib/systemd/system/initrd-switch-root.service",
    ]

    @staticmethod
    def get_expected_hooks(image_name: str, base_hooks: list[str]) -> list[str]:
        if "fallback" in image_name.lower():
            return [h for h in base_hooks if h != "autodetect"]
        return list(base_hooks)

    @classmethod
    def discover_preset_images(
        cls, preset_dir: Path = Path("/etc/mkinitcpio.d")
    ) -> list[tuple[Path, str]]:
        discovered: list[tuple[Path, str]] = []
        if not preset_dir.exists():
            return discovered

        for pf in preset_dir.glob("*.preset"):
            content = pf.read_text(encoding="utf-8")
            matches = re.findall(
                r"^(\w+)_image=[\"']?([^\"'\n]+)[\"']?", content, re.MULTILINE
            )
            for ptype, img_str in matches:
                discovered.append((Path(img_str.strip()), ptype))
        return discovered

    @classmethod
    def validate_image(
        cls,
        image_path: Path,
        expected_base_hooks: list[str],
        preset_type: str = "default",
    ) -> ValidationResult:
        errors: list[str] = []
        embedded_hooks: list[str] = []

        if not image_path.exists():
            return ValidationResult(
                image_path,
                preset_type,
                False,
                [f"Image file does not exist: {image_path}"],
            )
        if image_path.stat().st_size == 0:
            return ValidationResult(
                image_path,
                preset_type,
                False,
                [f"Image file is empty (0 bytes): {image_path}"],
            )

        expected_hooks = cls.get_expected_hooks(image_path.name, expected_base_hooks)

        # 1. Embedded config check
        res_cfg = subprocess.run(
            ["lsinitcpio", "-c", str(image_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res_cfg.returncode != 0:
            errors.append(f"lsinitcpio -c failed: {res_cfg.stderr.strip()}")
        else:
            match = re.search(r"^\s*HOOKS=\(([^)]*)\)", res_cfg.stdout, re.MULTILINE)
            if match:
                raw_cfg = match.group(1)
                try:
                    raw_tokens = shlex.split(raw_cfg, comments=True)
                except ValueError:
                    raw_tokens = raw_cfg.split()
                embedded_hooks = [
                    h.strip("'\" \t") for h in raw_tokens if h.strip("'\" \t")
                ]
                if "systemd" not in embedded_hooks:
                    errors.append(
                        f"Missing mandatory 'systemd' hook in embedded HOOKS={embedded_hooks}"
                    )
                if "udev" in embedded_hooks:
                    errors.append("Legacy 'udev' hook still present in systemd image.")
            else:
                errors.append("Could not parse HOOKS from image config.")

        # 2. Manifest check
        res_list = subprocess.run(
            ["lsinitcpio", str(image_path)], capture_output=True, text=True, check=False
        )
        if res_list.returncode != 0:
            errors.append(f"lsinitcpio manifest failed: {res_list.stderr.strip()}")
            return ValidationResult(
                image_path, preset_type, False, errors, embedded_hooks
            )

        manifest = set(res_list.stdout.splitlines())

        for p in cls.MANDATORY_SYSTEMD_PATHS:
            if p not in manifest:
                errors.append(f"Missing required systemd component: '{p}'")

        if (
            "lvm2" in expected_hooks
            and "usr/lib/udev/rules.d/69-dm-lvm.rules" not in manifest
            and "usr/bin/lvm" not in manifest
        ):
            errors.append("LVM2 hook enabled but missing LVM udev rules/binary.")

        if (
            "sd-encrypt" in expected_hooks
            and "usr/lib/systemd/systemd-cryptsetup" not in manifest
            and "usr/lib/systemd/system/systemd-cryptsetup@.service" not in manifest
        ):
            errors.append(
                "sd-encrypt hook enabled but missing systemd-cryptsetup binary/service."
            )

        if (
            "sd-vconsole" in expected_hooks
            and "usr/lib/systemd/system/systemd-vconsole-setup.service" not in manifest
        ):
            errors.append(
                "sd-vconsole enabled but missing systemd-vconsole-setup.service."
            )

        return ValidationResult(
            image_path, preset_type, len(errors) == 0, errors, embedded_hooks
        )


# ============================================================================
# Visual Renderers & UI
# ============================================================================


class DiffViewer:
    """Generates colored unified diff previews."""

    @staticmethod
    def render_diff(filepath: str, old_text: str, new_text: str) -> str:
        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"{filepath} (active)",
                tofile=f"{filepath} (proposed)",
                n=2,
            )
        )
        if not diff_lines:
            return f"  {Theme.DIM}(No changes required){Theme.RESET}"

        rendered = []
        for line in diff_lines:
            s = line.rstrip("\r\n")
            if s.startswith(("---", "+++")):
                rendered.append(f"{Theme.BOLD}{s}{Theme.RESET}")
            elif s.startswith("@@"):
                rendered.append(f"{Theme.CYAN}{s}{Theme.RESET}")
            elif s.startswith("+"):
                rendered.append(f"{Theme.GREEN}{s}{Theme.RESET}")
            elif s.startswith("-"):
                rendered.append(f"{Theme.RED}{s}{Theme.RESET}")
            else:
                rendered.append(f" {s}")
        return "\n".join(rendered)


class TableRenderer:
    """Aligned terminal tables without third-party dependencies."""

    @staticmethod
    def render_plan_table(plan: HookTranslationPlan) -> str:
        headers = ["Original Hook", "Migrated Hook", "Action", "Rationale"]
        rows = []
        for a in plan.actions:
            rows.append(
                [a.original or "-", a.migrated or "[DROPPED]", a.action, a.rationale]
            )

        col_w = [len(h) for h in headers]
        for r in rows:
            for i, val in enumerate(r):
                col_w[i] = max(col_w[i], len(val))

        sep = "+" + "+".join("-" * (w + 2) for w in col_w) + "+"
        hdr = (
            "| "
            + " | ".join(f"{headers[i]:<{col_w[i]}}" for i in range(len(headers)))
            + " |"
        )
        lines = [sep, hdr, sep]
        for r in rows:
            lines.append(
                "| " + " | ".join(f"{r[i]:<{col_w[i]}}" for i in range(len(r))) + " |"
            )
        lines.append(sep)
        return "\n".join(lines)


# ============================================================================
# Main Controller & Execution Logic
# ============================================================================


def confirm_execution(prompt_msg: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Non-interactive shell detected with '--apply'. Pass '--yes' / '-y' to confirm execution."
        )
    try:
        ans = (
            input(f"\n{Theme.BOLD}{Theme.YELLOW}{prompt_msg} [y/N]: {Theme.RESET}")
            .strip()
            .lower()
        )
        return ans in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print()
        return False


def run_dry_run_sandbox(
    conf_path: Path, new_hooks: list[str], kernel_info: KernelInfo
) -> None:
    log_info("Starting isolated dry-run test build...")
    with tempfile.TemporaryDirectory(prefix="mkinitcpio-test-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_conf = tmpdir_path / "mkinitcpio.test.conf"
        test_img = tmpdir_path / "initramfs-test.img"

        orig_content = conf_path.read_text(encoding="utf-8")
        test_content = HookMigrator.update_hooks_in_config(orig_content, new_hooks)
        test_conf.write_text(test_content, encoding="utf-8")

        cmd = [
            "mkinitcpio",
            "-c",
            str(test_conf),
            "-g",
            str(test_img),
            "-k",
            kernel_info.kver,
        ]
        log_info(f"Executing: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            log_error(f"Dry-run build failed (code {res.returncode}):\n{res.stderr}")
            raise RuntimeError("Dry-run build failed. System remains untouched.")

        val_res = RobustImageValidator.validate_image(
            test_img, new_hooks, "sandbox-test"
        )
        if not val_res.is_valid:
            log_error("Dry-run image assertions failed:")
            for err in val_res.errors:
                log_error(f"  - {err}")
            raise RuntimeError("Dry-run validation assertions failed.")

        log_success("Sandbox test build and deep image assertions PASSED.")


def execute_rollback(backup_base_dir: Path) -> None:
    latest_symlink = backup_base_dir / "backup_latest"
    if not latest_symlink.exists():
        raise RuntimeError(
            f"No backup session found at {latest_symlink}. Cannot rollback."
        )

    session_dir = latest_symlink.resolve()
    log_warn(f"Rolling back to session backup: {session_dir}")

    manifest_file = session_dir / "manifest.json"
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text())
        for orig_str, safe_name in manifest.items():
            orig_p = Path(orig_str)
            src_p = session_dir / safe_name
            if src_p.exists():
                shutil.copy2(src_p, orig_p)
                log_success(f"Restored: {orig_p}")

    log_info("Rebuilding all preset images with restored configuration...")
    res = subprocess.run(
        ["mkinitcpio", "-P"], capture_output=True, text=True, check=False
    )
    if res.returncode != 0:
        log_error(f"Preset rebuild during rollback failed:\n{res.stderr}")
        sys.exit(ExitCode.ERROR_GENERIC)
    print(res.stdout)
    log_success("Rollback completed successfully.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="migrate_to_systemd_initramfs.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Arch Linux systemd-based Initramfs & Bootloader Migration Tool
==============================================================
Safely transitions mkinitcpio from BusyBox/udev to native systemd hooks,
replaces legacy 'rw' kernel parameters with canonical 'ro', and validates
all generated initramfs images against mandatory systemd service manifests.
        """,
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform non-destructive diagnostics and sandbox test build.",
    )
    action_group.add_argument(
        "-a",
        "--apply",
        action="store_true",
        default=False,
        help="Execute migration, backups, atomic edits, and preset rebuild.",
    )
    action_group.add_argument(
        "-r",
        "--rollback",
        action="store_true",
        default=False,
        help="Roll back configuration files from latest backup session.",
    )

    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Assume 'yes' to confirmation prompts (for automated pipelines).",
    )
    parser.add_argument(
        "-d",
        "--diff",
        action="store_true",
        default=False,
        help="Always display colorized unified diff previews.",
    )
    parser.add_argument(
        "-k",
        "--kernel",
        type=str,
        default=None,
        help="Target specific kernel version (defaults to auto-discovery).",
    )
    parser.add_argument(
        "-c",
        "--conf",
        type=Path,
        default=DEFAULT_CONF_PATH,
        help=f"Path to mkinitcpio.conf (default: {DEFAULT_CONF_PATH})",
    )
    parser.add_argument(
        "--skip-bootloader",
        action="store_true",
        default=False,
        help="Skip migrating bootloader command-line parameters ('rw' -> 'ro').",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        default=False,
        help="Emit machine-readable JSON output to stdout.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI color formatting.",
    )

    raw_args = argv if argv is not None else sys.argv[1:]
    if not raw_args:
        parser.print_help()
        return

    args = parser.parse_args(argv)

    if args.no_color or args.json:
        Theme.disable()

    if not (args.apply or args.dry_run or args.rollback):
        parser.print_help()
        return

    # Handle Rollback
    if args.rollback:
        if os.geteuid() != 0:
            log_error("Error: --rollback requires root privileges (uid 0).")
            sys.exit(ExitCode.PRIVILEGE_REQUIRED)
        execute_rollback(BACKUP_DIR)
        return

    # Early Privilege check on --apply
    if args.apply and os.geteuid() != 0:
        log_error(
            "Error: --apply requires root privileges (uid 0). Please run with sudo."
        )
        sys.exit(ExitCode.PRIVILEGE_REQUIRED)

    if not args.json:
        print(
            f"{Theme.BOLD}{Theme.HEADER}=== Arch Linux systemd-based Initramfs Migrator ==={Theme.RESET}"
        )

    # Phase 1: Environment Diagnostics & Pre-Flight
    if not args.json:
        log_step("Phase 1: Environment Diagnostics & Pre-Flight Safety")
    try:
        SystemDiagnostics.verify_arch_linux()
        SystemDiagnostics.verify_dependencies()
        kernel_info = SystemDiagnostics.resolve_target_kernel(args.kernel)
        root_fstype = SystemDiagnostics.get_root_filesystem_type()
        cmdline = SystemDiagnostics.get_kernel_cmdline()

        # In dry-run mode without root, verify mount flags but don't probe write root-owned /boot
        probe_write = args.apply and os.geteuid() == 0
        PreflightSafetyGuard.verify_mount_writable(
            Path("/boot"), probe_write=probe_write
        )
        PreflightSafetyGuard.verify_mount_writable(
            args.conf.parent, probe_write=probe_write
        )
        PreflightSafetyGuard.verify_disk_space(
            boot_dir=Path("/boot"), tmp_dir=Path("/tmp")
        )

        if not args.json:
            log_info("Distribution: Arch Linux")
            log_info(f"Target Kernel: {kernel_info.kver} ({kernel_info.pkgbase})")
            log_info(f"Root Filesystem: {root_fstype}")
            log_info(f"Active Cmdline: {cmdline}")
            log_success("Pre-flight safety guards & disk space checks PASSED.")
    except Exception as e:  # noqa: BLE001
        log_error(f"Pre-flight diagnostics failed: {e}")
        sys.exit(ExitCode.PREFLIGHT_FAILED)

    # Phase 2: Hook Translation Plan
    if not args.json:
        log_step("Phase 2: Hook Translation Plan")
    if not args.conf.exists():
        log_error(f"Configuration file {args.conf} does not exist.")
        sys.exit(ExitCode.ERROR_USAGE)

    conf_content = args.conf.read_text(encoding="utf-8")
    try:
        current_hooks = HookMigrator.parse_hooks(conf_content)
        plan = HookMigrator.translate_hooks(current_hooks, root_fstype, cmdline=cmdline)
    except Exception as e:  # noqa: BLE001
        log_error(f"Failed to parse hooks: {e}")
        sys.exit(ExitCode.ERROR_USAGE)

    if not args.json:
        print(TableRenderer.render_plan_table(plan))
        for n in plan.notes:
            print(f"  {Theme.CYAN}•{Theme.RESET} {n}")

    # Phase 3: Bootloader Kernel Parameter Audit
    if not args.json:
        log_step("Phase 3: Bootloader Kernel Parameter Audit ('rw' -> 'ro')")
    bl_files = BootloaderMigrator.find_bootloader_configs()
    bl_targets: list[BootloaderTarget] = []

    for bf in bl_files:
        target = BootloaderMigrator.audit_config(bf)
        bl_targets.append(target)
        if not args.json:
            tag = (
                f"{Theme.YELLOW}[Needs 'rw' -> 'ro']{Theme.RESET}"
                if target.needs_update
                else f"{Theme.GREEN}[Already 'ro' / Clean]{Theme.RESET}"
            )
            print(f"  • {target.path} ({target.bootloader_type}) {tag}")

    # Display Diff Previews
    if (args.diff or args.apply) and not args.json:
        log_step("Configuration Diff Previews")
        new_mk_content = HookMigrator.update_hooks_in_config(
            conf_content, plan.proposed_hooks
        )
        print(f"\n{Theme.BOLD}--- {args.conf} ---{Theme.RESET}")
        print(DiffViewer.render_diff(str(args.conf), conf_content, new_mk_content))

        if not args.skip_bootloader:
            for bt in bl_targets:
                if bt.needs_update:
                    print(f"\n{Theme.BOLD}--- {bt.path} ---{Theme.RESET}")
                    print(
                        DiffViewer.render_diff(
                            str(bt.path), bt.original_content, bt.proposed_content
                        )
                    )

    # Phase 4: Sandbox Dry-Run Test
    if not args.json:
        log_step("Phase 4: Sandbox Test Build & Image Assertions")
    try:
        run_dry_run_sandbox(args.conf, plan.proposed_hooks, kernel_info)
    except Exception as e:  # noqa: BLE001
        log_error(f"Dry-run test failed: {e}")
        sys.exit(ExitCode.VALIDATION_FAILED)

    grub_needs_update = (
        any(t.bootloader_type == "GRUB" and t.needs_update for t in bl_targets)
        and not args.skip_bootloader
    )

    if args.dry_run:
        if args.json:
            out_data = {
                "status": "success",
                "mode": "dry-run",
                "kernel": asdict(kernel_info),
                "root_fstype": root_fstype,
                "plan": asdict(plan),
                "bootloader_targets": [asdict(t) for t in bl_targets],
                "grub_update_required": grub_needs_update,
            }
            print(json.dumps(out_data, indent=2, default=str))
        else:
            log_success(
                "\n[DRY RUN COMPLETE] Validation succeeded. Zero disk changes made."
            )
            if grub_needs_update:
                print(
                    f"\n{Theme.YELLOW}[NOTE]{Theme.RESET} GRUB configuration requires regeneration after applying updates:"
                )
                print(
                    f"  {Theme.BOLD}sudo grub-mkconfig -o /boot/grub/grub.cfg{Theme.RESET}"
                )
            print(
                f"\nRun with '{Theme.BOLD}sudo {sys.argv[0]} --apply{Theme.RESET}' to execute migration."
            )
        return

    # Phase 5: Interactive Confirmation & Execution
    if not args.json:
        log_step("Phase 5: Elevated Execution & 2-Phase Atomic Commit")
        if not confirm_execution(
            "Proceed with migration, atomic file updates, and initramfs rebuild?",
            args.yes,
        ):
            log_warn("Migration cancelled by user. Zero changes applied.")
            sys.exit(ExitCode.USER_CANCELLED)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    session_backup = BACKUP_DIR / f"backup_{timestamp}"
    txn = AtomicTransactionManager(backup_dir=session_backup)

    global_signal_mgr.register_cleanup_handler(txn.rollback)
    global_signal_mgr.register_cleanup_handler(txn.cleanup_temp_files)

    # Stage mkinitcpio.conf
    new_mk_content = HookMigrator.update_hooks_in_config(
        conf_content, plan.proposed_hooks
    )
    txn.stage_update(args.conf, new_mk_content)

    # Stage bootloader updates
    if not args.skip_bootloader:
        for bt in bl_targets:
            if bt.needs_update:
                txn.stage_update(bt.path, bt.proposed_content)

    try:
        txn.prepare_and_backup()
        txn.commit(global_signal_mgr)
        log_success("Atomic configuration transaction committed.")
    except Exception as e:  # noqa: BLE001
        log_error(f"Transaction failure: {e}")
        sys.exit(ExitCode.ERROR_GENERIC)

    # Rebuild all presets
    if not args.json:
        log_info("Rebuilding all initramfs presets via 'mkinitcpio -P'...")
    try:
        with global_signal_mgr.critical_section():
            res = subprocess.run(
                ["mkinitcpio", "-P"], capture_output=True, text=True, check=True
            )
            if not args.json:
                print(res.stdout)
    except Exception as e:  # noqa: BLE001
        log_error(f"Preset rebuild failed: {e}. Executing emergency rollback...")
        txn.rollback()
        subprocess.run(["mkinitcpio", "-P"], capture_output=True, check=False)
        sys.exit(ExitCode.ERROR_GENERIC)

    # Phase 6: Post-Rebuild Image Validation across All Presets
    if not args.json:
        log_step("Phase 6: Post-Rebuild Image Validation (All Presets)")
    preset_images = RobustImageValidator.discover_preset_images()
    if not preset_images:
        preset_images = [(p, "default") for p in Path("/boot").glob("initramfs-*.img")]

    all_valid = True
    val_results = []
    for img_path, ptype in preset_images:
        if img_path.exists():
            v_res = RobustImageValidator.validate_image(
                img_path, plan.proposed_hooks, ptype
            )
            val_results.append(v_res)
            if v_res.is_valid:
                if not args.json:
                    log_success(f"Validated {ptype} image: {img_path.name}")
            else:
                all_valid = False
                if not args.json:
                    log_error(f"Validation failed for {img_path.name} ({ptype}):")
                    for err in v_res.errors:
                        log_error(f"  - {err}")

    if not all_valid:
        log_error(
            "Validation assertions failed on newly generated images. Rolling back..."
        )
        txn.rollback()
        subprocess.run(["mkinitcpio", "-P"], capture_output=True, check=False)
        sys.exit(ExitCode.VALIDATION_FAILED)

    if args.json:
        out_data = {
            "status": "success",
            "mode": "applied",
            "backup_dir": str(session_backup),
            "validation_results": [asdict(r) for r in val_results],
            "grub_update_required": grub_needs_update,
        }
        print(json.dumps(out_data, indent=2, default=str))
    else:
        print(
            f"\n{Theme.BOLD}{Theme.GREEN}✔ Migration to systemd-based initramfs completed successfully!{Theme.RESET}"
        )
        print(f"Pristine backups securely stored in: {session_backup}")
        if grub_needs_update:
            print(
                f"\n{Theme.YELLOW}[NOTE]{Theme.RESET} GRUB configuration at /etc/default/grub was updated."
            )
            print(
                f"Remember to regenerate your GRUB configuration before rebooting:\n"
                f"  {Theme.BOLD}sudo grub-mkconfig -o /boot/grub/grub.cfg{Theme.RESET}"
            )
        print("\nYou can reboot whenever ready to boot into the new systemd initramfs.")


if __name__ == "__main__":
    main()

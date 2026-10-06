#!/usr/bin/python3
"""Portable installer with backups, rollback, and independent removal."""

import argparse
import datetime
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MARKER = b"ubuntu-memory-guard managed file"
SOURCE = Path(__file__).resolve().parents[1]
NAME = "ubuntu-memory-guard.service"


def load_guard(source):
    spec = importlib.util.spec_from_file_location("guard_for_installer", source / "memory_guard.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def atomic_write(path, content, mode=0o644):
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Installer:
    def __init__(self, source=SOURCE, root=Path("/"), manage_service=True):
        self.source = source
        self.root = root
        self.manage_service = manage_service
        self.library = root / "usr/local/lib/ubuntu-memory-guard"
        self.unit = root / "etc/systemd/system" / NAME
        self.config = root / "etc/ubuntu-memory-guard/config.toml"
        self.files = {
            self.library / "memory_guard.py": source / "memory_guard.py",
            self.unit: source / NAME,
        }

    def run(self, *args, check=True):
        return subprocess.run(args, check=check, text=True, capture_output=True)

    def validate_paths(self, include_sources=True):
        for destination in [*self.files, self.config]:
            for path in (destination, *destination.parents):
                if path == self.root:
                    break
                if path.is_symlink():
                    raise RuntimeError(f"Refusing installation through a symlink: {path}")
                if self.root == Path("/") and path.exists():
                    info = path.stat()
                    if info.st_uid != 0 or info.st_mode & 0o022:
                        raise RuntimeError(
                            f"Destination must be root-owned and not writable by others: {path}"
                        )
            if destination.exists() and not destination.is_file():
                raise RuntimeError(f"Expected a regular file: {destination}")
        for destination, original in self.files.items():
            if destination.exists() and MARKER not in destination.read_bytes():
                raise RuntimeError(f"Refusing unmanaged file: {destination}")
            if include_sources:
                if (
                    original.is_symlink()
                    or not original.is_file()
                    or MARKER not in original.read_bytes()
                ):
                    raise RuntimeError(f"Missing or unexpected source file: {original}")

    def preflight(self):
        self.validate_paths()
        if sys.version_info < (3, 11):  # noqa: UP036 - also invoked on older system Pythons
            raise RuntimeError("Python 3.11 or newer is required")
        match = re.match(r"(\d+)\.(\d+)", platform.release())
        if platform.system() != "Linux" or not match or tuple(map(int, match.groups())) < (6, 16):
            raise RuntimeError("Linux 6.16+ with cgroup v2 swappiness=max support is required")
        guard = load_guard(self.source)
        memory = guard.read_memory()
        if not guard.RECLAIM.exists():
            raise RuntimeError("Global cgroup v2 memory.reclaim is unavailable")
        if memory["SwapTotal"] == 0:
            raise RuntimeError("No active swap: configure and activate swap first")
        config = self.config if self.config.exists() else self.source / "config/config.toml"
        settings = guard.load_settings(config, required=True)
        if settings.swap_reserve_mib * guard.MIB >= memory["SwapTotal"]:
            raise RuntimeError(
                "Active swap must exceed swap_reserve_mib; lower the reserve or add swap"
            )
        if self.manage_service:
            self.run("systemd-analyze", "verify", str(self.source / NAME))
            self.run("systemctl", "show", "--property=Version")
        print(json.dumps(guard.status(memory, settings), indent=2))
        return guard

    def install(self):
        guard = self.preflight()
        if self.manage_service:
            guard.reclaim(0)
        before = {}
        payloads = {
            destination: original.read_bytes() for destination, original in self.files.items()
        }
        if not self.config.exists():
            payloads[self.config] = (self.source / "config/config.toml").read_bytes()
        for path in payloads:
            before[path] = (
                (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
            )
        backups = self.root / "var/backups"
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = Path(tempfile.mkdtemp(prefix=f"ubuntu-memory-guard-{stamp}-", dir=backups))
        for path, previous in before.items():
            if previous:
                atomic_write(backup / path.name, previous[0], previous[1])
        atomic_write(
            backup / "manifest.json",
            json.dumps(
                {str(path): previous is not None for path, previous in before.items()}, indent=2
            ).encode(),
        )
        was_active = was_enabled = False
        if self.manage_service:
            was_active = self.run("systemctl", "is-active", NAME, check=False).returncode == 0
            was_enabled = self.run("systemctl", "is-enabled", NAME, check=False).returncode == 0
        try:
            for path, content in payloads.items():
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                atomic_write(path, content)
            if self.manage_service:
                self.run("systemctl", "daemon-reload")
                self.run("systemctl", "enable", NAME)
                self.run("systemctl", "restart", NAME)
                self.run("systemctl", "is-active", NAME)
                self.run("systemctl", "is-enabled", NAME)
        except BaseException:
            if self.manage_service:
                self.run("systemctl", "stop", NAME, check=False)
                if not was_enabled:
                    self.run("systemctl", "disable", NAME, check=False)
            for path, previous in before.items():
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, *previous)
            if self.manage_service:
                self.run("systemctl", "daemon-reload", check=False)
                if was_active:
                    self.run("systemctl", "start", NAME, check=False)
            raise
        print(f"Installed. Configuration: {self.config}. Backup: {backup}")

    def remove(self):
        # Removal must work even after swap is disabled or configuration breaks.
        self.validate_paths(include_sources=False)
        if self.manage_service:
            self.run("systemctl", "disable", "--now", NAME)
        for path in self.files:
            path.unlink(missing_ok=True)
        if self.library.exists() and not any(self.library.iterdir()):
            self.library.rmdir()
        if self.manage_service:
            self.run("systemctl", "daemon-reload")
        print(f"Removed service and program. Configuration retained: {self.config}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Read-only preflight; no root needed")
    modes.add_argument(
        "--remove", action="store_true", help="Remove service; preserve configuration"
    )
    args = parser.parse_args()
    if not args.check and os.geteuid() != 0:
        parser.error("Installation/removal needs root: sudo ./install.sh [--remove]")
    installer = Installer()
    if args.remove:
        installer.remove()
    elif args.check:
        installer.preflight()
        print("Read-only checks passed; install with sudo ./install.sh")
    else:
        installer.install()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)

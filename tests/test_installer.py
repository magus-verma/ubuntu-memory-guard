import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import install


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.installer = install.Installer(root=self.root, manage_service=False)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def apply(self):
        with patch.object(self.installer, "preflight"):
            self.installer.install()

    def test_install_from_source_and_file_permissions(self):
        self.apply()
        for destination, original in self.installer.files.items():
            self.assertEqual(destination.read_bytes(), original.read_bytes())
            self.assertEqual(destination.stat().st_mode & 0o777, 0o644)
        self.assertTrue(self.installer.config.is_file())
        self.assertEqual(len(list((self.root / "var/backups").iterdir())), 1)

    def test_upgrade_preserves_configuration_and_backs_up_existing_files(self):
        self.apply()
        config = "trigger_percent = 80\nstop_percent = 75\n"
        self.installer.config.write_text(config)
        old = install.MARKER + b"\nold code\n"
        code = self.installer.library / "memory_guard.py"
        code.write_bytes(old)
        self.apply()
        self.assertEqual(self.installer.config.read_text(), config)
        self.assertTrue(
            any(
                (backup / "memory_guard.py").exists()
                and (backup / "memory_guard.py").read_bytes() == old
                for backup in (self.root / "var/backups").iterdir()
            )
        )

    def test_uninstall_works_without_source_swap_or_config_validation(self):
        self.apply()
        self.installer.config.write_text("invalid = [\n")
        self.installer.source = self.root / "nonexistent-source"
        with patch.object(self.installer, "preflight", side_effect=AssertionError("must not run")):
            self.installer.remove()
        self.assertTrue(self.installer.config.exists())
        self.assertFalse(self.installer.unit.exists())
        self.assertFalse(self.installer.library.exists())

    def test_unmanaged_file_rejected(self):
        self.installer.unit.parent.mkdir(parents=True)
        self.installer.unit.write_text("unmanaged service")
        with self.assertRaisesRegex(RuntimeError, "unmanaged"):
            self.installer.validate_paths()

    def test_symlink_parent_rejected(self):
        (self.root / "usr").mkdir()
        other = self.root / "other"
        other.mkdir()
        (self.root / "usr/local").symlink_to(other)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.installer.validate_paths()

    def test_dangling_destination_symlink_rejected(self):
        self.installer.unit.parent.mkdir(parents=True)
        self.installer.unit.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.installer.validate_paths()

    def test_failed_upgrade_restores_files_and_service_state(self):
        self.apply()
        before = {path: path.read_bytes() for path in self.installer.files}
        self.installer.manage_service = True
        calls = []

        def command(*args, check=True):
            calls.append(args)
            if args[:2] == ("systemctl", "restart"):
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0, "", "")

        with (
            patch.object(self.installer, "preflight") as preflight,
            patch.object(self.installer, "run", side_effect=command),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            self.installer.install()
            preflight.return_value.reclaim.assert_called_once_with(0)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertIn(("systemctl", "start", install.NAME), calls)
        self.assertNotIn(("systemctl", "disable", install.NAME), calls)

    def test_failed_first_install_removes_created_files(self):
        self.installer.manage_service = True

        def command(*args, check=True):
            if args[:2] == ("systemctl", "restart"):
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(
                args, 1 if args[1] in ("is-active", "is-enabled") else 0, "", ""
            )

        with (
            patch.object(self.installer, "preflight"),
            patch.object(self.installer, "run", side_effect=command),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            self.installer.install()
        self.assertFalse(self.installer.unit.exists())
        self.assertFalse(self.installer.config.exists())

    def test_preflight_rejects_older_kernel(self):
        with (
            patch.object(install.platform, "release", return_value="6.8.0"),
            patch.object(install.platform, "system", return_value="Linux"),
            self.assertRaisesRegex(RuntimeError, "6.16"),
        ):
            self.installer.preflight()

    def test_preflight_passes_on_supported_host_with_mocked_memory(self):
        guard = install.load_guard(install.SOURCE)
        memory = {
            "MemTotal": 16_000_000_000,
            "MemAvailable": 8_000_000_000,
            "SwapTotal": 4 * 1024**3,
            "SwapFree": 4 * 1024**3,
        }
        with (
            patch.object(install.platform, "release", return_value="7.2.2"),
            patch.object(install.platform, "system", return_value="Linux"),
            patch.object(install, "load_guard", return_value=guard),
            patch.object(guard, "read_memory", return_value=memory),
            patch.object(guard, "RECLAIM", **{"exists.return_value": True}),
        ):
            self.assertIs(self.installer.preflight(), guard)

import contextlib
import errno
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_guard as guard


def memory(used=50):
    total = 16_000_000_000
    return {
        "MemTotal": total,
        "MemAvailable": total * (100 - used) // 100,
        "SwapTotal": 64 * 1024**3,
        "SwapFree": 60 * 1024**3,
    }


class SettingsTests(unittest.TestCase):
    def test_defaults_and_missing_config(self):
        self.assertEqual(guard.load_settings(Path("/does-not-exist/guard.toml")), guard.Settings())
        with self.assertRaises(FileNotFoundError):
            guard.load_settings(Path("/does-not-exist/guard.toml"), required=True)

    def test_configuration_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text("trigger_percent = 80\nstop_percent = 75\nmax_batch_mib = 32\n")
            settings = guard.load_settings(path)
            self.assertEqual(settings.trigger_percent, 80)
            self.assertEqual(guard.plan(memory(79), False, settings), (False, 0))
            self.assertEqual(guard.plan(memory(81), False, settings)[1], 32 * guard.MIB)
            path.write_text("trigger_precent = 80\n")
            with self.assertRaisesRegex(ValueError, "Unknown"):
                guard.load_settings(path)
            path.write_text("trigger_percent = [\n")
            with self.assertRaises(ValueError):
                guard.load_settings(path)

    def test_invalid_configurations(self):
        cases = [
            {"trigger_percent": 100},
            {"stop_percent": 70},
            {"stop_percent": 0},
            {"trigger_percent": True},
            {"max_batch_mib": 0},
            {"max_batch_mib": 1025},
            {"swap_reserve_mib": -1},
            {"interval_seconds": 0},
            {"interval_seconds": float("nan")},
            {"interval_seconds": True},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                guard.Settings(**case).validate()

    def test_config_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.write_text("trigger_percent = 75\n")
            link = Path(directory) / "link"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                guard.load_settings(link)

    def test_reclaim_is_page_aligned_on_arm64(self):
        with patch.object(guard.os, "sysconf", return_value=65536):
            amount = guard.plan(memory(71), False)[1]
            self.assertEqual(amount % 65536, 0)
            self.assertLessEqual(amount, guard.MAX_BATCH_BYTES)

    def test_dangling_config_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "config.toml"
            link.symlink_to(Path(directory) / "missing")
            with self.assertRaisesRegex(ValueError, "symlink"):
                guard.load_settings(link)

    def test_hysteresis_over_multiple_samples(self):
        active = False
        result = []
        for used in [70, 71, 69, 67, 69, 72]:
            active, _ = guard.plan(memory(used), active)
            result.append(active)
        self.assertEqual(result, [False, True, True, False, False, True])

    def test_kernel_complete_short_write_and_permission_error(self):
        with (
            patch.object(guard.os, "open", return_value=42),
            patch.object(guard.os, "close"),
            patch.object(guard.os, "write", side_effect=lambda fd, payload: len(payload)),
        ):
            self.assertEqual(guard.reclaim(1048576), "complete")
        with (
            patch.object(guard.os, "open", return_value=42),
            patch.object(guard.os, "close"),
            patch.object(guard.os, "write", return_value=2),
        ):
            with self.assertRaisesRegex(RuntimeError, "Short write"):
                guard.reclaim(1048576)
        with patch.object(guard.os, "open", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                guard.reclaim(1048576)

    def test_invalid_memory_values(self):
        for content in [
            "MemTotal: 0 kB\nMemAvailable: 0 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
            "MemTotal: 100 kB\nMemAvailable: 101 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n",
            "MemTotal: 100 kB\nMemAvailable: 20 kB\nSwapTotal: 10 kB\nSwapFree: 11 kB\n",
        ]:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "meminfo"
                path.write_text(content)
                with self.assertRaises(RuntimeError):
                    guard.read_memory(path)


class CliTests(unittest.TestCase):
    def test_status_never_reclaims_or_requires_root(self):
        with (
            patch("sys.argv", ["memory_guard.py", "--status"]),
            patch.object(guard, "load_settings", return_value=guard.Settings()),
            patch.object(guard, "read_memory", return_value=memory(90)),
            patch.object(guard, "reclaim") as reclaim,
            patch.object(guard.os, "geteuid", return_value=1000),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            guard.main()
            reclaim.assert_not_called()
            self.assertIn('"would_start_reclaim": true', output.getvalue())

    def test_non_root_once_is_rejected(self):
        with (
            patch("sys.argv", ["memory_guard.py", "--once"]),
            patch.object(guard, "load_settings", return_value=guard.Settings()),
            patch.object(guard.os, "geteuid", return_value=1000),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            guard.main()

    def test_once_below_threshold_only_probes_zero_bytes(self):
        with (
            patch("sys.argv", ["memory_guard.py", "--once"]),
            patch.object(guard, "load_settings", return_value=guard.Settings()),
            patch.object(guard, "read_memory", return_value=memory(50)),
            patch.object(guard, "reclaim") as reclaim,
            patch.object(guard.os, "geteuid", return_value=0),
            patch.object(guard, "RECLAIM", **{"exists.return_value": True}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            guard.main()
            reclaim.assert_called_once_with(0)

    def test_unsupported_kernel_fails_before_reclaim_loop(self):
        with (
            patch("sys.argv", ["memory_guard.py", "--once"]),
            patch.object(guard, "load_settings", return_value=guard.Settings()),
            patch.object(guard, "read_memory", return_value=memory(90)),
            patch.object(guard, "reclaim", side_effect=OSError(errno.EINVAL, "unsupported")),
            patch.object(guard.os, "geteuid", return_value=0),
            patch.object(guard, "RECLAIM", **{"exists.return_value": True}),
            self.assertRaisesRegex(RuntimeError, "6.16"),
        ):
            guard.main()

import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_guard as guard


def sample(used=50, swap_free=10 * 1024**3):
    total = 16 * 1000**3
    return {
        "MemTotal": total,
        "MemAvailable": total * (100 - used) // 100,
        "SwapTotal": 64 * 1024**3,
        "SwapFree": swap_free,
    }


class GuardTests(unittest.TestCase):
    def test_trigger_and_hysteresis(self):
        self.assertEqual(guard.plan(sample(70), False), (False, 0))
        self.assertEqual(guard.plan(sample(71), False), (True, guard.MAX_BATCH_BYTES))
        self.assertGreater(guard.plan(sample(69), True)[1], 0)
        self.assertEqual(guard.plan(sample(68), True), (False, 0))
        self.assertEqual(guard.plan(sample(69), False), (False, 0))

    def test_swap_reserve_and_request_cap(self):
        self.assertEqual(guard.plan(sample(99), False)[1], guard.MAX_BATCH_BYTES)
        self.assertEqual(guard.plan(sample(95, guard.SWAP_RESERVE_BYTES), False)[1], 0)
        self.assertEqual(guard.plan(sample(95, 0), False)[1], 0)
        self.assertEqual(
            guard.plan(sample(95, guard.SWAP_RESERVE_BYTES + guard.MIB), False)[1], guard.MIB
        )

    def test_uses_available_memory_instead_of_free_or_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meminfo"
            path.write_text(
                "MemTotal: 100000 kB\nMemAvailable: 40000 kB\n"
                "MemFree: 1000 kB\nCached: 60000 kB\n"
                "SwapTotal: 200000 kB\nSwapFree: 200000 kB\n"
            )
            memory = guard.read_memory(path)
            self.assertEqual(guard.used_percent(memory), 60)
            self.assertEqual(guard.plan(memory, False), (False, 0))
            path.write_text("MemTotal: 100000 kB\n")
            with self.assertRaises(RuntimeError):
                guard.read_memory(path)

    def test_kernel_request_and_partial_reclaim(self):
        with (
            patch.object(guard.os, "open", return_value=42),
            patch.object(guard.os, "close") as close,
            patch.object(guard.os, "write", side_effect=OSError(errno.EAGAIN, "partial")) as write,
        ):
            self.assertEqual(guard.reclaim(guard.MIB), "partial")
            write.assert_called_once_with(42, b"1048576 swappiness=max")
            close.assert_called_once_with(42)
        with (
            patch.object(guard.os, "open", return_value=42),
            patch.object(guard.os, "close"),
            patch.object(guard.os, "write", side_effect=OSError(errno.EINVAL, "unsupported")),
        ):
            with self.assertRaises(OSError):
                guard.reclaim(guard.MIB)


if __name__ == "__main__":
    unittest.main()

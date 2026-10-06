#!/usr/bin/python3
"""Ask Linux to swap cold anonymous pages when usable RAM falls below 30%."""

import argparse
import errno
import json
import logging
import os
import signal
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

# ubuntu-memory-guard managed file
MIB = 1024**2
VERSION = "0.1.0"
TRIGGER_PERCENT = 70
STOP_PERCENT = 68
INTERVAL_SECONDS = 2
MAX_BATCH_BYTES = 256 * MIB
SWAP_RESERVE_BYTES = 1024 * MIB
MEMINFO = Path("/proc/meminfo")
RECLAIM = Path("/sys/fs/cgroup/memory.reclaim")
CONFIG = Path("/etc/ubuntu-memory-guard/config.toml")


@dataclass(frozen=True)
class Settings:
    trigger_percent: int = TRIGGER_PERCENT
    stop_percent: int = STOP_PERCENT
    interval_seconds: float = INTERVAL_SECONDS
    max_batch_mib: int = MAX_BATCH_BYTES // MIB
    swap_reserve_mib: int = SWAP_RESERVE_BYTES // MIB

    def validate(self):
        for key in ("trigger_percent", "stop_percent", "max_batch_mib", "swap_reserve_mib"):
            if type(getattr(self, key)) is not int:
                raise ValueError(f"{key} must be an integer")
        if not 0 < self.stop_percent < self.trigger_percent < 100:
            raise ValueError("Require 0 < stop_percent < trigger_percent < 100")
        if (
            type(self.interval_seconds) not in (int, float)
            or not 0.5 <= self.interval_seconds <= 60
        ):
            raise ValueError("interval_seconds must be between 0.5 and 60")
        if not 1 <= self.max_batch_mib <= 1024:
            raise ValueError("max_batch_mib must be between 1 and 1024")
        if not 16 <= self.swap_reserve_mib <= 1048576:
            raise ValueError("swap_reserve_mib must be between 16 and 1048576")
        return self


DEFAULT_SETTINGS = Settings()


def load_settings(path=CONFIG, required=False):
    if path.is_symlink():
        raise ValueError(f"Configuration must not be a symlink: {path}")
    if not path.exists() and not required:
        return DEFAULT_SETTINGS
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    unknown = data.keys() - asdict(Settings()).keys()
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    return Settings(**data).validate()


def read_memory(path=MEMINFO):
    values = {}
    for line in path.read_text().splitlines():
        key, rest = line.split(":", 1)
        fields = rest.split()
        if fields:
            values[key] = int(fields[0]) * 1024
    for key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
        if key not in values:
            raise RuntimeError(f"{key} is missing from {path}")
    if not 0 <= values["MemAvailable"] <= values["MemTotal"] or values["MemTotal"] <= 0:
        raise RuntimeError("Invalid total or available memory in meminfo")
    if not 0 <= values["SwapFree"] <= values["SwapTotal"]:
        raise RuntimeError("Invalid swap counters in meminfo")
    return values


def used_percent(memory):
    # MemAvailable includes memory Linux can reuse without swapping. Counting
    # all cache as used would unnecessarily swap applications on a healthy PC.
    return 100 * (1 - memory["MemAvailable"] / memory["MemTotal"])


def plan(memory, active, settings=DEFAULT_SETTINGS):
    available = memory["MemAvailable"]
    total = memory["MemTotal"]
    if available * 100 >= total * (100 - settings.stop_percent):
        active = False
    elif available * 100 < total * (100 - settings.trigger_percent):
        active = True
    amount = 0
    if active:
        goal = memory["MemTotal"] * (100 - settings.stop_percent) // 100
        deficit = max(0, goal - memory["MemAvailable"])
        swap_room = max(0, memory["SwapFree"] - settings.swap_reserve_mib * MIB)
        amount = min(settings.max_batch_mib * MIB, deficit, swap_room)
        amount = amount // os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PAGE_SIZE")
    return active, amount


def reclaim(amount, path=RECLAIM):
    # max exclusively selects anonymous memory, so the request asks for swap
    # instead of throwing out the filesystem cache. Linux selects the pages.
    payload = f"{amount} swappiness=max".encode("ascii")
    fd = os.open(path, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        try:
            count = os.write(fd, payload)
        except OSError as error:
            # EAGAIN means some or none of the requested memory was reclaimed.
            # The next sample determines whether another request is needed.
            if error.errno == errno.EAGAIN:
                return "partial"
            raise
        if count != len(payload):
            raise RuntimeError("Short write to memory.reclaim")
    finally:
        os.close(fd)
    return "complete"


def status(memory, settings=DEFAULT_SETTINGS):
    active, amount = plan(memory, False, settings)
    return {
        "ram_total_gib": round(memory["MemTotal"] / 1024**3, 2),
        "ram_used_percent": round(used_percent(memory), 2),
        "ram_available_gib": round(memory["MemAvailable"] / 1024**3, 2),
        "swap_total_gib": round(memory["SwapTotal"] / 1024**3, 2),
        "swap_used_gib": round((memory["SwapTotal"] - memory["SwapFree"]) / 1024**3, 3),
        "version": VERSION,
        "settings": asdict(settings),
        "trigger_percent": settings.trigger_percent,
        "stop_percent": settings.stop_percent,
        "would_start_reclaim": active,
        "next_request_mib": round(amount / MIB, 2),
        "reclaim_interface_present": RECLAIM.exists(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Read-only diagnostic")
    parser.add_argument("--once", action="store_true", help="One threshold-controlled request")
    parser.add_argument("--config", type=Path, help="Use an explicit TOML configuration")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    settings = load_settings(args.config or CONFIG, required=args.config is not None)
    if args.status:
        print(json.dumps(status(read_memory(), settings), indent=2))
        return
    if os.geteuid() != 0:
        parser.error("The daemon needs administrator privileges; --status does not.")
    if not RECLAIM.exists():
        raise RuntimeError("This service requires cgroup v2 memory.reclaim")
    if read_memory()["SwapTotal"] == 0:
        raise RuntimeError("No active swap; activate swap before starting this service")
    # Zero bytes checks the parser and write access without evicting any pages.
    try:
        reclaim(0)
    except OSError as error:
        if error.errno == errno.EINVAL:
            raise RuntimeError(
                "Kernel lacks swappiness=max support; Linux 6.16+ is required"
            ) from error
        raise

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.info(
        "Started v%s: RAM >%d%% triggers anonymous-page reclaim; stops at %d%%; "
        "maximum %d MiB every %s seconds",
        VERSION,
        settings.trigger_percent,
        settings.stop_percent,
        settings.max_batch_mib,
        settings.interval_seconds,
    )
    active = False
    last_report = 0
    last_warning = 0
    while running:
        memory = read_memory()
        was_active = active
        active, amount = plan(memory, active, settings)
        used = used_percent(memory)
        if active != was_active:
            logging.info(
                "%s proactive swapping; RAM used %.1f%%, swap used %.2f GiB",
                "Starting" if active else "Stopping",
                used,
                (memory["SwapTotal"] - memory["SwapFree"]) / 1024**3,
            )
        now = time.monotonic()
        if (
            active
            and not amount
            and memory["SwapFree"] <= settings.swap_reserve_mib * MIB
            and now - last_warning >= 60
        ):
            logging.warning(
                "RAM %.1f%%: no usable swap room beyond the %d MiB reserve; "
                "existing kernel/OOM safeguards remain responsible",
                used,
                settings.swap_reserve_mib,
            )
            last_warning = now
        if amount:
            result = reclaim(amount)
            if now - last_report >= 30:
                after = read_memory()
                logging.info(
                    "Reclaim %s: requested %.0f MiB; RAM %.1f%% -> %.1f%%; swap used %.2f GiB",
                    result,
                    amount / MIB,
                    used,
                    used_percent(after),
                    (after["SwapTotal"] - after["SwapFree"]) / 1024**3,
                )
                last_report = now
        if args.once:
            print(json.dumps(status(read_memory(), settings), indent=2))
            return
        time.sleep(settings.interval_seconds)
    logging.info("Stopped")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)

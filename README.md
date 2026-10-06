# Ubuntu Memory Guard

[![CI](https://github.com/magus-verma/ubuntu-memory-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/magus-verma/ubuntu-memory-guard/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](docs/compatibility.md)

**Start swapping earlier, before RAM pressure makes your Linux desktop unresponsive.**

Ubuntu Memory Guard is a small systemd service that asks Linux to move eligible
anonymous memory into your existing swap when RAM usage exceeds **70%**. It stops
requesting reclaim at **68%**. Thresholds, timing, batch size, and the swap reserve
are configurable. The daemon uses Python's standard library only.

> Initial release, v0.1.0. The core policy was verified on one Ubuntu ARM64 laptop.
> This reduces memory pressure; it does not guarantee against every crash.

## Quick start

Requires **Linux 6.16+**, **Python 3.11+**, **systemd**, **cgroup v2**, and active
swap greater than the configured reserve (1 GiB by default). Older Ubuntu kernels
are unsupported. See [compatibility](docs/compatibility.md) before installation.

```bash
git clone https://github.com/magus-verma/ubuntu-memory-guard.git
cd ubuntu-memory-guard
./install.sh --check
sudo ./install.sh
systemctl status ubuntu-memory-guard.service --no-pager
```

Review the source before running the privileged installer. For a versioned
checkout, run `git checkout v0.1.0` before the checks. Installation enables the
service at boot and starts it immediately. It preserves existing swap files,
`fstab`, kernel settings, and OOM safeguards. It does not create swap or change
boot configuration. The installer backs up replaced files and rolls them back
if a service command fails.

## What it does

| Setting | Default | Purpose |
| --- | --- | --- |
| `trigger_percent` | 70 | Start requesting reclaim above this RAM usage |
| `stop_percent` | 68 | Stop requests at or below this RAM usage |
| `interval_seconds` | 2 | Delay between checks, after each request completes |
| `max_batch_mib` | 256 | Maximum amount requested per check |
| `swap_reserve_mib` | 1024 | Leave this much swap available |

RAM usage is `100 × (1 − MemAvailable / MemTotal)`. Reusable filesystem cache is
accounted for through `MemAvailable`; a monitor using another formula may show
a different percentage. The 70%/68% gap prevents rapid toggling near the threshold.

The service writes `SIZE swappiness=max` to the root cgroup's `memory.reclaim`.
Linux selects eligible anonymous pages. Requests can reclaim more or less than
requested. The percentage is a policy target, not a hard RAM cap, and `swappiness`
itself is not a RAM percentage. Read the [design](docs/design.md) for details.

## Configure

Edit `/etc/ubuntu-memory-guard/config.toml`, then restart the service:

```bash
sudoedit /etc/ubuntu-memory-guard/config.toml
sudo systemctl restart ubuntu-memory-guard.service
```

```toml
trigger_percent = 70
stop_percent = 68
interval_seconds = 2
max_batch_mib = 256
swap_reserve_mib = 1024
```

Invalid or unknown settings fail with a clear error. Reinstallation preserves
existing configuration. [Configuration reference](docs/configuration.md).

## Check operation

```bash
python3 /usr/local/lib/ubuntu-memory-guard/memory_guard.py --status
journalctl -u ubuntu-memory-guard.service -n 30 --no-pager
free -h
vmstat 2
```

`--status` is read-only and works without root. It reports whether a fresh
threshold check would start reclaim; it does not query the running daemon's
hysteresis state. Journal messages show when actual requests start and stop.

An initial ARM64 observation showed RAM usage fall from about **86% to 67.5%**
while swap usage increased from about **1 GiB to 3.3 GiB**. This is a single
observation, not a benchmark or a guarantee. [Validation scope](docs/validation.md).

## Disable or remove

```bash
sudo systemctl disable --now ubuntu-memory-guard.service
```

From the repository checkout:

```bash
sudo ./install.sh --remove
```

Removal keeps configuration, backups, and all existing swap. It works even when
swap has been disabled or configuration is invalid. [Troubleshooting and
rollback](docs/troubleshooting.md).

## Limits and alternatives

Actively used pages can be swapped back immediately, which can slow applications.
Locked memory and some kernel/GPU allocations cannot be swapped. A fast-growing
workload can outrun the service, and sustained demand can exhaust both RAM and
swap. Existing kernel and systemd OOM handling remain relevant.

| Tool | Primary role |
| --- | --- |
| Ubuntu Memory Guard | Request early anonymous-page reclaim at a RAM threshold |
| [systemd-oomd](https://www.freedesktop.org/software/systemd/man/latest/systemd-oomd.service.html) | Kill selected cgroups under sustained memory pressure |
| [earlyoom](https://github.com/rfjakob/earlyoom) | Terminate selected processes when memory and swap run low |
| [nohang](https://github.com/hakavlad/nohang) | Configurable low-memory handling and recovery |
| [zram / zswap](https://docs.kernel.org/admin-guide/mm/zswap.html) | Compress memory used for swap; neither is configured here |

This project does not replace an OOM handler, fix memory leaks, or provide a hard
resource limit. Containers and restricted cgroup namespaces are unsupported.

## Development and community

```bash
make test
python3 -m pip install ruff==0.16.9  # optional development tool
make lint
```

CI runs behavioral tests on Python 3.11–3.14, lint, shell syntax, and systemd unit
validation. Tests simulate reclaim and installation in temporary directories;
CI does not force swap on its shared runner. Runtime has no pip dependencies.

- [Contributing](CONTRIBUTING.md) · [Code of conduct](CODE_OF_CONDUCT.md)
- [Security reporting](SECURITY.md) · [Support](SUPPORT.md)
- [Changelog](CHANGELOG.md) · [Roadmap](docs/roadmap.md)
- [Repository conventions and references](docs/repository-design.md)

MIT licensed. No telemetry or daemon network access.

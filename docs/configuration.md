# Configuration

The daemon loads `/etc/ubuntu-memory-guard/config.toml` once at startup. If the
default file is missing, built-in defaults apply. An explicitly supplied
`--config PATH` must exist. Symbolic links, invalid TOML, unknown keys, and invalid
values are rejected. Restart after editing. Upgrades preserve existing settings.

| Key | Range / constraint | Default |
| --- | --- | --- |
| `trigger_percent` | Integer; greater than stop, less than 100 | 70 |
| `stop_percent` | Integer; greater than 0, less than trigger | 68 |
| `interval_seconds` | Number between 0.5 and 60 | 2 |
| `max_batch_mib` | Integer between 1 and 1024 | 256 |
| `swap_reserve_mib` | Integer between 16 and 1048576; must be below active swap at installation | 1024 |

Higher trigger percentages preserve more RAM residency but leave less headroom.
Smaller batches or longer intervals reduce reclaim activity but react more slowly.
A very low threshold can increase swap-in traffic and application latency.
Start with defaults and inspect the journal, `vmstat 2`, and `/proc/pressure/memory`
under your normal workload.

Diagnostic commands:

```bash
python3 memory_guard.py --version
python3 memory_guard.py --status
python3 memory_guard.py --config config/config.toml --status
```

`--once` requires root and makes at most one threshold-controlled request after
a zero-byte feature probe. Avoid running it alongside the daemon when evaluating
request rate. Requests are page-aligned, including on 64 KiB page systems.

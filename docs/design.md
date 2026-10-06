# Design

At each sample the guard computes used RAM from `MemAvailable` and `MemTotal`.
It begins requesting reclaim above the trigger, keeps requesting in the gap,
and stops at or below the lower threshold. This hysteresis avoids repeated
start/stop transitions from small fluctuations.

A request is the minimum of the bytes needed to reach the stop target, the
configured batch, and free swap beyond the reserve. It is rounded down to the
host page size. After the synchronous kernel request completes, the daemon waits
for the configured interval. This bounds request size, not exact device throughput
or syscall duration. The kernel can over- or under-reclaim.

Requests go to the root cgroup so eligible memory across the host is considered.
`swappiness=max` selects anonymous memory; Linux decides which pages to reclaim.
`EAGAIN` means the requested amount was not fully reclaimed and is retried only
after the next sample. Other errors terminate the daemon and are visible in the
journal; systemd performs limited restarts. A zero-byte startup probe verifies
support without intentionally reclaiming pages.

The daemon does not set a hard memory limit, modify global swappiness, clear the
page cache, disable swap, or kill processes. Systemd and kernel OOM handling are
separate safeguards. The service protects its own small memory footprint from
OOM selection and limits its total memory to 96 MiB.

The installer derives its source directory from the checkout, rejects destination
symlinks/unmanaged code and unit files, stages atomic replacements, preserves
configuration, and records backups under `/var/backups/ubuntu-memory-guard-*`.
Service-command failure restores prior files and attempts to restore the previous
service state. Rollback is best-effort if the system manager or storage itself fails.
Removal has no dependency on current swap availability or valid configuration.

Sources: [kernel cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html),
[kernel VM settings](https://docs.kernel.org/admin-guide/sysctl/vm.html), and
[systemd execution restrictions](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).

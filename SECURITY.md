# Security

The latest v0.1.x release is the supported security-fix line. This is a new
project with limited field validation and no independent security audit.

The service runs as root to write the kernel reclaim interface. Its systemd unit
limits memory, removes capabilities, restricts writable paths, and disables
privilege escalation. The installer rejects symlinked destinations and unmanaged
program/unit files, uses atomic writes, and backs up replacements.

Do not post exploit details or sensitive logs in a public issue. Use
[GitHub private vulnerability reporting](https://github.com/magus-verma/ubuntu-memory-guard/security/advisories/new).
Include the version, affected paths, reproducible steps, and impact. The
maintainer will investigate and coordinate disclosure; no response-time SLA is
promised.

The daemon does not send telemetry or open network connections. Keep swap
security appropriate to your host: sensitive memory may be written to swap.
Reports should redact personal names, paths, and unrelated journal content.

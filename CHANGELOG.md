# Changelog

## 0.1.0 — 2026-10-07

Initial public release:

- Proactive anonymous-page reclaim above 70% RAM usage with a 68% stop threshold.
- Bounded requests, configurable polling, and a swap reserve.
- TOML settings with validation, read-only JSON status, and version output.
- Systemd service with automatic startup and resource restrictions.
- Portable installation, upgrade backups, rollback, and independent removal.
- Behavioral tests, Python 3.11–3.14 CI, pinned actions, lint, and community guidance.

The core policy was observed on one Ubuntu 26.04.1 ARM64 laptop with a custom
7.2.2 kernel. Broader hardware and distribution validation is outstanding.

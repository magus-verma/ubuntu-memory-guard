# Contributing

Open an issue describing the problem and proposed behavior before a substantial
change. Keep contributions focused on proactive reclaim, diagnostics, safe
installation, or documented compatibility.

Use Python 3.11 or newer. The daemon must retain a standard-library-only runtime.

```bash
make test
python3 -m pip install ruff==0.16.9
make lint
```

Add behavioral tests for changes to thresholds, reserves, configuration parsing,
kernel requests, and installer rollback. Unit tests must not write to real
cgroups, modify system files, allocate huge amounts of memory, or kill processes.
Installer tests use an isolated temporary filesystem tree.

For optional live validation, use a disposable VM or a carefully monitored host
with an existing working swap setup. Record kernel version, architecture, RAM,
swap, before/after usage, memory pressure, and any unexpected stalls. Avoid
exhausting a working machine. CI results alone cannot establish hardware support.

Submit pull requests against `main`, describe the user-visible behavior, and
include validation evidence. Changes to default policy or supported versions
need documentation and changelog entries. Contributions are accepted under MIT.

Review and understand any generated contribution before submitting it. Describe
important design decisions and do not claim measurements you did not perform.

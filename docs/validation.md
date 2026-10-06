# Validation

The initial core policy was exercised on Ubuntu 26.04.1 ARM64, kernel
`7.2.2-jg-0-qcom-x1e`, systemd 259, about 15.06 GiB usable RAM, and 64 GiB swap.
During one normal-workload observation on 7 October 2026:

| Measurement | Before | After |
| --- | --- | --- |
| Used RAM from MemAvailable | about 85.8% | about 67.5% |
| Swap used | about 1.03 GiB | about 3.31 GiB |
| Guard state | Reclaim started | Requests stopped at 67.9% |
| Service restarts | 0 | 0 |
| Current-boot kernel OOM kills | 0 | 0 |

Short subsequent samples reported memory full-pressure avg10 of 0 and no sustained
I/O wait. These observations support the core reclaim path only. They are not a
controlled benchmark, a long-duration soak test, or proof that all freezes are fixed.

The public release adds portable installation, configuration, and startup checks
to that policy. Tests cover threshold boundaries/hysteresis, reserve and batch
bounds, page alignment, malformed settings, status without mutation, kernel
errors, installation/upgrade/removal, symlink rejection, backups, and rollback.
They do not write to real cgroups or perform destructive memory stress.

CI checks Python 3.11–3.14, lint/format, shell syntax, and unit-file validity.
Its shared runner kernel need not support live reclaim. CI success should not be
interpreted as live x86_64/ARM64 support validation.

Outstanding: controlled comparison against kernel defaults, long-running hot
workloads, slow swap devices, zram/zswap combinations, other kernels, and additional
distributions/hardware. Publish reproducible evidence before expanding claims.

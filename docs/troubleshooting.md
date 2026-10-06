# Troubleshooting and rollback

## Preflight rejects the kernel

Anonymous-only `swappiness=max` requires Linux 6.16+. Older kernels may expose
`memory.reclaim` without supporting it. The installer intentionally refuses that
configuration. It does not replace your kernel.

## No active swap or swap below the reserve

Inspect `swapon --show` and `free -h`. Configure swap through your distribution's
supported procedure, or lower the guard's reserve while keeping adequate headroom.
The guard does not allocate, format, enable, disable, or delete swap devices.

## Service failed

```bash
systemctl status ubuntu-memory-guard.service --no-pager
journalctl -u ubuntu-memory-guard.service -n 50 --no-pager
```

Correct the reported configuration or capability error. If the restart limit was
reached, then run:

```bash
sudo systemctl reset-failed ubuntu-memory-guard.service
sudo systemctl restart ubuntu-memory-guard.service
```

## Swap rises and applications slow down

Some pages may be active and immediately read back. Stop the service and compare
normal workload behavior. Consider a higher trigger or smaller batches. The guard
cannot make an oversized working set fit in RAM without a performance tradeoff.

```bash
sudo systemctl disable --now ubuntu-memory-guard.service
```

This stops proactive requests; existing swap stays active. Do not use `swapoff`
as a rollback when RAM is already tight.

## Remove

From the checkout, `sudo ./install.sh --remove` removes the installed program and
unit while retaining configuration and backups. Manual equivalent:

```bash
sudo systemctl disable --now ubuntu-memory-guard.service
sudo rm /etc/systemd/system/ubuntu-memory-guard.service
sudo rm /usr/local/lib/ubuntu-memory-guard/memory_guard.py
sudo rmdir /usr/local/lib/ubuntu-memory-guard
sudo systemctl daemon-reload
```

## Upgrade rollback

A failed service command triggers file rollback automatically. To revert a
successful upgrade, inspect the printed `/var/backups/ubuntu-memory-guard-*`
manifest, stop the service, restore only files listed as previously existing,
and reload systemd. For a clean reinstall, remove the guard and install the prior
release checkout. Existing configuration remains in place; check it against the
prior version before starting.

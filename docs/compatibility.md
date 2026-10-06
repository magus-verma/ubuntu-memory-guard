# Compatibility

Required capabilities:

- Linux 6.16 or newer with `CONFIG_SWAP`, cgroup v2 memory accounting, and a
  writable root `/sys/fs/cgroup/memory.reclaim` supporting `swappiness=max`.
- Python 3.11 or newer for the standard-library TOML parser.
- A working systemd system manager and active swap exceeding the configured
  reserve (1 GiB by default).
- Root privileges to install, remove, or execute reclaim. Status is unprivileged.

`swappiness=max` is documented in the
[Linux 6.16 cgroup interface](https://www.kernel.org/doc/html/v6.16/admin-guide/cgroup-v2.html).
It exclusively reclaims anonymous memory. Older kernels expose `memory.reclaim`
without necessarily supporting this value; file presence alone is insufficient.
Installation and daemon startup perform a zero-byte request to check the parser
and write access without reclaiming pages. Read-only preflight checks versions,
paths, active swap, configuration, and the systemd unit; it cannot prove write access.

| Environment | Status |
| --- | --- |
| Ubuntu 26.04.1, ARM64, custom 7.2.2 qcom kernel, systemd 259 | Core live policy observed |
| Python 3.11–3.14 | Automated behavioral coverage |
| Other Linux 6.16+ systemd hosts | Intended; live operation unverified |
| Older stock Ubuntu kernels, including Linux 6.8 | Unsupported |
| Non-systemd distributions | Unsupported installer/service |
| Containers, restricted namespaces, cgroup v1 | Unsupported deployment |

The project does not install a different kernel or provision swap. Check your
kernel and swap with `uname -r` and `swapon --show` before proceeding. A version
check is conservative and may reject an older kernel with a custom backport.

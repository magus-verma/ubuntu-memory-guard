#!/bin/bash
# ubuntu-memory-guard managed file
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONPATH PYTHONHOME
task_script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec /usr/bin/python3 -I -B "$task_script_dir/tools/install.py" "$@"

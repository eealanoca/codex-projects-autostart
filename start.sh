#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/codex-projects-autostart"
mkdir -p -- "$STATE_DIR"
chmod 700 -- "$STATE_DIR"
exec "${CODEX_PROJECTS_PYTHON:-python3}" -u "$SCRIPT_DIR/projects.py" watch >>"$STATE_DIR/worker.log" 2>&1

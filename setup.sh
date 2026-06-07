#!/usr/bin/env bash
# Create a self-contained virtual environment for Particle Life.
# Re-running is safe; it just re-syncs dependencies.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  echo "creating .venv ..."
  "$PYTHON" -m venv .venv
fi

echo "installing dependencies ..."
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/pip install -e ".[dev]"

cat <<'EOF'

Done. Activate the environment with:

    source .venv/bin/activate

then try:

    particle-life render --discover --trials 30 --seconds 12 --out life.mp4

Or run without activating:

    .venv/bin/particle-life render --discover --seconds 12 --out life.mp4
EOF

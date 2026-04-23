#!/usr/bin/env bash
set -euo pipefail

SRC="${HERMES_AGENT_SRC:-$HOME/.hermes/hermes-agent}"
DST="$(cd "$(dirname "$0")/.." && pwd)/dm-runtime/vendor/hermes-agent"

if [ ! -f "$SRC/pyproject.toml" ]; then
  echo "Hermes source not found at $SRC"
  exit 1
fi

mkdir -p "$DST"
rsync -a --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  --exclude 'node_modules' \
  --exclude 'ui-tui/node_modules' \
  "$SRC/" "$DST/"

echo "Vendored Hermes source synced to $DST"

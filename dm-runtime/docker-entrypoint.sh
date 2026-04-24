#!/usr/bin/env bash
set -euo pipefail

export HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
DEFAULT_HOME="/opt/d20-hermes-home"

mkdir -p "$HERMES_HOME"

python3 - <<'PY'
import os
import shutil
from pathlib import Path

src = Path(os.environ.get('DEFAULT_HERMES_HOME', '/opt/d20-hermes-home'))
dst = Path(os.environ.get('HERMES_HOME', '/root/.hermes'))

def copy_missing(src_dir: Path, dst_dir: Path):
    if not src_dir.exists():
        return
    for item in src_dir.iterdir():
        target = dst_dir / item.name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            copy_missing(item, target)
        else:
            # Keep secrets/env files that may be provisioned by the deployment,
            # but refresh profile/config/prompt files on every container start so
            # stale named volumes cannot preserve broken DM profile settings.
            if item.name == ".env" and target.exists():
                continue
            shutil.copy2(item, target)

copy_missing(src, dst)
PY

exec "$@"

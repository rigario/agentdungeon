"""Root conftest — ensures dm-runtime/app is importable alongside the rules-server app/.

The DM runtime lives in dm-runtime/app/ but all its test files import from `app.*`
(e.g. app.services.intent_router, app.contract). Without this, pytest's module
caching picks up the top-level `app/` (rules server) and the DM tests fail with
ModuleNotFoundError.

This conftest inserts dm-runtime into sys.path BEFORE any test modules are
collected, so `app` resolves to dm-runtime/app when DM tests need it.
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_DM_RUNTIME = os.path.join(_PROJECT_ROOT, "dm-runtime")

# Insert dm-runtime at position 1 (after the project root that pytest adds)
if _DM_RUNTIME not in sys.path:
    sys.path.insert(0, _DM_RUNTIME)

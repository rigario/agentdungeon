"""D20 Agent RPG — Configuration."""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Database
DB_PATH = os.environ.get("D20_DB_PATH", str(DATA_DIR / "d20.db"))

# Server
HOST = os.environ.get("D20_HOST", "0.0.0.0")
PORT = int(os.environ.get("D20_PORT", "8600"))
BASE_URL = os.environ.get("D20_BASE_URL", f"http://localhost:{PORT}")

# RNG
RNG_SEED_PREFIX = os.environ.get("D20_RNG_SEED", "rigario-d20")

# OAuth — Google
GOOGLE_CLIENT_ID = os.environ.get("D20_GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("D20_GOOGLE_CLIENT_SECRET", "")

# OAuth — X/Twitter
TWITTER_CLIENT_ID = os.environ.get("D20_TWITTER_CLIENT_ID", "")
TWITTER_CLIENT_SECRET = os.environ.get("D20_TWITTER_CLIENT_SECRET", "")

# Dev mode: when no real OAuth credentials, use mock login
OAUTH_DEV_MODE = not (GOOGLE_CLIENT_ID and TWITTER_CLIENT_ID)

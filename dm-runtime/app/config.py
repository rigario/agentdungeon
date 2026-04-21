"""D20 DM Runtime — Configuration."""

import os

# Server
HOST = os.environ.get("DM_HOST", "0.0.0.0")
PORT = int(os.environ.get("DM_PORT", "8610"))

# Upstream rules server
RULES_SERVER_URL = os.environ.get("DM_RULES_SERVER_URL", "http://localhost:8600")

# Redis (session memory)
REDIS_URL = os.environ.get("DM_REDIS_URL", "redis://localhost:6379/0")

# Internal auth
SHARED_SECRET = os.environ.get("DM_SHARED_SECRET", "")

# Fire Pass / Kimi Turbo — LLM narration
FIRE_PASS_API_KEY = os.environ.get("DM_FIRE_PASS_API_KEY", "")
FIRE_PASS_BASE_URL = os.environ.get("DM_FIRE_PASS_BASE_URL", "https://api.firepass.ai/v1")

# Direct Kimi fallback (if not using Fire Pass proxy)
KIMI_API_KEY = os.environ.get("DM_KIMI_API_KEY", "")
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

# Narrator settings
NARRATOR_MODEL = os.environ.get("DM_NARRATOR_MODEL", "kimi-turbo")
NARRATOR_ENABLED = os.environ.get("DM_NARRATOR_ENABLED", "true").lower() == "true"

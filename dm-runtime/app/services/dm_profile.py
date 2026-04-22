"""Hermes DM Profile wrapper — invokes Kimi Turbo via the constrained d20-dm Hermes profile.

This module provides two invocation modes:
1. DIRECT: Call Kimi Turbo API directly (httpx) — used in-process by the FastAPI service.
2. HERMES: Spawn a hermes --profile d20-dm subprocess for narration — used when the DM
   runtime should go through Hermes for logging, session tracking, or model routing.

The DIRECT mode is the default for production (lower latency, no subprocess overhead).
The HERMES mode is available for debugging, session recording, or when model routing
needs to go through Hermes's provider abstraction.

Environment:
  KIMI_API_KEY      — Kimi/Moonshot API key (required for both modes)
  KIMI_BASE_URL     — Base URL (default: https://api.kimi.com/coding/v1)
  DM_HERMES_MODE    — "hermes" to use subprocess mode, "direct" (default) for in-process
  DM_HERMES_PROFILE — Hermes profile name (default: d20-dm)
"""

from __future__ import annotations
import os
import json
import logging
import asyncio
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Configuration
DM_HERMES_MODE = os.environ.get("DM_HERMES_MODE", "direct").lower()
DM_HERMES_PROFILE = os.environ.get("DM_HERMES_PROFILE", "d20-dm")
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "") or os.environ.get("DM_FIRE_PASS_API_KEY", "")
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.kimi.com/coding/v1")
DM_NARRATOR_MODEL = os.environ.get("DM_NARRATOR_MODEL", "kimi-k2.5")
DM_NARRATOR_TIMEOUT = int(os.environ.get("DM_NARRATOR_TIMEOUT", "60"))
DM_NARRATOR_MAX_TOKENS = int(os.environ.get("DM_NARRATOR_MAX_TOKENS", "1200"))

# Shared HTTP client for connection pooling (set by main.py lifespan)
_shared_client: Optional[httpx.AsyncClient] = None


def set_http_client(client: httpx.AsyncClient) -> None:
    """Set the shared HTTP client for Kimi API calls (connection pooling)."""
    global _shared_client
    _shared_client = client


async def narrate_via_direct(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.8,
) -> Optional[dict]:
    """Call Kimi Turbo directly via HTTP (in-process, lowest latency).

    Uses a shared AsyncClient with connection pooling when available
    (set by main.py lifespan), with per-request timeout.
    """
    if not KIMI_API_KEY:
        logger.warning("No KIMI_API_KEY set — cannot call Kimi Turbo directly")
        return None

    try:
        # Use shared client for connection pooling, or create temporary client
        if _shared_client is not None:
            client = _shared_client
            # Use client directly (caller manages lifecycle) with per-request timeout
            # to prevent hanging when Kimi API is slow (fast-fail → passthrough fallback)
            try:
                response = await client.post(
                    f"{KIMI_BASE_URL}/chat/completions",
                    json={
                        "model": DM_NARRATOR_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": DM_NARRATOR_MAX_TOKENS,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=8.0,   # Fail fast → structured passthrough fallback (8s SLA)
                )
            except httpx.TimeoutException as e:
                logger.warning(f"Kimi API timeout after 8s: {e}")
                return None
        else:
            # Fallback: create temporary client (no pooling) with fast timeout
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    f"{KIMI_BASE_URL}/chat/completions",
                    json={
                        "model": DM_NARRATOR_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": DM_NARRATOR_MAX_TOKENS,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=15.0,
                )

        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"].get("content", "")
        # Kimi coding API may put output in reasoning_content when thinking
        if not content or not content.strip():
            content = data["choices"][0]["message"].get("reasoning_content", "")
        if not content or not content.strip():
            logger.warning("Kimi returned empty content and reasoning_content")
            return None
        return json.loads(content)

    except json.JSONDecodeError as e:
        logger.warning(f"Kimi returned invalid JSON: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"Kimi API error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Kimi direct call error: {e}")
        return None


async def narrate_via_hermes(
    system_prompt: str,
    user_prompt: str,
) -> Optional[dict]:
    """Spawn a hermes subprocess with the d20-dm profile for narration.

    This mode goes through Hermes's full provider abstraction, session tracking,
    and model routing. Higher latency but provides logging and debugging.
    """
    try:
        # Build the prompt as a single message for hermes chat
        combined_prompt = f"""You are the Dungeon Master. Respond with ONLY valid JSON.

SYSTEM INSTRUCTIONS:
{system_prompt}

SCENE DATA:
{user_prompt}

Respond with JSON containing: scene, npc_lines, tone, choices_summary"""

        # Use hermes CLI in one-shot mode
        cmd = [
            "hermes", "chat",
            "--profile", DM_HERMES_PROFILE,
            "--no-stream",
            combined_prompt,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "HERMES_PROFILE": DM_HERMES_PROFILE},
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=DM_NARRATOR_TIMEOUT + 10,
        )

        if proc.returncode != 0:
            logger.warning(f"Hermes DM exited with code {proc.returncode}: {stderr.decode()[:200]}")
            return None

        output = stdout.decode().strip()
        # Try to parse JSON from output
        # Hermes may wrap output in markdown or add commentary — find JSON block
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            # Try to extract JSON from the output
            import re
            json_match = re.search(r'\{[^{}]*"scene"[^{}]*\}', output, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            logger.warning(f"Hermes DM output not valid JSON: {output[:200]}")
            return None

    except asyncio.TimeoutError:
        logger.warning("Hermes DM narration timed out")
        return None
    except FileNotFoundError:
        logger.warning("hermes CLI not found — falling back to direct mode")
        return None
    except Exception as e:
        logger.warning(f"Hermes DM call error: {e}")
        return None


async def narrate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.8,
) -> Optional[dict]:
    """Generate DM narration. Uses configured mode (direct or hermes).

    Args:
        system_prompt: DM system prompt with authority boundaries
        user_prompt: Scene context from server data
        temperature: LLM temperature (direct mode only)

    Returns:
        dict with keys: scene, npc_lines, tone, choices_summary
        None if narration unavailable (caller should use passthrough)
    """
    if DM_HERMES_MODE == "hermes":
        result = await narrate_via_hermes(system_prompt, user_prompt)
        if result:
            return result
        # Fall through to direct if hermes fails
        logger.info("Hermes mode failed, falling back to direct")

    return await narrate_via_direct(system_prompt, user_prompt, temperature)


def get_status() -> dict:
    """Return current DM profile configuration status."""
    return {
        "mode": DM_HERMES_MODE,
        "hermes_profile": DM_HERMES_PROFILE,
        "api_key_set": bool(KIMI_API_KEY),
        "base_url": KIMI_BASE_URL,
        "model": DM_NARRATOR_MODEL,
        "timeout": DM_NARRATOR_TIMEOUT,
        "max_tokens": DM_NARRATOR_MAX_TOKENS,
    }

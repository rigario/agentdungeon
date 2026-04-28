"""Hermes DM profile wrapper for D20 DM narration.

The DM runtime can narrate via either:
1. HERMES mode — `hermes chat -q -Q --profile d20-dm`
2. DIRECT mode — raw HTTP call to the configured Kimi endpoint

Hermes mode is the preferred production path. Direct mode remains as a fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import KIMI_BASE_URL as DEFAULT_KIMI_BASE_URL

logger = logging.getLogger(__name__)

DM_HERMES_MODE = os.environ.get("DM_HERMES_MODE", "hermes").lower()
DM_HERMES_PROFILE = os.environ.get("DM_HERMES_PROFILE", "d20-dm")
HERMES_HOME = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
KIMI_API_KEY = (
    os.environ.get("KIMI_API_KEY", "")
    or os.environ.get("DM_FIRE_PASS_API_KEY", "")
    or os.environ.get("FIRE_PASS_API_KEY", "")
)
KIMI_BASE_URL = os.environ.get("KIMI_BASE_URL", DEFAULT_KIMI_BASE_URL)
DM_NARRATOR_MODEL = os.environ.get("DM_NARRATOR_MODEL", "kimi-for-coding")
DM_NARRATOR_TIMEOUT = int(os.environ.get("DM_NARRATOR_TIMEOUT", "110"))
DM_NARRATOR_MAX_TOKENS = int(os.environ.get("DM_NARRATOR_MAX_TOKENS", "1200"))

_shared_client: Optional[httpx.AsyncClient] = None


def set_http_client(client: httpx.AsyncClient) -> None:
    global _shared_client
    _shared_client = client


def _hermes_binary() -> Optional[str]:
    return shutil.which("hermes")


def _profile_dir() -> Path:
    return Path(HERMES_HOME) / "profiles" / DM_HERMES_PROFILE


def _extract_balanced_json(text: str) -> Optional[str]:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return None


def _parse_json_text(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    if not text:
        return None
    candidates = [text]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    candidates.extend(chunk.strip() for chunk in fenced if chunk.strip())
    balanced = _extract_balanced_json(text)
    if balanced:
        candidates.append(balanced)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _build_hermes_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        "You are the Dungeon Master. Respond with ONLY valid JSON.\n\n"
        f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\n"
        f"SCENE DATA:\n{user_prompt}\n\n"
        "Respond with JSON containing: scene, npc_lines, tone, choices_summary"
    )


def _extract_hermes_session_id(*texts: str) -> Optional[str]:
    """Extract Hermes CLI session_id from stdout or stderr.

    Hermes versions differ on whether metadata is printed to stdout or stderr.
    Capture it before stdout filtering removes metadata lines.
    """
    combined = "\n".join(text for text in texts if text)
    match = re.search(r"(?:^|\n)session_id:\s*(\S+)", combined)
    return match.group(1) if match else None


def _filter_hermes_stdout(output: str) -> str:
    lines = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("↻"):
            continue
        if stripped.startswith("session_id:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _status_base() -> dict[str, Any]:
    binary = _hermes_binary()
    profile_dir = _profile_dir()
    binary_ok = bool(binary and os.access(binary, os.X_OK))
    help_ok = False
    if binary_ok:
        try:
            import subprocess
            proc = subprocess.run([binary, "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            help_ok = proc.returncode == 0
        except Exception:
            help_ok = False
    return {
        "mode": DM_HERMES_MODE,
        "hermes_profile": DM_HERMES_PROFILE,
        "hermes_home": HERMES_HOME,
        "hermes_binary": binary,
        "binary_ok": binary_ok,
        "binary_help_ok": help_ok,
        "profile_dir": str(profile_dir),
        "profile_exists": profile_dir.is_dir(),
        "api_key_set": bool(KIMI_API_KEY),
        "base_url": KIMI_BASE_URL,
        "model": DM_NARRATOR_MODEL,
        "timeout": DM_NARRATOR_TIMEOUT,
        "max_tokens": DM_NARRATOR_MAX_TOKENS,
        "runtime_ready": binary_ok and help_ok and profile_dir.is_dir(),
    }


def get_status() -> dict[str, Any]:
    return _status_base()


async def narrate_via_direct(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.8,
) -> Optional[dict[str, Any]]:
    if not KIMI_API_KEY:
        logger.warning("No KIMI_API_KEY set — cannot call Kimi directly")
        return None

    payload = {
        "model": DM_NARRATOR_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": DM_NARRATOR_MAX_TOKENS,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "User-Agent": "claude-code/0.1.0",
    }

    try:
        if _shared_client is not None:
            response = await _shared_client.post(
                f"{KIMI_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=110.0,
            )
        else:
            async with httpx.AsyncClient(timeout=110.0) as client:
                response = await client.post(
                    f"{KIMI_BASE_URL.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=110.0,
                )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        parsed = _parse_json_text(message.get("content", "") or message.get("reasoning_content", "") or "")
        if not parsed:
            logger.warning("Direct DM call returned non-JSON content")
            return None
        return parsed
    except httpx.TimeoutException as e:
        logger.warning("Direct DM call timed out: %s", e)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("Direct DM call HTTP error: %s %s", e.response.status_code, e.response.text[:200])
        return None
    except Exception as e:
        logger.warning("Direct DM call error: %s", e)
        return None


async def narrate_via_hermes(
    system_prompt: str,
    user_prompt: str,
    session_id: str | None = None,
) -> Optional[dict[str, Any]]:
    status = _status_base()
    if not status["runtime_ready"]:
        logger.warning(
            "Hermes runtime not ready (binary_ok=%s help_ok=%s profile_exists=%s)",
            status["binary_ok"],
            status["binary_help_ok"],
            status["profile_exists"],
        )
        return None

    prompt = _build_hermes_prompt(system_prompt, user_prompt)
    cmd = [
        status["hermes_binary"],
        "chat",
        "-q",
        prompt,
        "-Q",
        "--profile",
        DM_HERMES_PROFILE,
    ]
    if session_id:
        cmd.extend(["--resume", session_id])

    env = {**os.environ, "HERMES_HOME": HERMES_HOME}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=DM_NARRATOR_TIMEOUT)
        stdout_text = _filter_hermes_stdout(stdout.decode(errors="replace"))
        stderr_text = stderr.decode(errors="replace")

        if proc.returncode != 0:
            logger.warning("Hermes DM exited with code %s: %s", proc.returncode, stderr_text[:300])
            return None

        parsed = _parse_json_text(stdout_text)
        if not parsed:
            logger.warning("Hermes DM output not valid JSON: %s", stdout_text[:300])
            return None

        sid = _extract_hermes_session_id(stdout.decode(errors="replace"), stderr_text)
        if sid:
            parsed["_hermes_session_id"] = sid
        return parsed
    except asyncio.TimeoutError:
        logger.warning("Hermes DM narration timed out after %ss", DM_NARRATOR_TIMEOUT)
        return None
    except FileNotFoundError:
        logger.warning("Hermes CLI not found")
        return None
    except Exception as e:
        logger.warning("Hermes DM call error: %s", e)
        return None


async def narrate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.8,
    session_id: str | None = None,
) -> Optional[dict[str, Any]]:
    if DM_HERMES_MODE == "hermes":
        result = await narrate_via_hermes(system_prompt, user_prompt, session_id=session_id)
        if result:
            return result
        logger.warning("Hermes mode failed; direct fallback disabled for actual DM-agent flow")
        return None
    return await narrate_via_direct(system_prompt, user_prompt, temperature)

"""Thin client for a local Ollama daemon. Stdlib only (urllib) — no extra
dependency for something this small.

Default model is gpt-oss:20b: good instruction-following and JSON-mode
compliance at a size that leaves headroom on a 32GB card for the long
prompts this loop builds (trace excerpts + memory precedents). Override
with WAM_DIAGNOSTIC_MODEL, e.g. to deepseek-r1:32b for harder root-cause
cases (slower, and emits <think> reasoning that this client strips out).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("WAM_DIAGNOSTIC_MODEL", "gpt-oss:20b")

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaError(RuntimeError):
    pass


def is_available(base_url: str = DEFAULT_BASE_URL, timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(f"{base_url}/api/version", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError):
        return False


def chat_json(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 300.0,
) -> dict:
    """Chat call constrained to JSON output. Returns the parsed object.

    Raises OllamaError on a transport failure or on output that isn't
    valid JSON after <think>...</think> stripping — callers should treat
    that as "diagnosis failed" and fall back to leaving the anomaly
    unresolved rather than guessing.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": "json",
        "stream": False,
    }
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as e:
        raise OllamaError(f"could not reach ollama at {base_url}: {e}") from e

    content = body.get("message", {}).get("content", "")
    content = _THINK_RE.sub("", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise OllamaError(f"model did not return valid JSON: {e}\n---\n{content[:2000]}") from e

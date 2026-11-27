"""Small, auditable client for the Gemini Developer API."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "gemini-3.5-flash-lite"


def _load_local_config():
    """Load only the two Gemini settings from the ignored local .env file."""
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name not in {"GEMINI_API_KEY", "GEMINI_MODEL"} or name in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[name] = value


def generate(messages, *, model=None, max_tokens=300, response_schema=None):
    """Generate JSON text using Gemini; never log the key, prompt, or response."""
    _load_local_config()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in the environment, GitHub Actions secret, or ignored .env file")

    model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("GEMINI_MODEL contains unsupported characters")
    if not isinstance(max_tokens, int) or not 1 <= max_tokens <= 8192:
        raise ValueError("max_tokens must be between 1 and 8192")

    system_parts = [item["content"] for item in messages if item.get("role") == "system"]
    contents = []
    for item in messages:
        role = item.get("role")
        if role == "system":
            continue
        if role not in {"user", "assistant"}:
            raise ValueError("Only system, user, and assistant messages are supported")
        contents.append({"role": "model" if role == "assistant" else "user",
                         "parts": [{"text": str(item.get("content", ""))}]})
    if not contents or not any(item["role"] == "user" for item in contents):
        raise ValueError("At least one user message is required")

    payload = {
        "systemInstruction": {"parts": [{"text": "\n\n".join(system_parts)}]} if system_parts else None,
        "contents": contents,
        "generationConfig": {"temperature": 0, "seed": 42, "maxOutputTokens": max_tokens,
                             "responseMimeType": "application/json"},
    }
    if response_schema is not None:
        payload["generationConfig"]["responseJsonSchema"] = response_schema
    if payload["systemInstruction"] is None:
        del payload["systemInstruction"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='._-')}:generateContent"
    request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                      method="POST")
    started = time.monotonic()
    try:
        with urlopen(request, timeout=90) as response:
            value = json.loads(response.read(1_000_000).decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Gemini API request failed with HTTP {exc.code}; no report was certified") from None
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Gemini API request failed due to a network or response error; no report was certified") from None

    try:
        text = value["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Gemini API returned no text candidate; no report was certified") from None
    return {"text": text, "usage": value.get("usageMetadata", {}),
            "model": value.get("modelVersion", model), "provider": "Google Gemini API",
            "temperature": 0, "seed": 42,
            "seconds": round(time.monotonic() - started, 4),
            "timestamp_utc": datetime.now(timezone.utc).isoformat()}

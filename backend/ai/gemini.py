"""Thin Gemini API client (Google AI Studio), stdlib only.

No SDK dependency: we POST to generateContent with a responseSchema so
Gemini returns validated JSON. The key comes from GEMINI_API_KEY; when
it is absent every feature falls back to the deterministic logic in
local.py, so the app works fully offline — Gemini only makes it nicer.
"""
import base64
import json
import os
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(Exception):
    pass


def api_key():
    return os.environ.get("GEMINI_API_KEY", "").strip()


def model_name():
    # 'gemini-flash-latest' tracks the newest stable Flash model, so the
    # default keeps working as Google retires old versions.
    return os.environ.get("GEMINI_MODEL", "gemini-flash-latest").strip()


def available():
    return bool(api_key())


def generate_json(prompt, schema, image_bytes=None, image_mime=None, temperature=0.2):
    """Call generateContent and return the parsed JSON object.

    `schema` is a Gemini responseSchema (OpenAPI-subset). When
    image_bytes is given it is attached inline (receipt scanning).
    """
    if not available():
        raise GeminiError("GEMINI_API_KEY is not configured.")

    parts = [{"text": prompt}]
    if image_bytes:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image_mime or "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    }
    req = urllib.request.Request(
        f"{API_ROOT}/{model_name()}:generateContent",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as res:
            body = json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise GeminiError(f"Gemini API error {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GeminiError(f"Could not reach the Gemini API: {e}") from e

    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise GeminiError(f"Unexpected Gemini response shape: {e}") from e

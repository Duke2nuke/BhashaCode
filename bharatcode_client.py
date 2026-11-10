"""BharatCode model API client for BhashaCode.

Verified against the BharatCode Build League example project Marg
(https://github.com/Mqhnish/marg, ``marg/llm.py`` and ``BharatCode.txt``,
read 2026-11-06):

- Base URL: ``https://bharatcode.ai/api/model/v1``
- Default model: ``qwen-3.8-27b``
- Endpoints: ``POST /responses`` (default in Marg, ``store=false``) and
  ``POST /chat/completions`` (``--api chat`` in Marg). Both are
  OpenAI-compatible and take ``Authorization: Bearer $BHARATCODE_API_KEY``.
- The API is stateless; Marg replays history each request.
- BharatCode returns 503 when the model is busy; 429/5xx are retried
  with backoff.
- Get a key at https://bharatcode.ai/account (BharatCode homepage:
  students get Qwen free up to 10M tokens a day).

BhashaCode uses the Chat Completions endpoint for its single-turn
explain calls — same base URL and model, simpler non-streaming shape.
No standalone BharatCode API docs page was found on 2026-11-06; the
Marg source above is the documented reference.

The API key comes from the environment only (``BHARATCODE_API_KEY``).
When no key is set, :func:`explain_code` returns a clearly labelled
MOCK explanation produced locally — never presented as a live result.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://bharatcode.ai/api/model/v1"
DEFAULT_MODEL = "qwen-3.8-27b"
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_CODE_CHARS = 8_000
MAX_CODE_LINES = 200

# Language code -> display name. These are the 10 languages BhashaCode offers.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "mr": "Marathi",
    "kn": "Kannada",
    "ml": "Malayalam",
    "gu": "Gujarati",
    "pa": "Punjabi",
}


class BharatCodeError(Exception):
    """Raised when the live BharatCode API call fails."""


def base_url() -> str:
    """API base URL. ``BHARATCODE_API_URL`` wins; Marg's
    ``BHARATCODE_BASE_URL`` is accepted as a fallback."""
    return (
        os.environ.get("BHARATCODE_API_URL")
        or os.environ.get("BHARATCODE_BASE_URL")
        or DEFAULT_BASE_URL
    ).rstrip("/")


def model_name() -> str:
    return os.environ.get("BHARATCODE_MODEL") or DEFAULT_MODEL


def language_name(code: str) -> str:
    """Display name for a language code; raises ValueError if unknown."""
    try:
        return SUPPORTED_LANGUAGES[code]
    except KeyError as exc:
        raise ValueError(
            f"unsupported language {code!r}; choose one of "
            f"{', '.join(sorted(SUPPORTED_LANGUAGES))}"
        ) from exc


def validate_code(code: str) -> str:
    """Validate pasted code; raises ValueError on empty / oversized input."""
    if code is None or not str(code).strip():
        raise ValueError("code must not be empty")
    code = str(code)
    if len(code) > MAX_CODE_CHARS:
        raise ValueError(f"code is too long (max {MAX_CODE_CHARS} characters)")
    lines = code.splitlines()
    if len(lines) > MAX_CODE_LINES:
        raise ValueError(f"code has too many lines (max {MAX_CODE_LINES})")
    return code


# ---------------------------------------------------------------- mock mode
def _describe_line(line: str) -> str:
    """One plain-English description of a single line of code (mock)."""
    stripped = line.strip()
    if not stripped:
        return "Blank line."
    if stripped.startswith("#") or stripped.startswith("//"):
        return f"Comment: {stripped.lstrip('#/ ').strip() or 'a note for the reader.'}"
    if re.match(r"(def|function)\s+\w+", stripped):
        name = re.search(r"(?:def|function)\s+(\w+)", stripped).group(1)
        return f"Defines a function called {name}."
    if re.match(r"class\s+\w+", stripped):
        name = re.search(r"class\s+(\w+)", stripped).group(1)
        return f"Defines a class called {name}."
    if stripped.startswith(("import ", "from ")):
        return "Brings in code from another module so it can be used here."
    if re.match(r"for\s+.+\s+in\s+", stripped):
        return "Loops over a collection, doing the indented lines once per item."
    if stripped.startswith("while "):
        return "Repeats the indented lines while a condition stays true."
    if re.match(r"(if|elif)\s+", stripped):
        return "Runs the indented lines only if a condition is true."
    if stripped == "else:" or stripped.startswith("else:"):
        return "Runs these lines when the condition above was false."
    if stripped.startswith("return "):
        return "Sends a value back to whoever called this function."
    if stripped.startswith("print("):
        return "Prints a value to the screen."
    if re.match(r"\w[\w.]*\s*=\s*[^=]", stripped):
        return "Stores a value in a variable for later use."
    if stripped.startswith(("try:", "except", "finally:")):
        return "Handles errors so the program can fail gracefully."
    return f"Runs: {stripped[:100]}"


def mock_explain(code: str, lang: str) -> dict:
    """Deterministic local explanation. Always labelled MOCK.

    The mock explanation is in English: the language choice is honoured
    by the live model; without a key there is no translator to call.
    """
    code = validate_code(code)
    lang_name = language_name(lang)
    lines = [ln for ln in code.splitlines() if ln.strip()]
    kinds = set()
    if re.search(r"\bdef\b|\bfunction\b", code):
        kinds.add("function(s)")
    if re.search(r"\bclass\b", code):
        kinds.add("a class")
    if re.search(r"\bfor\b|\bwhile\b", code):
        kinds.add("a loop")
    if re.search(r"\bif\b", code):
        kinds.add("a condition")
    if re.search(r"\bprint\(", code):
        kinds.add("printed output")
    what = ", ".join(sorted(kinds)) if kinds else "a short sequence of statements"
    return {
        "summary": (
            f"MOCK — no BharatCode key set, demo only. This snippet has "
            f"{len(lines)} non-empty line(s) with {what}. "
            f"(Explanations in {lang_name} need a live BharatCode key; "
            f"this mock text is in English.)"
        ),
        "breakdown": [
            {"line": ln.strip()[:200], "explanation": _describe_line(ln)}
            for ln in lines
        ],
        "language": lang,
        "language_name": lang_name,
        "mode": "mock",
        "model": None,
    }


# ------------------------------------------------------------- live API path
def _chat_completion(code: str, lang: str, api_key: str, transport=None) -> dict:
    """One Chat Completions call. ``transport`` is an injectable
    ``(url, headers, body) -> dict`` used by the tests."""
    lang_name = language_name(lang)
    system = (
        "You explain code in plain, simple language for a beginner. "
        f"Answer in {lang_name}. Keep code, function names and keywords "
        "in English, untranslated. Reply with JSON only, exactly in this "
        'shape: {"summary": "<2-3 sentence plain-language summary>", '
        '"breakdown": [{"line": "<the code line>", "explanation": '
        '"<one plain sentence>"}, ...]} — one breakdown entry per '
        "non-empty line of the code."
    )
    body = {
        "model": model_name(),
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Explain this code in {lang_name}:\n\n```\n{code}\n```",
            },
        ],
        "max_tokens": 2000,
    }
    url = f"{base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if transport is None:
        transport = _default_transport
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            data = transport(url, headers, body)
            return _parse_chat_response(data)
        except BharatCodeError as exc:
            last_error = exc
            retryable = getattr(exc, "status", None) in RETRY_STATUSES or getattr(
                exc, "retryable", False
            )
            if retryable and attempt < 2:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise last_error  # pragma: no cover - loop always returns or raises


def _default_transport(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        err = BharatCodeError(f"BharatCode API returned HTTP {exc.code}: {detail}")
        err.status = exc.code  # type: ignore[attr-defined]
        raise err from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        err = BharatCodeError(f"could not reach BharatCode API: {exc}")
        err.retryable = True  # type: ignore[attr-defined]
        raise err from exc


def _parse_chat_response(data: dict) -> dict:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise BharatCodeError(f"unexpected BharatCode response shape: {str(data)[:300]}") from exc
    if not content or not content.strip():
        raise BharatCodeError("BharatCode returned an empty explanation")
    text = content.strip()
    # The model may wrap JSON in ```json fences; strip them.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        summary = str(parsed["summary"]).strip()
        breakdown = [
            {
                "line": str(item.get("line", ""))[:200],
                "explanation": str(item.get("explanation", "")).strip(),
            }
            for item in parsed.get("breakdown", [])
            if str(item.get("explanation", "")).strip()
        ]
        if not summary:
            raise ValueError("empty summary")
        return {"summary": summary, "breakdown": breakdown}
    except (ValueError, KeyError, TypeError, AttributeError):
        # Fallback: treat the whole reply as the summary.
        return {"summary": text, "breakdown": []}


def explain_code(code: str, lang: str = "en", api_key: str | None = None,
                 transport=None) -> dict:
    """Explain ``code`` in language ``lang``.

    Returns ``{summary, breakdown, language, language_name, mode, model}``
    with ``mode`` ``"live"`` when the BharatCode API answered and
    ``"mock"`` when no key is set. Raises ValueError for bad input and
    BharatCodeError when the live call fails.
    """
    code = validate_code(code)
    lang_name = language_name(lang)
    key = api_key or os.environ.get("BHARATCODE_API_KEY")
    if not key:
        return mock_explain(code, lang)
    result = _chat_completion(code, lang, key, transport=transport)
    return {
        "summary": result["summary"],
        "breakdown": result["breakdown"],
        "language": lang,
        "language_name": lang_name,
        "mode": "live",
        "model": model_name(),
    }

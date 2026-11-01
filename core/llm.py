"""OpenAI-compatible LLM client for the ModelScope inference endpoint.

Owned by Person 1. Contract in ``docs/data_contract.md`` (section 5).

Security rules enforced here:
- Only ``MODELSCOPE_API_KEY`` and ``MODELSCOPE_MODEL`` are ever read, from the
  server environment first and then the local ``.env`` file. No other
  environment variables or credential files (e.g. OpenCode credentials) are
  accessed.
- The API key is never logged and never appears in error messages; it is only
  sent as the ``Authorization`` header.
- Patient text is never logged; all error messages are fixed, safe English
  strings.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "ALLOWED_MODELS",
    "API_KEY_ENV",
    "BASE_URL",
    "ConfigError",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "LLMAuthError",
    "LLMConfig",
    "LLMError",
    "LLMNetworkError",
    "LLMQuotaError",
    "LLMResponseError",
    "LLMServerError",
    "MODEL_ENV",
    "chat",
    "chat_json",
    "chat_json_repairable",
    "default_dotenv_path",
    "load_config",
]

BASE_URL = "https://api-inference.modelscope.ai/v1"
DEFAULT_MODEL = "zai-org/GLM-5.2"

# The only models this client may call.
ALLOWED_MODELS: tuple[str, ...] = (
    "zai-org/GLM-5.2",
    "deepseek-ai/DeepSeek-V4-Pro-0813",
    "stepfun-ai/Step-3.5-Flash",
    "Qwen/Qwen3.8-27B",
)

API_KEY_ENV = "MODELSCOPE_API_KEY"
MODEL_ENV = "MODELSCOPE_MODEL"

DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
MAX_TIMEOUT_SECONDS = 600.0
_RETRY_BACKOFF_BASE_SECONDS = 0.5

logger = logging.getLogger("core.llm")


class LLMError(Exception):
    """Base class for all safe, English, user-facing LLM errors."""


class ConfigError(LLMError):
    """The local configuration (environment / .env) is missing or invalid."""


class LLMAuthError(LLMError):
    """The ModelScope API rejected the credentials."""


class LLMQuotaError(LLMError):
    """The ModelScope API quota or rate limit was reached."""


class LLMNetworkError(LLMError):
    """The ModelScope API could not be reached (network failure or timeout)."""


class LLMServerError(LLMError):
    """The ModelScope API returned an HTTP 5xx error."""


class LLMResponseError(LLMError):
    """The model response was missing, malformed, or failed validation."""


@dataclass(frozen=True)
class LLMConfig:
    """Resolved configuration (api_key is never printed or logged)."""

    api_key: str
    model: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def default_dotenv_path() -> Path:
    """The project-local ``.env`` path (repository root)."""
    return Path(__file__).resolve().parent.parent / ".env"


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` .env file (comments/blanks ignored)."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_config(
    env: dict[str, str] | None = None,
    dotenv_path: str | Path | None = None,
) -> LLMConfig:
    """Resolve the API key and model.

    Server environment variables win over the local ``.env`` file. Raises
    ``ConfigError`` (safe English message) when the key is missing or the
    model is not one of the approved models.
    """
    env = os.environ if env is None else env
    file_values = _parse_dotenv(Path(dotenv_path)) if dotenv_path is not None else {}

    api_key = (env.get(API_KEY_ENV) or file_values.get(API_KEY_ENV) or "").strip()
    model = (env.get(MODEL_ENV) or file_values.get(MODEL_ENV) or DEFAULT_MODEL).strip()

    if not api_key:
        raise ConfigError(
            "No API key configured. Copy .env.example to .env and set "
            "MODELSCOPE_API_KEY, or set it in the server environment."
        )
    if model not in ALLOWED_MODELS:
        raise ConfigError(
            "MODELSCOPE_MODEL is not an approved model. Approved models: "
            + ", ".join(ALLOWED_MODELS)
        )
    return LLMConfig(api_key=api_key, model=model)


# ---------------------------------------------------------------------------
# HTTP transport (single seam for tests)
# ---------------------------------------------------------------------------


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _http_post(
    url: str, payload: bytes, headers: dict[str, str], timeout: float
) -> tuple[int, bytes]:
    """POST and return ``(status, body)``; network failures raise."""
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _resolve_config() -> LLMConfig:
    """Resolve config for calls that do not pass one explicitly: server
    environment first, then the project-local ``.env`` file."""
    return load_config(dotenv_path=default_dotenv_path())


def chat(
    system: str,
    user: str,
    *,
    config: LLMConfig | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Send one chat completion request and return the assistant text.

    - Finite timeout (``0 < timeout <= 600`` seconds).
    - Bounded retries: network failures and HTTP 5xx are retried up to
      ``max_retries`` times with capped exponential backoff; authentication,
      quota, and other client errors fail fast.
    - Raises safe, English ``LLMError`` subclasses; messages never contain
      the API key or the request/response text.
    """
    cfg = config if config is not None else _resolve_config()
    chosen_model = model if model is not None else cfg.model
    if chosen_model not in ALLOWED_MODELS:
        raise ConfigError(
            "The requested model is not an approved model. Approved models: "
            + ", ".join(ALLOWED_MODELS)
        )
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        raise ConfigError("timeout must be a number of seconds between 0 and 600.")
    if max_retries < 0 or max_retries > 5:
        raise ConfigError("max_retries must be between 0 and 5.")

    url = BASE_URL.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }

    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            status, body = _http_post(url, payload, headers, timeout)
        except (OSError, http.client.HTTPException) as exc:
            logger.debug(
                "attempt %d/%d failed with network error type=%s",
                attempt,
                attempts,
                type(exc).__name__,
            )
            if attempt < attempts:
                _sleep(_RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue
            raise LLMNetworkError(
                "Could not reach the ModelScope API (network error). "
                "Check the connection and try again."
            ) from None

        if status == 200:
            return _content_from_body(body)
        if status in (401, 403):
            logger.debug("attempt %d failed with HTTP %s", attempt, status)
            raise LLMAuthError(
                "The ModelScope API rejected the API key (authentication "
                "failed). Check MODELSCOPE_API_KEY."
            )
        if status == 429:
            logger.debug("attempt %d failed with HTTP 429", attempt)
            raise LLMQuotaError(
                "The ModelScope API quota or rate limit was reached. "
                "Please try again later."
            )
        if 500 <= status < 600:
            logger.debug("attempt %d got HTTP %s", attempt, status)
            if attempt < attempts:
                _sleep(_RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue
            raise LLMServerError(
                "The ModelScope API returned a server error. "
                "Please try again later."
            )
        logger.debug("attempt %d failed with HTTP %s", attempt, status)
        raise LLMError(
            "The ModelScope API returned an error (HTTP "
            f"{status}). Please try again."
        )
    raise LLMNetworkError(  # pragma: no cover - unreachable
        "Could not reach the ModelScope API (network error). "
        "Check the connection and try again."
    )


def _content_from_body(body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMResponseError(
            "The model returned an invalid response. Please try again."
        ) from None
    if not isinstance(content, str) or not content.strip():
        raise LLMResponseError(
            "The model returned an empty response. Please try again."
        )
    return content


def chat_json(
    system: str,
    user: str,
    *,
    validate: Callable[[dict[str, Any]], list[str]],
    **kwargs: Any,
) -> dict[str, Any]:
    """As :func:`chat`, but the response must be a JSON object.

    ``validate(data)`` must return a list of problems (empty list = valid).
    Raises ``LLMResponseError`` with a safe message when the response is not
    valid JSON or fails validation.
    """
    if not callable(validate):
        raise ConfigError("chat_json requires a validate callable.")
    raw = chat(system, user, **kwargs)
    data = _extract_json_object(raw)
    errors = validate(data)
    if errors:
        raise LLMResponseError(
            "The model returned an invalid response. Please try again."
        )
    return data


def chat_json_repairable(
    system: str,
    user: str,
    *,
    validate: Callable[[dict[str, Any]], list[str]],
    repair_note: str | None = None,
    max_repairs: int = 1,
    **kwargs: Any,
) -> dict[str, Any]:
    """As :func:`chat_json`, with bounded JSON repair.

    When the response is not valid JSON or fails ``validate``, the request is
    repeated at most ``max_repairs`` times (default 1) with a repair note
    appended, so the total number of model calls is bounded by
    ``max_repairs + 1``. On the repair attempt the specific validation problems
    (fixed English labels only — never patient text) are appended so the model
    can fix them; this is the seam through which source/record-aware checks
    reach the bounded repair path. Raises ``LLMResponseError`` with a safe
    message when every attempt is invalid.
    """
    if not callable(validate):
        raise ConfigError("chat_json_repairable requires a validate callable.")
    note = repair_note or (
        "Your previous reply was not a valid JSON object matching the "
        "required schema."
    )
    attempts = max_repairs + 1
    last_problems: list[str] = []
    for attempt in range(1, attempts + 1):
        message = user
        if attempt > 1:
            parts = [note]
            if last_problems:
                parts.append(
                    "Problems found: " + "; ".join(last_problems) + "."
                )
            parts.append("Reply with only the corrected JSON object.")
            message = user + "\n\n" + " ".join(parts)
        raw = chat(system, message, **kwargs)
        try:
            data = _extract_json_object(raw)
            errors = validate(data)
        except LLMResponseError:
            errors = ["the response was not a valid JSON object"]
        if not errors:
            return data
        last_problems = errors
        logger.debug("json response invalid on attempt %d/%d", attempt, attempts)
    raise LLMResponseError(
        "The model returned an invalid response after the allowed repair "
        "attempts. Please try again."
    )


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMResponseError(
                "The model returned an invalid response. Please try again."
            ) from None
        try:
            data = json.loads(text[start : end + 1])
        except ValueError:
            raise LLMResponseError(
                "The model returned an invalid response. Please try again."
            ) from None
    if not isinstance(data, dict):
        raise LLMResponseError(
            "The model returned an invalid response. Please try again."
        )
    return data

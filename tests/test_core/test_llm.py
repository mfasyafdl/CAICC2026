"""Tests for the ModelScope LLM client (config + failure handling).

Owned by Person 1. No network access: the HTTP transport seam is faked.
"""

import json
import urllib.error

import pytest

from core import llm
from core.llm import (
    ALLOWED_MODELS,
    ConfigError,
    LLMAuthError,
    LLMConfig,
    LLMError,
    LLMNetworkError,
    LLMQuotaError,
    LLMResponseError,
    LLMServerError,
    chat,
    chat_json,
    load_config,
)

FAKE_KEY = "ms-fake-key-do-not-use"
CFG = LLMConfig(api_key=FAKE_KEY, model="zai-org/GLM-5.2")


class FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, url, payload, headers, timeout):
        self.calls.append(
            {"url": url, "payload": payload, "headers": headers, "timeout": timeout}
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ok_body(content: str) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode("utf-8")


def _install(monkeypatch, outcomes, sleep_values=None):
    transport = FakeTransport(outcomes)
    monkeypatch.setattr(llm, "_http_post", transport)
    sleeps = []
    monkeypatch.setattr(llm, "_sleep", lambda s: sleeps.append(s))
    return transport, sleeps


# --- configuration ---------------------------------------------------------


def test_allowed_models_are_exactly_the_four_approved():
    assert ALLOWED_MODELS == (
        "zai-org/GLM-5.2",
        "deepseek-ai/DeepSeek-V4-Pro-0813",
        "stepfun-ai/Step-3.5-Flash",
        "Qwen/Qwen3.8-27B",
    )


def test_load_config_reads_server_env_and_defaults_model(monkeypatch):
    monkeypatch.setenv("MODELSCOPE_API_KEY", FAKE_KEY)
    monkeypatch.delenv("MODELSCOPE_MODEL", raising=False)
    cfg = load_config()
    assert cfg.api_key == FAKE_KEY
    assert cfg.model == llm.DEFAULT_MODEL == "zai-org/GLM-5.2"


def test_load_config_env_wins_over_dotenv(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("MODELSCOPE_API_KEY=file-key\nMODELSCOPE_MODEL=Qwen/Qwen3.8-27B\n")
    monkeypatch.setenv("MODELSCOPE_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MODELSCOPE_MODEL", "stepfun-ai/Step-3.5-Flash")
    cfg = load_config(dotenv_path=dotenv)
    assert cfg.api_key == FAKE_KEY
    assert cfg.model == "stepfun-ai/Step-3.5-Flash"


def test_load_config_falls_back_to_dotenv(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text('MODELSCOPE_API_KEY="file-key"\n# a comment\n\nMODELSCOPE_MODEL=Qwen/Qwen3.8-27B\n')
    monkeypatch.delenv("MODELSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("MODELSCOPE_MODEL", raising=False)
    cfg = load_config(dotenv_path=dotenv)
    assert cfg.api_key == "file-key"
    assert cfg.model == "Qwen/Qwen3.8-27B"


def test_load_config_missing_key_raises_safe_error(monkeypatch, tmp_path):
    monkeypatch.delenv("MODELSCOPE_API_KEY", raising=False)
    with pytest.raises(ConfigError) as exc:
        load_config(dotenv_path=tmp_path / "missing.env")
    message = str(exc.value)
    assert "MODELSCOPE_API_KEY" in message
    assert FAKE_KEY not in message


def test_load_config_rejects_unapproved_model(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELSCOPE_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MODELSCOPE_MODEL", "evil-org/evil-model")
    with pytest.raises(ConfigError) as exc:
        load_config(dotenv_path=tmp_path / "missing.env")
    message = str(exc.value)
    assert "not an approved model" in message
    assert "evil-org/evil-model" not in message


def test_only_modelscope_vars_are_read(monkeypatch, tmp_path):
    monkeypatch.setenv("MODELSCOPE_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENCODE_API_KEY", "sentinel-must-not-appear")
    monkeypatch.setenv("SOME_OTHER_SECRET", "sentinel-must-not-appear")
    cfg = load_config(dotenv_path=tmp_path / "missing.env")
    assert cfg.api_key == FAKE_KEY
    assert "sentinel" not in repr(cfg)


def test_chat_rejects_unapproved_model_without_network(monkeypatch):
    transport, _ = _install(monkeypatch, [])
    with pytest.raises(ConfigError):
        chat("s", "u", config=CFG, model="evil-org/evil-model")
    assert transport.calls == []


def test_chat_rejects_non_finite_timeout(monkeypatch):
    transport, _ = _install(monkeypatch, [])
    with pytest.raises(ConfigError):
        chat("s", "u", config=CFG, timeout=0)
    with pytest.raises(ConfigError):
        chat("s", "u", config=CFG, timeout=float("inf"))
    assert transport.calls == []


# --- failure handling -------------------------------------------------------


def test_auth_failure_fails_fast_without_retry(monkeypatch):
    transport, sleeps = _install(monkeypatch, [(401, b'{"error":"bad key"}')])
    with pytest.raises(LLMAuthError) as exc:
        chat("s", "u", config=CFG)
    assert len(transport.calls) == 1
    assert sleeps == []
    assert "authentication failed" in str(exc.value)
    assert FAKE_KEY not in str(exc.value)


def test_forbidden_is_auth_error(monkeypatch):
    _install(monkeypatch, [(403, b"")])
    with pytest.raises(LLMAuthError):
        chat("s", "u", config=CFG)


def test_quota_error_fails_fast(monkeypatch):
    transport, _ = _install(monkeypatch, [(429, b'{"error":"quota"}')])
    with pytest.raises(LLMQuotaError) as exc:
        chat("s", "u", config=CFG)
    assert len(transport.calls) == 1
    assert "quota" in str(exc.value).lower()


def test_network_error_retries_bounded_times(monkeypatch):
    outcomes = [urllib.error.URLError("dns fail")] * 3
    transport, sleeps = _install(monkeypatch, outcomes)
    with pytest.raises(LLMNetworkError) as exc:
        chat("s", "u", config=CFG)
    assert len(transport.calls) == 3  # 1 initial + 2 retries
    assert sleeps == [0.5, 1.0]
    assert "network error" in str(exc.value).lower()


def test_network_error_respects_zero_retries(monkeypatch):
    transport, _ = _install(monkeypatch, [urllib.error.URLError("dns fail")])
    with pytest.raises(LLMNetworkError):
        chat("s", "u", config=CFG, max_retries=0)
    assert len(transport.calls) == 1


def test_server_error_retried_then_raises(monkeypatch):
    transport, _ = _install(monkeypatch, [(503, b""), (500, b""), (502, b"")])
    with pytest.raises(LLMServerError):
        chat("s", "u", config=CFG)
    assert len(transport.calls) == 3  # 1 initial + 2 retries


def test_other_4xx_is_plain_llm_error(monkeypatch):
    _install(monkeypatch, [(400, b'{"error":"bad request"}')])
    with pytest.raises(LLMError) as exc:
        chat("s", "u", config=CFG)
    assert not isinstance(exc.value, (LLMAuthError, LLMQuotaError, LLMNetworkError))
    assert "HTTP 400" in str(exc.value)


def test_malformed_success_body_raises_response_error(monkeypatch):
    _install(monkeypatch, [(200, b"this is not json")])
    with pytest.raises(LLMResponseError):
        chat("s", "u", config=CFG)


def test_success_returns_content_and_sends_key_only_in_header(monkeypatch, caplog):
    transport, _ = _install(monkeypatch, [(200, _ok_body("hello back"))])
    with caplog.at_level("DEBUG", logger="core.llm"):
        result = chat("you are a scribe", "summarize", config=CFG)
    assert result == "hello back"
    call = transport.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert call["timeout"] == llm.DEFAULT_TIMEOUT_SECONDS
    payload = json.loads(call["payload"].decode("utf-8"))
    assert payload["model"] == "zai-org/GLM-5.2"
    assert caplog.text.count(FAKE_KEY) == 0
    assert "summarize" not in caplog.text


# --- chat_json ---------------------------------------------------------------


def test_chat_json_returns_validated_dict(monkeypatch):
    _install(monkeypatch, [(200, _ok_body('{"a": 1}'))])
    data = chat_json("s", "u", config=CFG, validate=lambda d: [])
    assert data == {"a": 1}


def test_chat_json_parses_fenced_json(monkeypatch):
    _install(monkeypatch, [(200, _ok_body("```json\n{\"a\": 1}\n```"))])
    data = chat_json("s", "u", config=CFG, validate=lambda d: [])
    assert data == {"a": 1}


def test_chat_json_validation_failure_raises_safe_error(monkeypatch):
    _install(monkeypatch, [(200, _ok_body('{"a": "patient words here"}'))])
    with pytest.raises(LLMResponseError) as exc:
        chat_json("s", "u", config=CFG, validate=lambda d: ["field a is wrong"])
    message = str(exc.value)
    assert "patient words" not in message
    assert FAKE_KEY not in message


def test_chat_json_requires_validator(monkeypatch):
    _install(monkeypatch, [])
    with pytest.raises(ConfigError):
        chat_json("s", "u", config=CFG, validate=None)  # type: ignore[arg-type]

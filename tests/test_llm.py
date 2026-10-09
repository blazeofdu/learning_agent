import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError

import llm


def test_missing_key_fails_before_client_creation(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(llm.ModelServiceError) as error:
        asyncio.run(llm.create_chat_completion(messages=[]))
    assert error.value.status_code == 503


@pytest.mark.parametrize("error_class, status", [
    (APITimeoutError, 504), (APIConnectionError, 503),
    (RateLimitError, 503), (AuthenticationError, 502),
])
@pytest.mark.parametrize("async_mode", [True, False])
def test_sdk_errors_are_mapped_without_leaking_details(monkeypatch, error_class, status, async_mode):
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    if error_class in (APITimeoutError, APIConnectionError):
        sdk_error = error_class(request=request)
    else:
        sdk_error = error_class(
            "private-upstream-detail", response=httpx.Response(429, request=request),
            body={"secret": "private-upstream-detail"},
        )

    if async_mode:
        client = AsyncMock()
        client.__aenter__.return_value = client
        create = AsyncMock(side_effect=sdk_error)
        client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kwargs: client)
    else:
        client = MagicMock()
        client.__enter__.return_value = client
        client.chat.completions.create.side_effect = sdk_error
        monkeypatch.setattr(llm, "OpenAI", lambda **kwargs: client)

    with pytest.raises(llm.ModelServiceError) as error:
        if async_mode:
            asyncio.run(llm.create_chat_completion(messages=[]))
        else:
            llm.create_sync_chat_completion(messages=[])

    assert error.value.status_code == status
    assert "private-upstream-detail" not in error.value.detail


def test_model_config_sets_bounded_timeout_and_retries():
    config, model = llm.model_config()
    assert config["timeout"] == 20.0
    assert config["max_retries"] == 1
    assert model == "test-model"

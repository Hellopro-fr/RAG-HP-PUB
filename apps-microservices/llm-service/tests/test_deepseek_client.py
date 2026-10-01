"""Tests for the DeepSeek V4 migration in llm-service's DeepSeekClient.

V4 facts under test: deepseek-chat/deepseek-reasoner are retired; thinking is
a request parameter (default ENABLED on v4) — so the client must (a) default
to deepseek-v4-flash, (b) explicitly disable thinking for old deepseek-chat
behavior, (c) enable thinking instead of swapping to the dead reasoner model.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_MODEL_NAME", raising=False)
    from infrastructure.deepseek_client import DeepSeekClient

    c = DeepSeekClient()
    response = Mock()
    message = Mock()
    message.content = "<think>raisonnement</think> réponse finale"
    response.choices = [Mock(message=message)]
    response.model_dump.return_value = {"ok": True}
    c.client.chat.completions.create = AsyncMock(return_value=response)
    return c


def _call(client, enable_thinking):
    return asyncio.run(
        client.get_chat_completion(
            message_history=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=256,
            enable_thinking=enable_thinking,
        )
    )


def test_non_thinking_uses_v4_flash_with_thinking_disabled(client):
    result = _call(client, enable_thinking=False)

    kwargs = client.client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-v4-flash"
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    # <think> strip + whitespace collapse still applied on non-thinking path
    assert result["full_message"] == "réponse finale"


def test_thinking_enables_param_instead_of_dead_reasoner_model(client):
    _call(client, enable_thinking=True)

    kwargs = client.client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] != "deepseek-reasoner"  # retired model name
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_env_var_still_overrides_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL_NAME", "deepseek-v4-pro")
    from infrastructure.deepseek_client import DeepSeekClient

    c = DeepSeekClient()
    response = Mock()
    response.choices = []
    response.model_dump.return_value = {}
    c.client.chat.completions.create = AsyncMock(return_value=response)
    _call(c, enable_thinking=False)

    assert c.client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v4-pro"

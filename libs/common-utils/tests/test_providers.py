"""Tests for the DeepSeek V4 defaults in common_utils.llm.providers."""

import asyncio
from unittest.mock import AsyncMock, Mock

from common_utils.llm.providers import DeepSeekClient


def _mock_response(text="ok"):
    response = Mock()
    message = Mock()
    message.content = text
    response.choices = [Mock(message=message)]
    return response


def test_default_model_is_v4_flash():
    client = DeepSeekClient(api_key="k")
    assert client.model == "deepseek-v4-flash"


def test_generate_disables_thinking_by_default():
    client = DeepSeekClient(api_key="k")
    client.client.chat.completions.create = AsyncMock(return_value=_mock_response())

    out = asyncio.run(client.generate("bonjour", temperature=0.1, max_tokens=8192))

    kwargs = client.client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-v4-flash"
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert kwargs["temperature"] == 0.1
    assert out == "ok"


def test_generate_respects_caller_extra_body():
    client = DeepSeekClient(api_key="k")
    client.client.chat.completions.create = AsyncMock(return_value=_mock_response())

    asyncio.run(client.generate("x", extra_body={"thinking": {"type": "enabled"}}))

    kwargs = client.client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}

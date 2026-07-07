"""Tests for DLQ classification in Consumer._process_message_task."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from website_processor_service.messaging.consumer import Consumer


def _make_consumer():
    return Consumer(connection=Mock(), publisher=Mock())


def _make_message():
    msg = Mock()
    msg.body = json.dumps({"data": {"url": "https://ex.com/page"}}).encode()
    msg.headers = {}
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_recursion_error_is_permanent_straight_to_dlq():
    """Deterministic RecursionError must not burn the 3 transient retries."""
    consumer = _make_consumer()
    consumer._instrumented_processing_logic = AsyncMock(
        side_effect=RecursionError("maximum recursion depth exceeded")
    )
    consumer._send_to_dlq = AsyncMock()
    msg = _make_message()

    await consumer._process_message_task(msg)

    consumer._send_to_dlq.assert_awaited_once()
    _, error, retry_count = consumer._send_to_dlq.await_args.args
    assert isinstance(error, RecursionError)
    assert retry_count == 0
    msg.ack.assert_awaited_once()
    msg.nack.assert_not_awaited()


@pytest.mark.asyncio
async def test_generic_error_still_goes_through_retry_cycle():
    consumer = _make_consumer()
    consumer._instrumented_processing_logic = AsyncMock(side_effect=RuntimeError("transient"))
    consumer._send_to_dlq = AsyncMock()
    msg = _make_message()

    await consumer._process_message_task(msg)

    msg.nack.assert_awaited_once_with(requeue=False)
    consumer._send_to_dlq.assert_not_awaited()
    msg.ack.assert_not_awaited()

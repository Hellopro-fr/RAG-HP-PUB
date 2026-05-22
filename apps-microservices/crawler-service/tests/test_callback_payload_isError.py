"""Unit tests for _read_callback_isError helper in crawler_manager."""
import json
import os
import pytest

from app.core.crawler_manager import _read_callback_isError


@pytest.mark.asyncio
async def test_missing_storage_dir():
    result = await _read_callback_isError('/nonexistent/path/xyz')
    assert result is None


@pytest.mark.asyncio
async def test_missing_payload_file(tmp_path):
    result = await _read_callback_isError(str(tmp_path))
    assert result is None


@pytest.mark.asyncio
async def test_empty_payload_file(tmp_path):
    (tmp_path / '_callback_payload.json').write_text('')
    result = await _read_callback_isError(str(tmp_path))
    assert result is None  # invalid JSON


@pytest.mark.asyncio
async def test_payload_without_isError_key(tmp_path):
    (tmp_path / '_callback_payload.json').write_text(json.dumps({'id_domaine': 123}))
    result = await _read_callback_isError(str(tmp_path))
    assert result is None


@pytest.mark.asyncio
async def test_payload_with_empty_isError(tmp_path):
    (tmp_path / '_callback_payload.json').write_text(json.dumps({'isError': ''}))
    result = await _read_callback_isError(str(tmp_path))
    assert result is None


@pytest.mark.asyncio
async def test_payload_with_stoppedManually(tmp_path):
    (tmp_path / '_callback_payload.json').write_text(
        json.dumps({'isError': 'stoppedManually', 'isFinished': 1})
    )
    result = await _read_callback_isError(str(tmp_path))
    assert result == 'stoppedManually'


@pytest.mark.asyncio
async def test_payload_with_insufficientData(tmp_path):
    (tmp_path / '_callback_payload.json').write_text(json.dumps({'isError': 'insufficientData'}))
    result = await _read_callback_isError(str(tmp_path))
    assert result == 'insufficientData'


@pytest.mark.asyncio
async def test_payload_with_non_string_isError(tmp_path):
    (tmp_path / '_callback_payload.json').write_text(json.dumps({'isError': 42}))
    result = await _read_callback_isError(str(tmp_path))
    assert result is None  # non-string treated as no-error

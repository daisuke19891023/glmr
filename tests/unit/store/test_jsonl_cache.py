"""Tests for the JSONL merge request cache."""

import logging
from pathlib import Path

import orjson
import pendulum
import pytest

from app.store.jsonl_cache import MergeRequestCache
from tests.factories import build_record


def test_cache_skips_invalid_lines(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Invalid cache lines should be logged and ignored."""
    caplog.set_level(logging.WARNING)
    cache_dir = tmp_path
    cache_path = cache_dir / "merge_requests.jsonl"

    reference = pendulum.datetime(2024, 1, 1, tz="UTC")
    valid_record = build_record(reference)

    invalid_json = b"{invalid json}\n"
    invalid_payload = orjson.dumps({}) + b"\n"
    valid_payload = orjson.dumps(valid_record.model_dump(mode="json")) + b"\n"

    cache_path.write_bytes(invalid_json + invalid_payload + valid_payload)

    cache = MergeRequestCache(cache_dir)

    assert len(cache) == 1
    warning_messages = [record.message for record in caplog.records if record.levelno == logging.WARNING]
    assert any("invalid JSON cache line" in message for message in warning_messages)
    assert any("invalid cache record" in message for message in warning_messages)
    assert not cache.should_store(valid_record)

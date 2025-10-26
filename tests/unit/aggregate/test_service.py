"""Tests for the aggregation service."""

import logging

import orjson
import pendulum
import pytest

from app.aggregate.models import build_windows
from app.aggregate.service import AggregationService
from tests.factories import build_record

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from app.models import MergeRequestRecord


def _write_record(path: "Path", record: "MergeRequestRecord") -> None:
    """Persist a merge request record to a JSONL cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json")
    with path.open("wb") as handle:
        handle.write(orjson.dumps(payload))
        handle.write(b"\n")


def test_aggregation_service_produces_windowed_metrics(tmp_path: "Path") -> None:
    """AggregationService should produce counts for each configured window."""
    reference = pendulum.datetime(2024, 1, 15, tz="UTC")
    cache_path = tmp_path / "merge_requests.jsonl"
    output_path = tmp_path / "agg" / "report.json"

    record = build_record(reference)
    _write_record(cache_path, record)

    service = AggregationService(
        cache_path=cache_path,
        output_path=output_path,
        windows=build_windows(),
        reference=reference,
    )

    report = service.run()

    assert output_path.exists()
    stored = orjson.loads(output_path.read_bytes())
    assert stored["windows"] == [window.key for window in build_windows()]

    assert len(report.projects) == 1
    project_metrics = report.projects[0].metrics["7d"]
    assert project_metrics.merge_requests_created == 1
    assert project_metrics.merge_requests_merged == 1
    assert project_metrics.merge_requests_closed == 0
    assert project_metrics.comments_written == 1

    people = {person.user.username: person for person in report.people}
    assert set(people.keys()) == {"alice", "bob"}

    alice_metrics = people["alice"].metrics["7d"]
    assert alice_metrics.merge_requests_created == 1
    assert alice_metrics.merge_requests_merged == 1
    assert alice_metrics.comments_written == 0
    assert people["alice"].recent_merge_requests

    bob_metrics = people["bob"].metrics["7d"]
    assert bob_metrics.comments_written == 1
    assert people["bob"].recent_merge_requests

    assert report.generated_at == reference


def test_aggregation_service_handles_missing_cache(tmp_path: "Path") -> None:
    """AggregationService should produce an empty report when no cache exists."""
    cache_path = tmp_path / "merge_requests.jsonl"
    output_path = tmp_path / "agg" / "report.json"

    service = AggregationService(
        cache_path=cache_path,
        output_path=output_path,
        windows=build_windows(),
        reference=pendulum.datetime(2024, 1, 1, tz="UTC"),
    )

    report = service.run()

    assert output_path.exists()
    assert report.projects == []
    assert report.people == []


def test_aggregation_service_skips_invalid_cache_lines(
    tmp_path: "Path", caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid cache lines should be logged and ignored during aggregation."""
    caplog.set_level(logging.WARNING)
    reference = pendulum.datetime(2024, 2, 1, tz="UTC")
    cache_path = tmp_path / "merge_requests.jsonl"
    output_path = tmp_path / "agg" / "report.json"

    record = build_record(reference)
    invalid_json = b"{invalid json}\n"
    invalid_payload = orjson.dumps({}) + b"\n"
    valid_payload = orjson.dumps(record.model_dump(mode="json")) + b"\n"

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(invalid_json + invalid_payload + valid_payload)

    service = AggregationService(
        cache_path=cache_path,
        output_path=output_path,
        windows=build_windows(),
        reference=reference,
    )

    report = service.run()

    warning_messages = [entry.message for entry in caplog.records if entry.levelno == logging.WARNING]
    assert any("invalid JSON cache line" in message for message in warning_messages)
    assert any("invalid cache record" in message for message in warning_messages)
    assert len(report.projects) == 1

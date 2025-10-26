from __future__ import annotations

import logging
from typing import Self, TYPE_CHECKING

import pytest
import typer

from app import collector as collector_module
from app.collector import MergeRequestCollector
from app.gitlab_client import GitLabAPIError
from tests import factories

if TYPE_CHECKING:
    from pathlib import Path

    from app.config import AppSettings
    from app.models import Project


class FakeGitLabClient:
    """Stand-in async context manager for GitLabClient."""

    def __init__(self, settings: object) -> None:
        """Record initialization arguments for assertions if needed."""
        self.settings = settings

    async def __aenter__(self) -> Self:
        """Return self when entering the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        """Discard exception context when leaving the async manager."""
        del exc_type, exc, tb


class FakeMergeRequestCache:
    """Minimal cache stub used to avoid filesystem writes in tests."""

    def __init__(self, cache_dir: Path, *, filename: str = "merge_requests.jsonl") -> None:
        """Capture initialization metadata for assertions if required."""
        self.cache_dir = cache_dir
        self.filename = filename
        self.upserted: list[object] = []
        self.flushed = False

    def should_store(self, record: object) -> bool:
        """Pretend the cache never needs to store items during tests."""
        del record
        return False

    def upsert(self, record: object) -> None:
        """Record which entries would have been cached."""
        self.upserted.append(record)

    def flush(self) -> None:
        """Mark the cache as flushed when invoked."""
        self.flushed = True


@pytest.mark.asyncio
async def test_run_exits_when_project_listing_fails(
    monkeypatch: pytest.MonkeyPatch,
    settings: AppSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Collector.run should exit with code 1 when project discovery fails."""
    caplog.set_level(logging.ERROR, logger=collector_module.__name__)
    failing_settings = settings.model_copy(update={"cache_dir": tmp_path})
    collector = MergeRequestCollector(failing_settings)

    async def fail_fetch_group_projects(*_: object, **__: object) -> list[object]:
        raise GitLabAPIError("upstream failure")

    monkeypatch.setattr(collector_module, "GitLabClient", FakeGitLabClient)
    monkeypatch.setattr(
        collector_module.projects,
        "fetch_group_projects",
        fail_fetch_group_projects,
    )

    with pytest.raises(typer.Exit) as excinfo:
        await collector.run()

    exit_exception = excinfo.value
    assert isinstance(exit_exception, typer.Exit)
    assert exit_exception.exit_code == 1
    assert "upstream failure" in caplog.text


@pytest.mark.asyncio
async def test_run_skips_project_when_merge_requests_fail(
    monkeypatch: pytest.MonkeyPatch,
    settings: AppSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Collector.run should log a warning and skip projects with API failures."""
    caplog.set_level(logging.WARNING, logger=collector_module.__name__)
    failing_settings = settings.model_copy(update={"cache_dir": tmp_path})
    collector = MergeRequestCollector(failing_settings)
    project = factories.build_project()

    async def fail_fetch_merge_requests(*_: object, **__: object) -> list[object]:
        raise GitLabAPIError("merge request fetch failed")

    async def return_projects(*_: object, **__: object) -> list[Project]:
        return [project]

    monkeypatch.setattr(
        collector_module.merge_requests,
        "fetch_project_merge_requests",
        fail_fetch_merge_requests,
    )
    monkeypatch.setattr(
        collector_module.projects,
        "fetch_group_projects",
        return_projects,
    )
    monkeypatch.setattr(collector_module, "GitLabClient", FakeGitLabClient)
    monkeypatch.setattr(collector_module, "MergeRequestCache", FakeMergeRequestCache)

    summary = await collector.run()

    assert summary == {"projects": 1, "seen": 0, "written": 0}
    assert "merge request fetch failed" in caplog.text

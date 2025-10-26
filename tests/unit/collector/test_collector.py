from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import quote

import pytest
import typer

from app import collector as collector_module
from app.collector import MergeRequestCollector
from app.gitlab_client import GitLabAPIError, GitLabClient
from tests import factories

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Mapping
    from pathlib import Path

    from app.config import AppSettings
    from app.collector import MergeRequestCacheProtocol


class FakeGitLabClient(GitLabClient):
    """Stand-in async context manager for GitLabClient with configurable responses."""

    def __init__(
        self,
        settings: object,
        *,
        responses: Mapping[str, Iterable[dict[str, Any]] | BaseException] | None = None,
    ) -> None:
        """Record initialization arguments for assertions if needed."""
        self.settings = settings
        self._settings = settings
        self.responses: dict[str, Iterable[dict[str, Any]] | BaseException] = dict(responses or {})

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

    async def paginate(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield configured responses or raise errors for specific paths."""
        del method, params, headers
        result = self.responses.get(path, [])
        if isinstance(result, BaseException):
            raise result
        for item in result:
            yield item


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
    settings: AppSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Collector.run should exit with code 1 when project discovery fails."""
    caplog.set_level(logging.ERROR, logger=collector_module.__name__)
    failing_settings = settings.model_copy(update={"cache_dir": tmp_path})
    responses = {
        _group_projects_path(failing_settings): GitLabAPIError("upstream failure"),
    }
    collector = MergeRequestCollector(
        failing_settings,
        client_factory=lambda app_settings: FakeGitLabClient(
            app_settings,
            responses=responses,
        ),
        cache_provider=lambda cache_dir: FakeMergeRequestCache(cache_dir),
    )

    with pytest.raises(typer.Exit) as excinfo:
        await collector.run()

    exit_exception = excinfo.value
    assert isinstance(exit_exception, typer.Exit)
    assert exit_exception.exit_code == 1
    assert "upstream failure" in caplog.text
    captured = capsys.readouterr()
    assert "Failed to fetch projects" in captured.err


@pytest.mark.asyncio
async def test_run_skips_project_when_merge_requests_fail(
    settings: AppSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Collector.run should log a warning and skip projects with API failures."""
    caplog.set_level(logging.WARNING, logger=collector_module.__name__)
    failing_settings = settings.model_copy(update={"cache_dir": tmp_path})
    project = factories.build_project()
    responses = {
        _group_projects_path(failing_settings): [project.model_dump()],
        _project_merge_requests_path(project.id): GitLabAPIError(
            "merge request fetch failed",
        ),
    }
    collector = MergeRequestCollector(
        failing_settings,
        client_factory=lambda app_settings: FakeGitLabClient(
            app_settings,
            responses=responses,
        ),
        cache_provider=lambda cache_dir: FakeMergeRequestCache(cache_dir),
    )

    summary = await collector.run()

    assert summary == {"projects": 1, "seen": 0, "written": 0}
    assert "merge request fetch failed" in caplog.text


@pytest.mark.asyncio
async def test_run_exits_when_cache_initialization_fails(
    settings: AppSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Collector.run should exit when the cache cannot be created."""
    caplog.set_level(logging.ERROR, logger=collector_module.__name__)
    failing_settings = settings.model_copy(update={"cache_dir": tmp_path})
    def cache_factory(_: Path) -> MergeRequestCacheProtocol:
        raise OSError("cache initialization failure")

    collector = MergeRequestCollector(
        failing_settings,
        client_factory=lambda app_settings: FakeGitLabClient(app_settings),
        cache_provider=cache_factory,
    )

    with pytest.raises(typer.Exit) as excinfo:
        await collector.run()

    exit_exception = excinfo.value
    assert exit_exception.exit_code == 1
    assert "cache initialization failure" in caplog.text
    captured = capsys.readouterr()
    assert "cache initialization failure" in captured.err


@pytest.mark.asyncio
async def test_run_exits_when_cache_flush_fails(
    settings: AppSettings,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Collector.run should exit when flushing the cache fails."""
    caplog.set_level(logging.ERROR, logger=collector_module.__name__)
    failing_settings = settings.model_copy(update={"cache_dir": tmp_path})
    class FlushFailingCache(FakeMergeRequestCache):
        def flush(self) -> None:
            raise OSError("cache flush failure")

    collector = MergeRequestCollector(
        failing_settings,
        client_factory=lambda app_settings: FakeGitLabClient(
            app_settings,
            responses={_group_projects_path(failing_settings): []},
        ),
        cache_provider=lambda cache_dir: FlushFailingCache(cache_dir),
    )

    with pytest.raises(typer.Exit) as excinfo:
        await collector.run()

    exit_exception = excinfo.value
    assert exit_exception.exit_code == 1
    assert "cache flush failure" in caplog.text
    captured = capsys.readouterr()
    assert "cache flush failure" in captured.err


def _group_projects_path(settings: AppSettings) -> str:
    return f"/groups/{quote(settings.group_id_or_path, safe='')}/projects"


def _project_merge_requests_path(project_id: int) -> str:
    return f"/projects/{project_id}/merge_requests"

"""Data collection orchestration for GitLab merge requests."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import typer

from app.fetchers import discussions, merge_requests, notes, projects, reviewers
from app.gitlab_client import GitLabAPIError, GitLabClient
from app.models import MergeRequestRecord, Project
from app.store.jsonl_cache import MergeRequestCache

if TYPE_CHECKING:
    from app.config import AppSettings
    from app.models import Discussion, MergeRequest, Note, ReviewerState

LOGGER = logging.getLogger(__name__)

DetailResult = tuple[
    list["Discussion"] | BaseException,
    list["Note"] | BaseException,
    list["ReviewerState"] | BaseException,
]


class MergeRequestCacheProtocol(Protocol):
    """Protocol capturing the cache behaviors used by the collector."""

    def should_store(self, record: MergeRequestRecord) -> bool:
        """Return True when the provided record should update the cache."""
        ...

    def upsert(self, record: MergeRequestRecord) -> None:
        """Insert or update the record inside the cache."""
        ...

    def flush(self) -> None:
        """Persist any pending cache changes to durable storage."""
        ...


class MergeRequestCollector:
    """Collect merge request data, discussions, notes, and reviewers for projects."""

    def __init__(
        self,
        settings: "AppSettings",
        *,
        client_factory: Callable[["AppSettings"], GitLabClient] | None = None,
        cache_provider: MergeRequestCacheProtocol
        | Callable[[Path], MergeRequestCacheProtocol]
        | None = None,
    ) -> None:
        """Initialize the collector with runtime settings."""
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._client_factory: Callable[[AppSettings], GitLabClient]
        self._client_factory = client_factory or GitLabClient
        if cache_provider is None:
            self._cache_factory: Callable[[Path], MergeRequestCacheProtocol] | None = MergeRequestCache
            self._cache_instance: MergeRequestCacheProtocol | None = None
        elif callable(cache_provider):
            self._cache_factory = cache_provider
            self._cache_instance = None
        else:
            self._cache_factory = None
            self._cache_instance = cache_provider

    async def run(self) -> dict[str, int]:
        """Execute the collection workflow, returning summary statistics."""
        try:
            cache = self._resolve_cache()
        except OSError as exc:
            LOGGER.exception(
                "Failed to initialize merge request cache at %s",
                self._settings.cache_dir,
            )
            typer.secho(
                f"Failed to initialize cache at {self._settings.cache_dir}: {exc}",
                err=True,
            )
            raise typer.Exit(1) from exc
        async with self._client_factory(self._settings) as client:
            try:
                project_list = await projects.fetch_group_projects(
                    client,
                    self._settings.group_id_or_path,
                )
            except GitLabAPIError as exc:
                LOGGER.error(
                    "Failed to fetch projects for %s: %s",
                    self._settings.group_id_or_path,
                    exc,
                )
                raise typer.Exit(code=1) from exc
            LOGGER.info("Discovered %s projects with merge requests enabled", len(project_list))
            total_seen = 0
            total_written = 0
            for project in project_list:
                project_records = await self._collect_project(client, project, cache)
                total_seen += project_records["seen"]
                total_written += project_records["written"]
        try:
            cache.flush()
        except OSError as exc:
            LOGGER.exception(
                "Failed to flush merge request cache at %s",
                self._settings.cache_dir,
            )
            typer.secho(
                f"Failed to flush cache at {self._settings.cache_dir}: {exc}",
                err=True,
            )
            raise typer.Exit(1) from exc
        return {"projects": len(project_list), "seen": total_seen, "written": total_written}

    def _resolve_cache(self) -> MergeRequestCacheProtocol:
        """Return a cache instance using either an instance or factory."""
        if self._cache_instance is not None:
            return self._cache_instance
        if self._cache_factory is None:
            msg = "Cache factory is not configured"
            raise RuntimeError(msg)
        return self._cache_factory(self._settings.cache_dir)

    async def _collect_project(
        self,
        client: GitLabClient,
        project: Project,
        cache: MergeRequestCacheProtocol,
    ) -> dict[str, int]:
        LOGGER.debug("Collecting merge requests for project %s", project.path_with_namespace)
        try:
            merge_request_list = await merge_requests.fetch_project_merge_requests(
                client,
                project.id,
                updated_after=self._settings.report_since,
            )
        except GitLabAPIError as exc:
            LOGGER.warning(
                "Skipping project %s due to GitLab API error: %s",
                project.path_with_namespace,
                exc,
            )
            return {"seen": 0, "written": 0}
        LOGGER.debug("Fetched %s merge requests for %s", len(merge_request_list), project.path_with_namespace)
        tasks = [
            asyncio.create_task(self._build_record(client, project, merge_request))
            for merge_request in merge_request_list
        ]
        written = 0
        for task in asyncio.as_completed(tasks):
            record = await task
            if record is None:
                continue
            if cache.should_store(record):
                cache.upsert(record)
                written += 1
        return {"seen": len(merge_request_list), "written": written}

    async def _build_record(
        self,
        client: GitLabClient,
        project: Project,
        merge_request: "MergeRequest",
    ) -> MergeRequestRecord | None:
        async with self._semaphore:
            details: DetailResult = await asyncio.gather(
                discussions.fetch_merge_request_discussions(client, project.id, merge_request.iid),
                notes.fetch_merge_request_notes(client, project.id, merge_request.iid),
                reviewers.fetch_merge_request_reviewers(client, project.id, merge_request.iid),
                return_exceptions=True,
            )
        return _handle_gather_results(details, project, merge_request)


def _handle_gather_results(
    results: DetailResult,
    project: Project,
    merge_request: "MergeRequest",
) -> MergeRequestRecord | None:
    """Convert gather results into a record, logging failures gracefully."""
    discussions_result, notes_result, reviewers_result = results
    for error_candidate in (discussions_result, notes_result, reviewers_result):
        if isinstance(error_candidate, BaseException):
            LOGGER.error(
                "Failed to fetch details for %s!%s: %s",
                project.path_with_namespace,
                merge_request.iid,
                error_candidate,
            )
            return None
    discussions_list = cast("list[Discussion]", discussions_result)
    notes_list = cast("list[Note]", notes_result)
    reviewers_list = cast("list[ReviewerState]", reviewers_result)
    return MergeRequestRecord(
        project=project,
        merge_request=merge_request,
        discussions=discussions_list,
        notes=notes_list,
        reviewers=reviewers_list,
    )

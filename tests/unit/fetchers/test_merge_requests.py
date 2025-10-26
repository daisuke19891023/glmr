"""Tests for merge request fetchers."""

from typing import TYPE_CHECKING

import pytest
from httpx import Response

from app.fetchers.merge_requests import fetch_project_merge_requests
from app.gitlab_client import GitLabClient

if TYPE_CHECKING:
    from app.config import AppSettings
    from respx import MockRouter


@pytest.mark.asyncio
async def test_fetch_project_merge_requests_includes_since(
    settings: "AppSettings",
    respx_mock: "MockRouter",
) -> None:
    """Merge request fetcher should propagate updated_after and pagination parameters."""
    async with GitLabClient(settings) as client:
        route = respx_mock.get(
            "https://gitlab.example.com/api/v4/projects/1/merge_requests",
            params={
                "scope": "all",
                "state": "all",
                "order_by": "updated_at",
                "sort": "desc",
                "updated_after": "2024-01-01T00:00:00Z",
                "per_page": "100",
            },
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 501,
                        "iid": 42,
                        "project_id": 1,
                        "title": "Refactor service module",
                        "state": "opened",
                        "created_at": "2024-01-05T12:00:00Z",
                        "updated_at": "2024-01-06T12:00:00Z",
                        "merged_at": None,
                        "closed_at": None,
                        "web_url": "https://gitlab.example.com/mr/42",
                        "author": {"id": 10, "username": "alice", "name": "Alice"},
                        "assignees": [],
                        "reviewers": [],
                    },
                ],
            ),
        )

        merge_requests = await fetch_project_merge_requests(
            client,
            1,
            updated_after="2024-01-01T00:00:00Z",
        )

    assert len(merge_requests) == 1
    assert merge_requests[0].iid == 42
    assert route.called

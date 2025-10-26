"""Tests for merge request detail fetchers."""

from typing import TYPE_CHECKING
from collections.abc import Awaitable, Callable

import pytest
from httpx import Response

from app.fetchers import discussions, notes, reviewers
from app.gitlab_client import GitLabClient

if TYPE_CHECKING:
    from app.config import AppSettings
    from respx import MockRouter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "path"),
    [
        (discussions.fetch_merge_request_discussions, "/projects/1/merge_requests/42/discussions"),
        (notes.fetch_merge_request_notes, "/projects/1/merge_requests/42/notes"),
        (reviewers.fetch_merge_request_reviewers, "/projects/1/merge_requests/42/reviewers"),
    ],
)
async def test_merge_request_detail_fetchers(
    settings: "AppSettings",
    respx_mock: "MockRouter",
    fetcher: Callable[[GitLabClient, int, int], Awaitable[list[object]]],
    path: str,
) -> None:
    """Detail fetchers should hydrate models from GitLab responses."""
    payload: object = {"id": "thread", "individual_note": False, "notes": []}
    if "notes" in path and "reviewers" not in path:
        payload = {
            "id": 1,
            "body": "Looks good",
            "created_at": "2024-01-05T12:00:00Z",
            "updated_at": None,
            "system": False,
            "author": {"id": 10, "username": "alice", "name": "Alice"},
        }
    if "reviewers" in path:
        payload = {
            "id": 1,
            "user": {"id": 11, "username": "bob", "name": "Bob"},
            "state": "approved",
        }

    async with GitLabClient(settings) as client:
        respx_mock.get(f"https://gitlab.example.com/api/v4{path}").mock(
            return_value=Response(200, json=[payload]),
        )
        result = await fetcher(client, 1, 42)

    assert len(result) == 1

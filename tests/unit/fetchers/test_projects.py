"""Tests for the project fetcher."""

from typing import TYPE_CHECKING

import pytest
from httpx import Response

from app.fetchers.projects import fetch_group_projects
from app.gitlab_client import GitLabClient

if TYPE_CHECKING:
    from app.config import AppSettings
    from respx import MockRouter


@pytest.mark.asyncio
async def test_fetch_group_projects_handles_pagination(
    settings: "AppSettings",
    respx_mock: "MockRouter",
) -> None:
    """Project fetcher should request all pages with expected query parameters."""
    settings = settings.model_copy(update={"group_id_or_path": "example/group"})
    async with GitLabClient(settings) as client:
        route = respx_mock.get(
            "https://gitlab.example.com/api/v4/groups/example%2Fgroup/projects",
            params={
                "include_subgroups": "true",
                "with_merge_requests_enabled": "true",
                "archived": "false",
                "order_by": "last_activity_at",
                "sort": "desc",
                "per_page": "100",
            },
        )
        route.side_effect = [
            Response(
                200,
                json=[{"id": 1, "path_with_namespace": "example/repo", "name": "Repo"}],
                headers={"X-Next-Page": "2"},
            ),
            Response(
                200,
                json=[{"id": 2, "path_with_namespace": "example/other", "name": "Other"}],
            ),
        ]

        projects = await fetch_group_projects(client, "example/group")

    assert [project.id for project in projects] == [1, 2]
    assert route.call_count == 2

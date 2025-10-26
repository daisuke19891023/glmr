"""Merge request fetchers for GitLab projects."""

from typing import TYPE_CHECKING

from app.models import MergeRequest

if TYPE_CHECKING:
    from app.gitlab_client import GitLabClient


async def fetch_project_merge_requests(
    client: "GitLabClient",
    project_id: int,
    *,
    updated_after: str | None = None,
) -> list[MergeRequest]:
    """Return merge requests for a project, optionally filtered by update timestamp."""
    params = {
        "scope": "all",
        "state": "all",
        "order_by": "updated_at",
        "sort": "desc",
    }
    if updated_after:
        params["updated_after"] = updated_after
    return [
        MergeRequest.model_validate(payload)
        async for payload in client.paginate("GET", f"/projects/{project_id}/merge_requests", params=params)
    ]

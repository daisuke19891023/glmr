"""Reviewer fetchers for merge requests."""

from typing import TYPE_CHECKING

from app.models import ReviewerState

if TYPE_CHECKING:
    from app.gitlab_client import GitLabClient


async def fetch_merge_request_reviewers(
    client: "GitLabClient",
    project_id: int,
    merge_request_iid: int,
) -> list[ReviewerState]:
    """Return reviewer state for a merge request if supported by the project."""
    return [
        ReviewerState.model_validate(payload)
        async for payload in client.paginate(
            "GET",
            f"/projects/{project_id}/merge_requests/{merge_request_iid}/reviewers",
        )
    ]

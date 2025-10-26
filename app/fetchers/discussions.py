"""Discussion fetchers for merge requests."""

from typing import TYPE_CHECKING

from app.models import Discussion

if TYPE_CHECKING:
    from app.gitlab_client import GitLabClient


async def fetch_merge_request_discussions(
    client: "GitLabClient",
    project_id: int,
    merge_request_iid: int,
) -> list[Discussion]:
    """Return the discussion threads associated with a merge request."""
    return [
        Discussion.model_validate(payload)
        async for payload in client.paginate(
            "GET",
            f"/projects/{project_id}/merge_requests/{merge_request_iid}/discussions",
        )
    ]

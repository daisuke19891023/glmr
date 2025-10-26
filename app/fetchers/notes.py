"""Note fetchers for merge request review activity."""

from typing import TYPE_CHECKING

from app.models import Note

if TYPE_CHECKING:
    from app.gitlab_client import GitLabClient


async def fetch_merge_request_notes(
    client: "GitLabClient",
    project_id: int,
    merge_request_iid: int,
) -> list[Note]:
    """Return the system and user notes for a merge request."""
    return [
        Note.model_validate(payload)
        async for payload in client.paginate(
            "GET",
            f"/projects/{project_id}/merge_requests/{merge_request_iid}/notes",
        )
    ]

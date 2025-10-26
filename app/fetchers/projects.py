"""Project fetchers for GitLab group hierarchies."""

from urllib.parse import quote
from typing import TYPE_CHECKING

from app.models import Project

if TYPE_CHECKING:
    from app.gitlab_client import GitLabClient


async def fetch_group_projects(
    client: "GitLabClient",
    group_id_or_path: str,
    *,
    include_subgroups: bool = True,
    archived: bool = False,
) -> list[Project]:
    """Return all projects for a group respecting configuration defaults."""
    encoded = quote(group_id_or_path, safe="")
    params = {
        "include_subgroups": str(include_subgroups).lower(),
        "with_merge_requests_enabled": "true",
        "archived": str(archived).lower(),
        "order_by": "last_activity_at",
        "sort": "desc",
    }
    return [
        Project.model_validate(payload)
        async for payload in client.paginate("GET", f"/groups/{encoded}/projects", params=params)
    ]

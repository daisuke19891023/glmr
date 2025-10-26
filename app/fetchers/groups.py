"""Group-level fetchers for GitLab collections."""

from urllib.parse import quote
from typing import TYPE_CHECKING

from app.models import Group

if TYPE_CHECKING:
    from app.gitlab_client import GitLabClient


async def fetch_group(client: "GitLabClient", group_id_or_path: str) -> Group:
    """Fetch metadata about a GitLab group."""
    encoded = quote(group_id_or_path, safe="")
    response = await client.request("GET", f"/groups/{encoded}")
    payload = client.parse_json(response)
    return Group.model_validate(payload)

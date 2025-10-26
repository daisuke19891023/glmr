"""Pydantic models describing GitLab entities used by the collector."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class GitLabUser(BaseModel):
    """Subset of GitLab user metadata used in metrics."""

    id: int
    username: str
    name: str | None = None
    avatar_url: HttpUrl | None = None


def _empty_users() -> list["GitLabUser"]:
    return []


class Group(BaseModel):
    """GitLab group details used to scope project discovery."""

    id: int
    full_path: str
    name: str
    web_url: HttpUrl | None = None


class Project(BaseModel):
    """GitLab project metadata returned from the groups/projects endpoint."""

    id: int
    path_with_namespace: str
    name: str
    web_url: HttpUrl | None = None
    default_branch: str | None = None


class MergeRequest(BaseModel):
    """Core merge request payload fields required for aggregation."""

    id: int
    iid: int
    project_id: int
    title: str
    state: str
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    web_url: HttpUrl | None = None
    author: GitLabUser
    assignees: list[GitLabUser] = Field(default_factory=_empty_users)
    reviewers: list[GitLabUser] = Field(default_factory=_empty_users)
    source_branch: str | None = None
    target_branch: str | None = None


class Note(BaseModel):
    """Individual note or system note associated with a merge request."""

    id: int
    body: str
    created_at: datetime
    updated_at: datetime | None = None
    system: bool
    author: GitLabUser


class Discussion(BaseModel):
    """Merge request discussion thread containing one or more notes."""

    id: str
    individual_note: bool
    notes: list[Note]


def _empty_discussions() -> list[Discussion]:
    return []


def _empty_notes() -> list[Note]:
    return []


class ReviewerState(BaseModel):
    """Reviewer state returned by the GitLab reviewers endpoint."""

    id: int
    state: str
    user: GitLabUser | None = None


def _empty_reviewer_states() -> list[ReviewerState]:
    return []


class MergeRequestRecord(BaseModel):
    """Aggregate record stored in the JSONL cache for a merge request."""

    project: Project
    merge_request: MergeRequest
    discussions: list[Discussion] = Field(default_factory=_empty_discussions)
    notes: list[Note] = Field(default_factory=_empty_notes)
    reviewers: list[ReviewerState] = Field(default_factory=_empty_reviewer_states)
    extras: dict[str, Any] = Field(default_factory=dict)

    def cache_key(self) -> str:
        """Return the composite cache key for the record."""
        return f"{self.merge_request.project_id}#{self.merge_request.iid}"

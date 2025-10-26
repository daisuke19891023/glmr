"""Factories for constructing common domain objects in tests."""

from __future__ import annotations

import pendulum

from app.models import Discussion, GitLabUser, MergeRequest, MergeRequestRecord, Note, Project


def build_project() -> Project:
    """Create a deterministic project instance for testing."""
    return Project(
        id=1,
        path_with_namespace="example/repo",
        name="Example Repo",
    )


def build_users() -> tuple[GitLabUser, GitLabUser]:
    """Return an author and reviewer pair."""
    author = GitLabUser(id=10, username="alice", name="Alice")
    reviewer = GitLabUser(id=11, username="bob", name="Bob")
    return author, reviewer


def build_merge_request(project: Project, reference: pendulum.DateTime) -> MergeRequest:
    """Create a merge request anchored to the provided reference time."""
    author, reviewer = build_users()
    return MergeRequest(
        id=501,
        iid=42,
        project_id=project.id,
        title="Refactor service module",
        state="merged",
        created_at=reference - pendulum.duration(days=3),
        updated_at=reference - pendulum.duration(days=1),
        merged_at=reference - pendulum.duration(days=1),
        closed_at=None,
        web_url=None,
        author=author,
        assignees=[author],
        reviewers=[reviewer],
    )


def build_record(reference: pendulum.DateTime) -> MergeRequestRecord:
    """Assemble a merge request record with associated discussion and note."""
    project = build_project()
    merge_request = build_merge_request(project, reference)
    reviewer = merge_request.reviewers[0]
    note = Note(
        id=900,
        body="LGTM",
        created_at=reference - pendulum.duration(days=1),
        updated_at=None,
        system=False,
        author=reviewer,
    )
    discussion = Discussion(id="disc", individual_note=False, notes=[note])
    return MergeRequestRecord(
        project=project,
        merge_request=merge_request,
        discussions=[discussion],
        notes=[],
    )

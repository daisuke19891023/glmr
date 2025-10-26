"""Models representing aggregated report structures."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, Field


class TimeWindow(BaseModel):
    """A normalized time window used for aggregation."""

    key: str
    delta: timedelta | None = Field(
        default=None,
        description="Timedelta representing the length of the window. None indicates all-time.",
    )

    def includes(self, timestamp: datetime, *, reference: datetime) -> bool:
        """Return True when the timestamp falls inside the window."""
        if self.delta is None:
            return True
        return timestamp >= reference - self.delta


class MetricTotals(BaseModel):
    """Common metric counts captured for windows."""

    merge_requests_created: int = 0
    merge_requests_merged: int = 0
    merge_requests_closed: int = 0
    comments_written: int = 0

    def add(self, other: MetricTotals) -> MetricTotals:
        """Return a new MetricTotals representing the sum with another instance."""
        return MetricTotals(
            merge_requests_created=self.merge_requests_created + other.merge_requests_created,
            merge_requests_merged=self.merge_requests_merged + other.merge_requests_merged,
            merge_requests_closed=self.merge_requests_closed + other.merge_requests_closed,
            comments_written=self.comments_written + other.comments_written,
        )


class UserSummary(BaseModel):
    """Trimmed user details retained for reporting."""

    id: int
    username: str
    name: str | None = None
    avatar_url: str | None = None


class ProjectSummary(BaseModel):
    """Minimal project representation for aggregated reports."""

    id: int
    path_with_namespace: str
    name: str
    web_url: str | None = None


class MergeRequestSummary(BaseModel):
    """Compact representation of a merge request for listing in reports."""

    id: int
    iid: int
    project_id: int
    project_path: str
    title: str
    created_at: datetime
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    web_url: str | None = None


def _empty_merge_request_summaries() -> list[MergeRequestSummary]:
    return []


class PersonReport(BaseModel):
    """Aggregated metrics for a GitLab user."""

    user: UserSummary
    metrics: dict[str, MetricTotals]
    recent_merge_requests: list[MergeRequestSummary] = Field(default_factory=_empty_merge_request_summaries)


class ProjectReport(BaseModel):
    """Aggregated metrics for a project."""

    project: ProjectSummary
    metrics: dict[str, MetricTotals]


class Report(BaseModel):
    """Top-level aggregation report."""

    generated_at: datetime
    windows: list[str]
    projects: list[ProjectReport]
    people: list[PersonReport]

    def window_keys(self) -> list[str]:
        """Return the ordered window keys configured for the report."""
        return list(self.windows)


def build_windows() -> list[TimeWindow]:
    """Return canonical aggregation windows."""
    return [
        TimeWindow(key="7d", delta=timedelta(days=7)),
        TimeWindow(key="30d", delta=timedelta(days=30)),
        TimeWindow(key="90d", delta=timedelta(days=90)),
        TimeWindow(key="all", delta=None),
    ]

"""Aggregation service turning raw merge request records into reporting metrics."""

from __future__ import annotations

from collections import defaultdict
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import orjson
import pendulum
from pydantic import ValidationError

from app.aggregate.models import (
    MetricTotals,
    MergeRequestSummary,
    PersonReport,
    ProjectReport,
    ProjectSummary,
    Report,
    TimeWindow,
    UserSummary,
    build_windows,
)
from app.models import GitLabUser, MergeRequestRecord, Project

if TYPE_CHECKING:
    from datetime import datetime


LOGGER = logging.getLogger(__name__)


class AggregationService:
    """Load cached merge request data and produce an aggregated report."""

    def __init__(
        self,
        *,
        cache_path: Path,
        output_path: Path,
        windows: list[TimeWindow] | None = None,
        reference: datetime | None = None,
    ) -> None:
        """Configure the aggregation service with input/output paths and windows."""
        self._cache_path = Path(cache_path)
        self._output_path = Path(output_path)
        self._windows = list(windows or build_windows())
        self._reference = reference or pendulum.now("UTC")

    def run(self) -> Report:
        """Execute aggregation and write the resulting report to disk."""
        records = self._load_records()
        report = self._build_report(records)
        self._write_report(report)
        return report

    def _load_records(self) -> list[MergeRequestRecord]:
        if not self._cache_path.exists():
            return []
        records: list[MergeRequestRecord] = []
        with self._cache_path.open("rb") as handle:
            for index, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = orjson.loads(line)
                except orjson.JSONDecodeError as error:
                    LOGGER.warning(
                        "Skipping invalid JSON cache line %s:%s: %s",
                        self._cache_path,
                        index,
                        error,
                    )
                    continue
                try:
                    record = MergeRequestRecord.model_validate(payload)
                except ValidationError as error:
                    LOGGER.warning(
                        "Skipping invalid cache record %s:%s: %s",
                        self._cache_path,
                        index,
                        error,
                    )
                    continue
                records.append(record)
        return records

    def _build_report(self, records: list[MergeRequestRecord]) -> Report:
        project_metrics: dict[int, dict[str, MetricTotals]] = defaultdict(lambda: defaultdict(MetricTotals))
        person_metrics: dict[int, dict[str, MetricTotals]] = defaultdict(lambda: defaultdict(MetricTotals))
        recent_by_person: dict[int, dict[int, MergeRequestSummary]] = defaultdict(dict)
        projects: dict[int, ProjectSummary] = {}
        users: dict[int, UserSummary] = {}

        for record in records:
            projects[record.project.id] = self._project_summary(record.project)
            self._aggregate_project_metrics(project_metrics[record.project.id], record)
            self._aggregate_person_metrics(person_metrics, recent_by_person, record)
            for contributor in self._collect_contributors(record):
                users[contributor.id] = self._user_summary(contributor)

        project_reports: list[ProjectReport] = [
            ProjectReport(project=projects[project_id], metrics=dict(metrics))
            for project_id, metrics in sorted(project_metrics.items())
        ]

        person_reports: list[PersonReport] = []
        for user_id, metrics in sorted(person_metrics.items()):
            if not metrics:
                continue
            user = users.get(user_id)
            if user is None:
                continue
            person_reports.append(
                PersonReport(
                    user=user,
                    metrics=dict(metrics),
                    recent_merge_requests=sorted(
                        recent_by_person[user_id].values(),
                        key=lambda summary: summary.created_at,
                        reverse=True,
                    )[:10],
                ),
            )

        return Report(
            generated_at=self._reference,
            windows=[window.key for window in self._windows],
            projects=project_reports,
            people=person_reports,
        )

    def _collect_contributors(self, record: MergeRequestRecord) -> list[GitLabUser]:
        contributors: list[GitLabUser] = [record.merge_request.author]
        contributors.extend(record.merge_request.reviewers)
        contributors.extend(record.merge_request.assignees)
        for discussion in record.discussions:
            contributors.extend(note.author for note in discussion.notes)
        contributors.extend(note.author for note in record.notes)
        return contributors

    def _aggregate_project_metrics(self, metrics: dict[str, MetricTotals], record: MergeRequestRecord) -> None:
        for window in self._windows:
            totals = metrics.setdefault(window.key, MetricTotals())
            totals.merge_requests_created += self._count_if(record.merge_request.created_at, window)
            if record.merge_request.merged_at:
                totals.merge_requests_merged += self._count_if(record.merge_request.merged_at, window)
            if record.merge_request.closed_at:
                totals.merge_requests_closed += self._count_if(record.merge_request.closed_at, window)
            totals.comments_written += self._count_discussion_comments(record, window)

    def _aggregate_person_metrics(
        self,
        metrics: dict[int, dict[str, MetricTotals]],
        recent: dict[int, dict[int, MergeRequestSummary]],
        record: MergeRequestRecord,
    ) -> None:
        summary = self._merge_request_summary(record)
        author_id = record.merge_request.author.id
        for window in self._windows:
            totals = metrics[author_id].setdefault(window.key, MetricTotals())
            totals.merge_requests_created += self._count_if(record.merge_request.created_at, window)
            if record.merge_request.merged_at:
                totals.merge_requests_merged += self._count_if(record.merge_request.merged_at, window)
            if record.merge_request.closed_at:
                totals.merge_requests_closed += self._count_if(record.merge_request.closed_at, window)
        if self._count_if(record.merge_request.created_at, self._windows[-1]):
            recent[author_id][summary.id] = summary

        for discussion in record.discussions:
            for note in discussion.notes:
                if note.system:
                    continue
                user_id = note.author.id
                for window in self._windows:
                    totals = metrics[user_id].setdefault(window.key, MetricTotals())
                    totals.comments_written += self._count_if(note.created_at, window)
                recent[user_id][summary.id] = summary

    def _count_discussion_comments(self, record: MergeRequestRecord, window: TimeWindow) -> int:
        count = 0
        for discussion in record.discussions:
            for note in discussion.notes:
                if note.system:
                    continue
                count += self._count_if(note.created_at, window)
        return count

    def _count_if(self, timestamp: datetime, window: TimeWindow) -> int:
        return int(window.includes(timestamp, reference=self._reference))

    def _write_report(self, report: Report) -> None:
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        self._output_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))

    def _project_summary(self, project: Project) -> ProjectSummary:
        return ProjectSummary(
            id=project.id,
            path_with_namespace=project.path_with_namespace,
            name=project.name,
            web_url=str(project.web_url) if project.web_url else None,
        )

    def _user_summary(self, user: GitLabUser) -> UserSummary:
        return UserSummary(
            id=user.id,
            username=user.username,
            name=user.name,
            avatar_url=str(user.avatar_url) if user.avatar_url else None,
        )

    def _merge_request_summary(self, record: MergeRequestRecord) -> MergeRequestSummary:
        merge_request = record.merge_request
        project = record.project
        return MergeRequestSummary(
            id=merge_request.id,
            iid=merge_request.iid,
            project_id=project.id,
            project_path=project.path_with_namespace,
            title=merge_request.title,
            created_at=merge_request.created_at,
            merged_at=merge_request.merged_at,
            closed_at=merge_request.closed_at,
            web_url=str(merge_request.web_url) if merge_request.web_url else None,
        )

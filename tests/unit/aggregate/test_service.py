from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import pendulum

from app.aggregate.models import build_windows
from app.aggregate.service import AggregationService
from app.models import Discussion, GitLabUser, MergeRequest, MergeRequestRecord, Note, Project


if TYPE_CHECKING:
    from pathlib import Path


def _write_record(path: Path, record: MergeRequestRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json")
    with path.open("wb") as handle:
        handle.write(orjson.dumps(payload))
        handle.write(b"\n")


def test_aggregation_service_produces_windowed_metrics(tmp_path: Path) -> None:
    """AggregationService should produce counts for each configured window."""
    reference = pendulum.datetime(2024, 1, 15, tz="UTC")
    cache_path = tmp_path / "merge_requests.jsonl"
    output_path = tmp_path / "agg" / "report.json"

    project = Project(id=1, path_with_namespace="example/repo", name="Example Repo")
    author = GitLabUser(id=10, username="alice", name="Alice")
    reviewer = GitLabUser(id=11, username="bob", name="Bob")

    merge_request = MergeRequest(
        id=101,
        iid=7,
        project_id=project.id,
        title="Improve build pipeline",
        state="merged",
        created_at=reference - pendulum.duration(days=5),
        updated_at=reference - pendulum.duration(days=1),
        merged_at=reference - pendulum.duration(days=2),
        closed_at=None,
        web_url=None,
        author=author,
        assignees=[author],
        reviewers=[reviewer],
    )

    note = Note(
        id=400,
        body="Looks good!",
        created_at=reference - pendulum.duration(days=1),
        updated_at=None,
        system=False,
        author=reviewer,
    )
    discussion = Discussion(id="abc", individual_note=False, notes=[note])

    record = MergeRequestRecord(
        project=project,
        merge_request=merge_request,
        discussions=[discussion],
        notes=[],
    )
    _write_record(cache_path, record)

    service = AggregationService(
        cache_path=cache_path,
        output_path=output_path,
        windows=build_windows(),
        reference=reference,
    )

    report = service.run()

    assert output_path.exists()
    stored = orjson.loads(output_path.read_bytes())
    assert stored["windows"] == [window.key for window in build_windows()]

    assert len(report.projects) == 1
    project_metrics = report.projects[0].metrics["7d"]
    assert project_metrics.merge_requests_created == 1
    assert project_metrics.merge_requests_merged == 1
    assert project_metrics.merge_requests_closed == 0
    assert project_metrics.comments_written == 1

    people = {person.user.username: person for person in report.people}
    assert set(people.keys()) == {"alice", "bob"}

    alice_metrics = people["alice"].metrics["7d"]
    assert alice_metrics.merge_requests_created == 1
    assert alice_metrics.merge_requests_merged == 1
    assert alice_metrics.comments_written == 0
    assert people["alice"].recent_merge_requests

    bob_metrics = people["bob"].metrics["7d"]
    assert bob_metrics.comments_written == 1
    assert people["bob"].recent_merge_requests

    assert report.generated_at == reference

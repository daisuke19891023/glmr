from __future__ import annotations

from pathlib import Path

import orjson
import pendulum

from app.aggregate.service import AggregationService
from app.models import Discussion, GitLabUser, MergeRequest, MergeRequestRecord, Note, Project
from app.render.service import RenderService


def _create_record(reference: pendulum.DateTime) -> MergeRequestRecord:
    project = Project(id=1, path_with_namespace="example/repo", name="Example Repo")
    author = GitLabUser(id=10, username="alice", name="Alice")
    reviewer = GitLabUser(id=11, username="bob", name="Bob")
    merge_request = MergeRequest(
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


def _write_cache(cache_path: Path, record: MergeRequestRecord) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json")
    with cache_path.open("wb") as handle:
        handle.write(orjson.dumps(payload))
        handle.write(b"\n")


def test_render_service_builds_static_site(tmp_path: Path) -> None:
    """RenderService should emit HTML, assets, and a manifest for the report."""
    reference = pendulum.datetime(2024, 2, 1, tz="UTC")
    cache_path = tmp_path / "merge_requests.jsonl"
    report_path = tmp_path / "agg" / "report.json"
    _write_cache(cache_path, _create_record(reference))

    aggregation = AggregationService(
        cache_path=cache_path,
        output_path=report_path,
        reference=reference,
    )
    aggregation.run()

    build_dir = tmp_path / "build"
    public_dir = tmp_path / "public"
    templates = Path("app/templates")
    static_dir = Path("app/render/static")

    renderer = RenderService(
        report_path=report_path,
        template_dir=templates,
        static_dir=static_dir,
        build_dir=build_dir,
        public_dir=public_dir,
    )
    manifest = renderer.run()

    index_html = public_dir / "index.html"
    person_html = public_dir / "people" / "alice.html"
    styles_css = public_dir / "static" / "styles.css"
    manifest_path = public_dir / "manifest.json"

    assert index_html.exists()
    assert person_html.exists()
    assert styles_css.exists()
    assert manifest_path.exists()

    manifest_payload = orjson.loads(manifest_path.read_bytes())
    assert manifest_payload == manifest
    for key in ("index.html", "people/alice.html", "static/styles.css"):
        assert key in manifest_payload

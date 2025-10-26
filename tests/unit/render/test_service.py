from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import orjson
import pendulum
import app.render.service as render_module
from app.aggregate.service import AggregationService
from app.render.service import RenderService
from tests.factories import build_record

if TYPE_CHECKING:
    from app.models import MergeRequestRecord
    import pytest


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
    _write_cache(cache_path, build_record(reference))

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


def test_render_service_skips_unmodified_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RenderService should avoid copying unchanged files into the public directory."""
    reference = pendulum.datetime(2024, 2, 1, tz="UTC")
    cache_path = tmp_path / "merge_requests.jsonl"
    report_path = tmp_path / "agg" / "report.json"
    _write_cache(cache_path, build_record(reference))

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

    copy_calls: list[tuple[Path, Path]] = []
    original_copy2 = render_module.shutil.copy2

    def spy_copy2(src: str | Path, dst: str | Path, *, follow_symlinks: bool = True) -> Path:
        path_src = Path(src)
        path_dst = Path(dst)
        copy_calls.append((path_src, path_dst))
        result = original_copy2(path_src, path_dst, follow_symlinks=follow_symlinks)
        return Path(result)

    monkeypatch.setattr(render_module.shutil, "copy2", spy_copy2)

    renderer.run()
    public_calls_first = [call for call in copy_calls if call[1].is_relative_to(public_dir)]
    assert public_calls_first

    copy_calls.clear()
    renderer.run()
    public_calls_second = [call for call in copy_calls if call[1].is_relative_to(public_dir)]
    assert public_calls_second == []


def test_render_service_escapes_script_payload(tmp_path: Path) -> None:
    """Ensure rendered JSON data escapes closing script tags."""
    reference = pendulum.datetime(2024, 2, 1, tz="UTC")
    cache_path = tmp_path / "merge_requests.jsonl"
    report_path = tmp_path / "agg" / "report.json"

    malicious_title = "Security </script> check"
    record = build_record(reference)
    patched_record = record.model_copy(
        update={
            "merge_request": record.merge_request.model_copy(update={"title": malicious_title}),
        },
    )
    _write_cache(cache_path, patched_record)

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
    renderer.run()

    index_html = public_dir / "index.html"
    payload = index_html.read_text(encoding="utf-8")
    script_match = re.search(
        r"<script id=\"report-data\" type=\"application/json\">(.*?)</script>",
        payload,
        re.DOTALL,
    )
    assert script_match is not None
    script_payload = script_match.group(1)

    assert "</script>" not in script_payload
    assert "\\u003c/script" in script_payload


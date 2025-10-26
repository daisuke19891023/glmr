"""Rendering pipeline for GLMR static dashboards."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import orjson
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.aggregate.models import PersonReport, Report


class RenderService:
    """Render aggregated reports into static HTML and publish with diff awareness."""

    def __init__(
        self,
        *,
        report_path: Path,
        template_dir: Path,
        static_dir: Path,
        build_dir: Path,
        public_dir: Path,
    ) -> None:
        """Initialise a renderer pointing at the report, template, and output directories."""
        self._report_path = Path(report_path)
        self._template_dir = Path(template_dir)
        self._static_dir = Path(static_dir)
        self._build_dir = Path(build_dir)
        self._public_dir = Path(public_dir)
        self._env = Environment(
            loader=FileSystemLoader(self._template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def run(self) -> dict[str, str]:
        """Render the report and publish updated artifacts."""
        report = self._load_report()
        self._prepare_build_dir()
        self._render_index(report)
        self._render_people(report.people, window_keys=list(report.window_keys()))
        self._copy_static_assets()
        return self._publish()

    def _load_report(self) -> Report:
        if not self._report_path.exists():
            msg = f"Aggregated report not found at {self._report_path}"
            raise FileNotFoundError(msg)
        payload = orjson.loads(self._report_path.read_bytes())
        return Report.model_validate(payload)

    def _prepare_build_dir(self) -> None:
        if self._build_dir.exists():
            shutil.rmtree(self._build_dir)
        self._build_dir.mkdir(parents=True, exist_ok=True)

    def _render_index(self, report: Report) -> None:
        template = self._env.get_template("index.html.j2")
        target = self._build_dir / "index.html"
        target.write_text(
            template.render(
                report=report,
                window_keys=list(report.window_keys()),
                report_json=self._encode_json(report),
            ),
            encoding="utf-8",
        )

    def _render_people(self, people: list[PersonReport], window_keys: list[str]) -> None:
        template = self._env.get_template("person.html.j2")
        people_dir = self._build_dir / "people"
        people_dir.mkdir(parents=True, exist_ok=True)
        for person in people:
            target = people_dir / f"{person.user.username}.html"
            target.write_text(
                template.render(
                    person=person,
                    window_keys=window_keys,
                ),
                encoding="utf-8",
            )

    def _copy_static_assets(self) -> None:
        if not self._static_dir.exists():
            return
        target_dir = self._build_dir / "static"
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in self._static_dir.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(self._static_dir)
            destination = target_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def _publish(self) -> dict[str, str]:
        build_hashes = self._compute_hashes(self._build_dir)
        self._public_dir.mkdir(parents=True, exist_ok=True)
        for relative, checksum in build_hashes.items():
            source = self._build_dir / relative
            destination = self._public_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or self._hash_file(destination) != checksum:
                shutil.copy2(source, destination)
        manifest_path = self._public_dir / "manifest.json"
        manifest_payload = json.dumps(build_hashes, indent=2)
        manifest_path.write_text(manifest_payload, encoding="utf-8")
        return build_hashes

    def _compute_hashes(self, root: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for file_path in sorted(p for p in root.rglob("*") if p.is_file()):
            relative = file_path.relative_to(root).as_posix()
            hashes[relative] = self._hash_file(file_path)
        return hashes

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _encode_json(self, report: Report) -> str:
        return orjson.dumps(report.model_dump(mode="json"), option=orjson.OPT_INDENT_2).decode()

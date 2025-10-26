"""JSONL cache helpers for merge request collection."""

from __future__ import annotations

from pathlib import Path

import orjson
import pendulum

from app.models import MergeRequestRecord


class MergeRequestCache:
    """Persist merge request records as JSONL keyed by `project_id#iid`."""

    def __init__(self, cache_dir: Path, *, filename: str = "merge_requests.jsonl") -> None:
        """Create a cache instance backed by the provided directory."""
        self._path = Path(cache_dir) / filename
        self._records: dict[str, MergeRequestRecord] = {}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def __len__(self) -> int:
        """Return the number of cached merge request records."""
        return len(self._records)

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("rb") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = orjson.loads(line)
                record = MergeRequestRecord.model_validate(payload)
                self._records[record.cache_key()] = record

    def should_store(self, record: MergeRequestRecord) -> bool:
        """Return True when the cache should be updated with the record."""
        existing = self._records.get(record.cache_key())
        if existing is None:
            return True
        existing_updated = pendulum.instance(existing.merge_request.updated_at)
        incoming_updated = pendulum.instance(record.merge_request.updated_at)
        return incoming_updated > existing_updated

    def upsert(self, record: MergeRequestRecord) -> None:
        """Insert or update the stored record."""
        self._records[record.cache_key()] = record

    def flush(self) -> None:
        """Write the cache back to disk as JSONL."""
        ordered = sorted(
            self._records.values(),
            key=lambda record: (record.merge_request.project_id, record.merge_request.iid),
        )
        if not ordered:
            self._path.write_bytes(b"")
            return
        with self._path.open("wb") as handle:
            for entry in ordered:
                handle.write(orjson.dumps(entry.model_dump(mode="json")))
                handle.write(b"\n")

"""PostgreSQL storage for Open Jobs generations and their provenance.

The collector keeps source bytes outside this module.  This module records
the content address, the release that selected it, and the small mutable heads
needed by an operator to find the current release or inspect a link.  It does
not parse a posting into canonical evidence and never commits for its caller;
the caller owns one unit-of-work transaction.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, default=str)


def _stable_id(prefix: str, *parts: object) -> str:
    material = "\0".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _decode_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class OpenJobsStore:
    """Small SQL boundary for migration ``0114_open_jobs``.

    The connection is supplied by the worker so PostgreSQL's normal
    transaction and connection lifecycle remain visible to the caller.  This
    also keeps the helpers usable in offline tests with a recording
    connection, without introducing a second database abstraction.
    """

    def __init__(self, conn: Any):
        self.conn = conn

    def provenance(
        self,
        source_url: str,
        payload_sha256: str,
        *,
        fetched_at: str | None = None,
        archived_path: str | None = None,
        http_status: int | None = None,
        content_type: str | None = None,
        byte_size: int | None = None,
        metadata: dict[str, Any] | None = None,
        provenance_id: str | None = None,
    ) -> str:
        """Record one fetched payload and return its stable provenance id.

        A repeated observation of the same URL and bytes is idempotent.  The
        id derives from that pair so callers can retry after a connection
        failure without making a second logical provenance row.
        """
        pid = provenance_id or _stable_id("oj-prov", source_url, payload_sha256)
        self.conn.execute(
            "INSERT INTO open_jobs_provenance "
            "(provenance_id, source_url, fetched_at, payload_sha256, archived_path, "
            "http_status, content_type, byte_size, metadata_json, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (source_url, payload_sha256) DO NOTHING",
            (pid, source_url, fetched_at or _now(), payload_sha256, archived_path,
             http_status, content_type, byte_size, _json(metadata), _now()),
        )
        return pid

    def generation(
        self,
        source_name: str,
        source_url: str,
        *,
        generation_id: str | None = None,
        started_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Open a collector generation and return its id."""
        gid = generation_id or _new_id("oj-generation")
        self.conn.execute(
            "INSERT INTO open_jobs_generations "
            "(generation_id, source_name, source_url, started_at, status, metadata_json) "
            "VALUES (%s, %s, %s, %s, 'running', %s) "
            "ON CONFLICT (generation_id) DO NOTHING",
            (gid, source_name, source_url, started_at or _now(), _json(metadata)),
        )
        return gid

    def finish_generation(
        self,
        generation_id: str,
        *,
        status: str = "complete",
        record_count: int | None = None,
        error_text: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        if status not in {"complete", "failed", "partial"}:
            raise ValueError(f"invalid Open Jobs generation status: {status!r}")
        self.conn.execute(
            "UPDATE open_jobs_generations SET finished_at = %s, status = %s, "
            "record_count = %s, error_text = %s WHERE generation_id = %s",
            (finished_at or _now(), status, record_count, error_text, generation_id),
        )

    def release(
        self,
        generation_id: str,
        release_version: str | None = None,
        *,
        release_id: str | None = None,
        schema_version: str = "v1",
        parent_release: str | None = None,
        content_sha256: str | None = None,
        expected_rows: int | None = None,
        status: str = "candidate",
        record_count: int | None = None,
        manifest_sha256: str | None = None,
        published_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create an idempotent release row for a generation."""
        if status not in {"candidate", "released", "withdrawn"}:
            raise ValueError(f"invalid Open Jobs release status: {status!r}")
        # `release_id` is normally the source's release anchor.  The fallback
        # keeps this helper useful for a local fixture that only has a version.
        version = release_version or release_id
        if not version:
            raise ValueError("an Open Jobs release needs release_id or release_version")
        rid = release_id or _stable_id("oj-release", generation_id, version)
        self.conn.execute(
            "INSERT INTO open_jobs_releases "
            "(release_id, generation_id, release_version, schema_version, parent_release, "
            "content_sha256, expected_rows, status, record_count, manifest_sha256, "
            "published_at, metadata_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (generation_id, release_version) DO NOTHING",
            (rid, generation_id, version, schema_version, parent_release,
             content_sha256, expected_rows, status, record_count, manifest_sha256,
             published_at, _json(metadata)),
        )
        return rid

    def set_release_status(
        self, release_id: str, *, status: str, published_at: str | None = None
    ) -> None:
        if status not in {"candidate", "released", "withdrawn"}:
            raise ValueError(f"invalid Open Jobs release status: {status!r}")
        self.conn.execute(
            "UPDATE open_jobs_releases SET status = %s, published_at = %s "
            "WHERE release_id = %s", (status, published_at, release_id),
        )

    def artifact(
        self,
        provenance_id: str,
        artifact_kind: str,
        storage_path: str,
        byte_size: int,
        sha256: str,
        *,
        artifact_id: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Register an archived artifact by content hash."""
        aid = artifact_id or _stable_id("oj-artifact", artifact_kind, sha256)
        self.conn.execute(
            "INSERT INTO open_jobs_artifacts "
            "(artifact_id, provenance_id, artifact_kind, storage_path, byte_size, "
            "sha256, content_type, metadata_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (artifact_kind, sha256) DO NOTHING",
            (aid, provenance_id, artifact_kind, storage_path, byte_size, sha256,
             content_type, _json(metadata)),
        )
        return aid

    def bind_artifact(
        self,
        release_id: str,
        artifact_id: str,
        binding_kind: str,
        *,
        ordinal: int | None = None,
        binding_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        bid = binding_id or _stable_id(
            "oj-binding", release_id, artifact_id, binding_kind
        )
        self.conn.execute(
            "INSERT INTO open_jobs_bindings "
            "(binding_id, release_id, artifact_id, binding_kind, ordinal, metadata_json) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (release_id, artifact_id, binding_kind) DO NOTHING",
            (bid, release_id, artifact_id, binding_kind, ordinal, _json(metadata)),
        )
        return bid

    def set_current(
        self,
        current_key: str,
        source_name: str,
        *,
        generation_id: str | None = None,
        release_id: str | None = None,
        artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        updated_at: str | None = None,
    ) -> None:
        if generation_id is None and release_id is None and artifact_id is None:
            raise ValueError("an Open Jobs current pointer needs a target")
        self.conn.execute(
            "INSERT INTO open_jobs_current "
            "(current_key, source_name, generation_id, release_id, artifact_id, updated_at, metadata_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (current_key) DO UPDATE SET source_name = excluded.source_name, "
            "generation_id = excluded.generation_id, release_id = excluded.release_id, "
            "artifact_id = excluded.artifact_id, updated_at = excluded.updated_at, "
            "metadata_json = excluded.metadata_json",
            (current_key, source_name, generation_id, release_id, artifact_id,
             updated_at or _now(), _json(metadata)),
        )

    def set_link_state(
        self,
        source_name: str,
        job_key: str,
        link_url: str,
        state: str,
        *,
        checked_at: str | None = None,
        http_status: int | None = None,
        error_text: str | None = None,
        provenance_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        link_key: str | None = None,
    ) -> str:
        if state not in {"unknown", "live", "gone", "redirected", "blocked", "error"}:
            raise ValueError(f"invalid Open Jobs link state: {state!r}")
        key = link_key or _stable_id("oj-link", source_name, job_key)
        self.conn.execute(
            "INSERT INTO open_jobs_link_state "
            "(link_key, source_name, job_key, link_url, state, checked_at, http_status, "
            "error_text, provenance_id, metadata_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (source_name, job_key) DO UPDATE SET link_key = excluded.link_key, "
            "link_url = excluded.link_url, state = excluded.state, checked_at = excluded.checked_at, "
            "http_status = excluded.http_status, error_text = excluded.error_text, "
            "provenance_id = excluded.provenance_id, metadata_json = excluded.metadata_json",
            (key, source_name, job_key, link_url, state, checked_at or _now(),
             http_status, error_text, provenance_id, _json(metadata)),
        )
        return key

    def upsert_advert(
        self,
        ats: str,
        slug: str,
        upstream_id: str,
        generation_id: str,
        release_id: str,
        operation: str,
        *,
        advert_id: str | None = None,
        removal_reason: str | None = None,
        provenance_id: str | None = None,
        source_url: str | None = None,
        title: str | None = None,
        company: str | None = None,
        location: str | None = None,
        published_at: str | None = None,
        first_seen_at: str | None = None,
        last_seen_at: str | None = None,
        changed_at: str | None = None,
        removed_at: str | None = None,
        payload: dict[str, Any] | None = None,
        updated_at: str | None = None,
    ) -> str:
        """Write the latest source-shaped advert observation."""
        if operation not in {"added", "changed", "changed_prev", "removed", "carried"}:
            raise ValueError(f"invalid Open Jobs operation: {operation!r}")
        if removal_reason not in {None, "closed", "left_dataset", "unknown"}:
            raise ValueError(f"invalid Open Jobs removal reason: {removal_reason!r}")
        if not provenance_id:
            raise ValueError("an Open Jobs advert needs provenance_id")
        aid = advert_id or _stable_id("oj-advert", ats, slug, upstream_id)
        self.conn.execute(
            "INSERT INTO open_jobs_adverts "
            "(advert_id, ats, slug, upstream_id, generation_id, release_id, provenance_id, "
            "operation, removal_reason, source_url, title, company, location, published_at, "
            "first_seen_at, last_seen_at, changed_at, removed_at, payload_json, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (ats, slug, upstream_id) DO UPDATE SET "
            "generation_id = excluded.generation_id, release_id = excluded.release_id, "
            "provenance_id = excluded.provenance_id, operation = excluded.operation, "
            "removal_reason = excluded.removal_reason, "
            "source_url = COALESCE(excluded.source_url, open_jobs_adverts.source_url), "
            "title = COALESCE(excluded.title, open_jobs_adverts.title), "
            "company = COALESCE(excluded.company, open_jobs_adverts.company), "
            "location = COALESCE(excluded.location, open_jobs_adverts.location), "
            "published_at = COALESCE(excluded.published_at, open_jobs_adverts.published_at), "
            "first_seen_at = COALESCE(excluded.first_seen_at, open_jobs_adverts.first_seen_at), "
            # A carried row is an export copy, not a fresh employer/crawler
            # confirmation. Preserve prior timestamps and descriptive fields
            # when the carry-forward payload omits them.
            "last_seen_at = COALESCE(excluded.last_seen_at, open_jobs_adverts.last_seen_at), "
            "changed_at = COALESCE(excluded.changed_at, open_jobs_adverts.changed_at), "
            "removed_at = COALESCE(excluded.removed_at, open_jobs_adverts.removed_at), "
            "payload_json = CASE WHEN excluded.payload_json = '{}'::jsonb "
            "THEN open_jobs_adverts.payload_json ELSE excluded.payload_json END, "
            "updated_at = excluded.updated_at",
            (aid, ats, slug, upstream_id, generation_id, release_id, provenance_id,
             operation, removal_reason, source_url, title, company, location, published_at,
             first_seen_at, last_seen_at, changed_at, removed_at, _json(payload), updated_at or _now()),
        )
        return aid

    def advert_event(
        self,
        ats: str,
        slug: str,
        upstream_id: str,
        generation_id: str,
        release_id: str,
        operation: str,
        *,
        advert_event_id: str | None = None,
        removal_reason: str | None = None,
        provenance_id: str | None = None,
        occurred_at: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Append one source operation; replaying a generation is idempotent."""
        if operation not in {"added", "changed", "changed_prev", "removed", "carried"}:
            raise ValueError(f"invalid Open Jobs operation: {operation!r}")
        if removal_reason not in {None, "closed", "left_dataset", "unknown"}:
            raise ValueError(f"invalid Open Jobs removal reason: {removal_reason!r}")
        if not provenance_id:
            raise ValueError("an Open Jobs advert event needs provenance_id")
        # The generation is reused while a source chain continues, and the
        # release id separates repeated operations for the same advert across
        # releases. Together these make a replay of one verified release a
        # no-op while preserving a later `changed` event as history.
        eid = advert_event_id or _stable_id(
            "oj-advert-event", generation_id, release_id, ats, slug,
            upstream_id, operation, removal_reason or "",
        )
        # 0114 generated ids without the release identity. Recognise an
        # already committed row by its source/release tuple so upgrading a
        # live beta database does not append a third copy of the same event.
        existing = self.conn.execute(
            "SELECT advert_event_id FROM open_jobs_advert_events "
            "WHERE ats = %s AND slug = %s AND upstream_id = %s "
            "AND generation_id = %s AND release_id = %s AND operation = %s "
            "AND removal_reason IS NOT DISTINCT FROM %s LIMIT 1",
            (ats, slug, upstream_id, generation_id, release_id, operation,
             removal_reason),
        ).fetchone()
        if existing is not None:
            return _value(existing, "advert_event_id")
        self.conn.execute(
            "INSERT INTO open_jobs_advert_events "
            "(advert_event_id, ats, slug, upstream_id, generation_id, release_id, provenance_id, "
            "operation, removal_reason, occurred_at, payload_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (advert_event_id) DO NOTHING",
            (eid, ats, slug, upstream_id, generation_id, release_id, provenance_id,
             operation, removal_reason, occurred_at or _now(), _json(payload)),
        )
        return eid

    def queue_review(
        self,
        review_kind: str,
        reason: str,
        *,
        review_id: str | None = None,
        advert_id: str | None = None,
        ats: str | None = None,
        slug: str | None = None,
        upstream_id: str | None = None,
        generation_id: str | None = None,
        release_id: str | None = None,
        provenance_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Queue an unresolved attribution or parsing question for a person."""
        if advert_id is None and not (ats and slug and upstream_id):
            raise ValueError("Open Jobs review needs an advert or source identity")
        rid = review_id or _stable_id(
            "oj-review", review_kind, advert_id or "|".join((ats or "", slug or "", upstream_id or "")), reason
        )
        self.conn.execute(
            "INSERT INTO open_jobs_review_queue "
            "(review_id, advert_id, review_kind, ats, slug, upstream_id, generation_id, release_id, "
            "provenance_id, reason, payload_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            # A pending review is a current work item.  Refresh its source
            # context and explainable triage payload when a later archive
            # contains richer text; resolved decisions are left untouched.
            "ON CONFLICT (review_id) DO UPDATE SET "
            "generation_id = COALESCE(excluded.generation_id, open_jobs_review_queue.generation_id), "
            "release_id = COALESCE(excluded.release_id, open_jobs_review_queue.release_id), "
            "provenance_id = COALESCE(excluded.provenance_id, open_jobs_review_queue.provenance_id), "
            "payload_json = excluded.payload_json "
            "WHERE open_jobs_review_queue.status = 'pending'",
            (rid, advert_id, review_kind, ats, slug, upstream_id, generation_id, release_id,
             provenance_id, reason, _json(payload)),
        )
        return rid

    def event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        *,
        generation_id: str | None = None,
        release_id: str | None = None,
        occurred_at: str | None = None,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> str:
        eid = event_id or _new_id("oj-event")
        self.conn.execute(
            "INSERT INTO open_jobs_events "
            "(event_id, event_type, entity_type, entity_id, generation_id, release_id, occurred_at, payload_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (event_id) DO NOTHING",
            (eid, event_type, entity_type, entity_id, generation_id, release_id,
             occurred_at or _now(), _json(payload)),
        )
        return eid

    def current(self, current_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT current_key, source_name, generation_id, release_id, artifact_id, "
            "updated_at, metadata_json FROM open_jobs_current WHERE current_key = %s",
            (current_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "current_key": _value(row, "current_key"),
            "source_name": _value(row, "source_name"),
            "generation_id": _value(row, "generation_id"),
            "release_id": _value(row, "release_id"),
            "artifact_id": _value(row, "artifact_id"),
            "updated_at": _value(row, "updated_at"),
            "metadata": _decode_json(_value(row, "metadata_json"), {}),
        }

    def events(self, entity_type: str, entity_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1_000))
        rows = self.conn.execute(
            "SELECT event_id, event_type, entity_type, entity_id, generation_id, release_id, "
            "occurred_at, payload_json FROM open_jobs_events "
            "WHERE entity_type = %s AND entity_id = %s ORDER BY occurred_at DESC, event_id DESC LIMIT %s",
            (entity_type, entity_id, limit),
        ).fetchall()
        return [
            {**{key: _value(row, key) for key in (
                "event_id", "event_type", "entity_type", "entity_id",
                "generation_id", "release_id", "occurred_at")},
             "payload": _decode_json(_value(row, "payload_json"), {})}
            for row in rows
        ]


# Functional aliases keep the storage boundary convenient for small modules
# that already pass a connection around, while the class is useful when many
# writes share the same connection.
def record_provenance(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).provenance(*args, **kwargs)


def start_generation(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).generation(*args, **kwargs)


def finish_generation(conn: Any, *args: Any, **kwargs: Any) -> None:
    OpenJobsStore(conn).finish_generation(*args, **kwargs)


def record_release(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).release(*args, **kwargs)


def record_artifact(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).artifact(*args, **kwargs)


def bind_artifact(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).bind_artifact(*args, **kwargs)


def set_current(conn: Any, *args: Any, **kwargs: Any) -> None:
    OpenJobsStore(conn).set_current(*args, **kwargs)


def set_link_state(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).set_link_state(*args, **kwargs)


def upsert_advert(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).upsert_advert(*args, **kwargs)


def append_advert_event(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).advert_event(*args, **kwargs)


def queue_review(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).queue_review(*args, **kwargs)


def append_event(conn: Any, *args: Any, **kwargs: Any) -> str:
    return OpenJobsStore(conn).event(*args, **kwargs)


def load_current(conn: Any, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
    return OpenJobsStore(conn).current(*args, **kwargs)


def list_events(conn: Any, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return OpenJobsStore(conn).events(*args, **kwargs)


__all__ = [
    "OpenJobsStore", "record_provenance", "start_generation", "finish_generation",
    "record_release", "record_artifact", "bind_artifact", "set_current",
    "set_link_state", "upsert_advert", "append_advert_event", "queue_review",
    "append_event", "load_current", "list_events",
]

"""Module 35 — Open Jobs operator shadow collector.

Open Jobs is a useful comparison corpus, but it is not evidence for the pay
campaign.  This module therefore has an explicit deployment gate, is marked
operator-only in the registry, and writes only the dedicated ``open_jobs_*``
tables.  It stores the source's release metadata and exact Parquet artifacts;
the bounded reader validates identity/lifecycle columns but does not promote,
enrich, or publish a posting.

The source's release parts can be hundreds of megabytes.  The configured
limits are checked both against the manifest and the fetched bytes, and the
collector uses the shared HTTP client so robots, rate limiting, conditional
cache and raw-byte provenance remain in one place.  Offline tests inject a
fake client; a normal installation never imports PyArrow unless this module is
explicitly enabled and run.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import structlog

from pipeline.http import PipelineHTTPClient
from pipeline.open_jobs.commands import OpenJobsClient
from pipeline.open_jobs.contract import DIFF_CONTRACT, SNAPSHOT_CONTRACT
from pipeline.open_jobs.policy import OpenJobsPolicy, PolicyError
from pipeline.open_jobs.reader import ReaderLimits, iter_batches, iter_records
from pipeline.open_jobs.store import OpenJobsStore
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "open_jobs"
CURRENT_KEY = "open_jobs_latest"
_KINDS = ("diffs", "ledger")
_DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _release_version(kind: str, entry: dict[str, Any]) -> str:
    return str(entry.get("to") or entry.get("date") or entry.get("dir") or kind)


def _entry_count(entry: dict[str, Any]) -> int | None:
    # Diffs carry a count of events; ledgers carry no count in the index. The
    # value is source metadata, never a count reconstructed by this module.
    counts = entry.get("counts")
    if isinstance(counts, dict):
        total = sum(v for v in counts.values() if isinstance(v, int) and v >= 0)
        return total
    for key in ("jobs", "new_jobs", "rows", "record_count"):
        value = entry.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    return None


def _write_temp(body: bytes, policy: OpenJobsPolicy) -> Path:
    if len(body) > policy.max_temp_bytes:
        raise PolicyError("Open Jobs temporary artifact exceeds max_temp_bytes")
    with tempfile.NamedTemporaryFile(prefix="open-jobs-", suffix=".parquet", delete=False) as stream:
        stream.write(body)
        return Path(stream.name)


def _validate_artifact(path: Path, *, kind: str, policy: OpenJobsPolicy) -> int:
    """Validate Parquet rows in bounded batches and return the row count."""
    contract = DIFF_CONTRACT if kind == "diffs" else SNAPSHOT_CONTRACT
    limits = ReaderLimits(max_artifact_bytes=policy.max_artifact_bytes,
                          max_record_bytes=policy.max_record_bytes,
                          decode_batch_rows=policy.decode_batch_rows)
    count = 0
    for batch in iter_batches(path, limits=limits, contract=contract):
        count += getattr(batch, "num_rows", 0)
    return count


def _project_rows(path: Path, *, ctx: ModuleContext, store: OpenJobsStore,
                  generation_id: str, release_id: str, provenance_id: str,
                  policy: OpenJobsPolicy) -> int:
    """Apply source operations to the shadow projection and append history.

    Only small, source-shaped fields are copied into PostgreSQL. Full text and
    enrichment remain in the archived artifact, preserving the privacy and
    attribution boundary while keeping replay deterministic.
    """
    contract = DIFF_CONTRACT
    limits = ReaderLimits(max_artifact_bytes=policy.max_artifact_bytes,
                          max_record_bytes=policy.max_record_bytes,
                          decode_batch_rows=policy.decode_batch_rows)
    count = 0
    for row in iter_records(path, limits=limits, contract=contract):
        count += 1
        ats, slug, upstream_id = row["ats"], row["slug"], row["id"]
        operation = row.get("op")
        removal_reason = row.get("removal_reason")
        payload = {key: row.get(key) for key in (
            "salary", "salary_text", "country", "published_at", "first_seen_at",
            "last_seen_at", "content_sha256") if key in row}
        salary_text = row.get("salary_text") or row.get("salary")
        if isinstance(salary_text, str) and salary_text.strip():
            # Reuse NHS Jobs' deterministic parser; this is a derived shadow
            # hint and remains in payload JSON with its source text, never a
            # promoted pay fact or an annualised value.
            from pipeline.modules.m16_nhs_jobs import parse_salary
            payload["salary_parse"] = parse_salary(salary_text)
        advert_id = None
        if operation != "changed_prev":
            advert_id = store.upsert_advert(
                ats, slug, upstream_id, generation_id, release_id, operation,
                removal_reason=removal_reason, provenance_id=provenance_id,
                source_url=row.get("url") or row.get("job_url"), title=row.get("title"),
                company=row.get("company") or row.get("employer"), location=row.get("location"),
                published_at=_iso(row.get("published_at")),
                first_seen_at=_iso(row.get("first_seen_at")),
                last_seen_at=None if operation == "carried" else _iso(row.get("last_seen_at")),
                changed_at=_iso(row.get("changed_at")), removed_at=_iso(row.get("removed_at")),
                payload=payload)
        store.advert_event(ats, slug, upstream_id, generation_id, release_id, operation,
                           removal_reason=removal_reason, provenance_id=provenance_id,
                           payload=payload)
        # Every Open Jobs identity is unbound until a person verifies a board
        # mapping. Coalescing by advert/reason keeps repeated releases from
        # creating an unbounded per-row review workload.
        if advert_id and operation in {"added", "changed"}:
            store.queue_review(
                "unknown_organisation", "Employer identity and provider binding require review",
                advert_id=advert_id, generation_id=generation_id, release_id=release_id,
                provenance_id=provenance_id,
                payload={"ats": ats, "slug": slug, "upstream_id": upstream_id})
    return count


def _collect_dry_run(client: OpenJobsClient, policy: OpenJobsPolicy,
                     since: str | None, limit: int | None) -> dict[str, int]:
    """Fetch and validate inputs without creating any warehouse state."""
    releases = artifacts = records = 0
    used = 0
    for kind in _KINDS:
        result, entries = client.fetch_index(kind)
        if not result.ok:
            continue
        for entry in policy.select_entries(entries, since=since, limit=limit):
            releases += 1
            if kind != "diffs":
                continue
            parts = client.artifacts(kind, entry, lite=True)
            if not parts:
                raise PolicyError("Open Jobs release listed no diff artifacts")
            for artifact in parts:
                fetched = client.fetch_artifact(artifact, used_bytes=used)
                if not fetched.ok:
                    raise PolicyError(f"Open Jobs artifact unavailable ({fetched.status_code})")
                used += len(fetched.body)
                path = _write_temp(fetched.body, policy)
                try:
                    records += _validate_artifact(path, kind=kind, policy=policy)
                finally:
                    path.unlink(missing_ok=True)
                artifacts += 1
    return {"releases": releases, "artifacts": artifacts, "records": records}


def collect(ctx: ModuleContext, *, http: Any | None = None) -> dict[str, int]:
    """Collect selected release manifests and bounded artifact parts.

    ``http`` is an optional test seam containing the shared-client interface;
    production callers leave it unset so this function creates exactly one
    ``PipelineHTTPClient`` for the run.
    """
    settings = ctx.settings
    if not getattr(settings, "open_jobs_enabled", False):
        log.info("open_jobs.disabled", reason="OPEN_JOBS_ENABLED is false")
        return {"releases": 0, "artifacts": 0, "records": 0}

    policy = OpenJobsPolicy.from_settings(settings)
    ctx.phase("validating Open Jobs release indexes and bounded diff artifacts")
    conn = ctx.conn
    store = OpenJobsStore(conn)
    own_client = http is None
    client_http = http or PipelineHTTPClient(SOURCE_SYSTEM, settings=settings, conn=conn)
    client = client_http if isinstance(client_http, OpenJobsClient) else OpenJobsClient(client_http, policy)
    if ctx.dry_run:
        try:
            result = _collect_dry_run(client, policy, ctx.since, ctx.limit)
        finally:
            if own_client:
                client_http.__exit__(None, None, None)
        log.info("open_jobs.dry_run", **result)
        return result
    generation_url = policy.url("/data/diffs/index.json")
    generation_id = store.generation(SOURCE_SYSTEM, generation_url,
                                     metadata={"since": ctx.since, "source": ctx.source})
    # Make the attempt durable before any release work. If a later artifact or
    # schema failure rolls back the module transaction, a separate bookkeeping
    # update can still mark this generation failed for operator diagnosis.
    conn.commit()
    release_count = artifact_count = record_count = 0
    used_bytes = 0
    try:
        for kind in _KINDS:
            result, entries = client.fetch_index(kind)
            index_pid = None
            if _DIGEST.fullmatch(result.payload_sha256 or ""):
                index_pid = store.provenance(
                    result.url, result.payload_sha256,
                    fetched_at=_iso(result.retrieved_at),
                    archived_path=result.archived_ref,
                    http_status=result.status_code,
                    content_type=result.content_type,
                    byte_size=len(result.body),
                    metadata={"kind": kind},
                )
            if not result.ok:
                store.event("index_unavailable", "provenance",
                            index_pid or f"{SOURCE_SYSTEM}-{kind}-unavailable",
                            generation_id=generation_id,
                            payload={"kind": kind, "status": result.status_code})
                continue
            selected = policy.select_entries(entries, since=ctx.since, limit=ctx.limit)
            for entry in selected:
                version = _release_version(kind, entry)
                release_id = store.release(
                    generation_id, version, status="released",
                    record_count=_entry_count(entry),
                    manifest_sha256=result.payload_sha256,
                    published_at=_iso(result.retrieved_at),
                    metadata={"kind": kind, "entry": entry},
                )
                store.event("release_selected", "release", release_id,
                            generation_id=generation_id, release_id=release_id,
                            payload={"kind": kind, "version": version})
                # The ledger is a full all-jobs snapshot with no lite tier;
                # downloading it would be a multi-hundred-megabyte live
                # crawl for metadata that the operator can inspect at source.
                # Diff releases expose a bounded lite tier and are the only
                # artifact bytes this shadow collector captures.
                if kind != "diffs":
                    store.event("artifact_deferred", "release", release_id,
                                generation_id=generation_id, release_id=release_id,
                                payload={"kind": kind, "reason": "full snapshot deferred"})
                    release_count += 1
                    continue
                declared_release_bytes = sum(
                    part.byte_size for part in client.artifacts(kind, entry, lite=True))
                policy.accept_size(declared_release_bytes, kind="release", used=used_bytes)
                release_artifacts = 0
                for artifact in client.artifacts(kind, entry, lite=True):
                    fetched = client.fetch_artifact(artifact, used_bytes=used_bytes)
                    if not fetched.ok:
                        raise PolicyError(
                            f"Open Jobs artifact unavailable ({fetched.status_code}): {artifact.url}")
                    used_bytes += len(fetched.body)
                    if used_bytes > policy.archive_budget_bytes:
                        raise PolicyError("Open Jobs archive budget exceeded")
                    artifact_pid = store.provenance(
                        fetched.url, fetched.payload_sha256,
                        fetched_at=_iso(fetched.retrieved_at),
                        archived_path=fetched.archived_ref,
                        http_status=fetched.status_code,
                        content_type=fetched.content_type,
                        byte_size=len(fetched.body),
                        metadata={"kind": artifact.artifact_kind,
                                  "release_version": version},
                    )
                    path = _write_temp(fetched.body, policy)
                    try:
                        rows = _validate_artifact(path, kind=kind, policy=policy)
                        if not ctx.dry_run:
                            rows = _project_rows(
                                path, ctx=ctx, store=store, generation_id=generation_id,
                                release_id=release_id, provenance_id=artifact_pid,
                                policy=policy)
                    finally:
                        path.unlink(missing_ok=True)
                    record_count += rows
                    artifact_id = store.artifact(
                        artifact_pid, artifact.artifact_kind,
                        fetched.archived_ref or str(fetched.archived_path or fetched.url),
                        len(fetched.body), fetched.payload_sha256,
                        content_type=fetched.content_type,
                        metadata={"declared_sha256": artifact.sha256,
                                  "declared_bytes": artifact.byte_size,
                                  "release_dir": entry.get("dir"),
                                  "filename": artifact.filename,
                                  "rows": rows},
                    )
                    store.bind_artifact(release_id, artifact_id, artifact.artifact_kind,
                                        ordinal=artifact.ordinal,
                                        metadata={"rows": rows})
                    store.event("artifact_captured", "artifact", artifact_id,
                                generation_id=generation_id, release_id=release_id,
                                payload={"rows": rows, "bytes": len(fetched.body)})
                    artifact_count += 1
                    release_artifacts += 1
                if release_artifacts == 0:
                    raise PolicyError(f"Open Jobs release {version} listed no diff artifacts")
                store.set_current(CURRENT_KEY, SOURCE_SYSTEM,
                                  generation_id=generation_id, release_id=release_id,
                                  metadata={"kind": kind, "version": version})
                release_count += 1
        store.finish_generation(generation_id, status="complete", record_count=record_count)
    except Exception as exc:
        try:
            from pipeline import db
            failure_conn = db.get_connection(settings)
            try:
                OpenJobsStore(failure_conn).finish_generation(
                    generation_id, status="failed", record_count=record_count,
                    error_text=f"{type(exc).__name__}: {exc}")
                failure_conn.commit()
            finally:
                failure_conn.close()
        except Exception as bookkeeping_exc:
            log.error("open_jobs.failure_bookkeeping_failed", error=str(bookkeeping_exc))
        raise
    finally:
        if own_client:
            client_http.__exit__(None, None, None)
    if not ctx.dry_run:
        conn.commit()
    log.info("open_jobs.finished", releases=release_count, artifacts=artifact_count,
             records=record_count, bytes=used_bytes)
    return {"releases": release_count, "artifacts": artifact_count, "records": record_count}


@register_module(
    "m35_open_jobs", supports_since=True, operator_only=True,
    since_note="selects Open Jobs releases whose source date is on or after --since",
)
def run(ctx: ModuleContext) -> None:
    if ctx.since:
        ctx.phase(f"replaying Open Jobs releases since {ctx.since}")
    collect(ctx)

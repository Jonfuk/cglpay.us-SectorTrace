"""Module 40 — OpenTender/OCP Registry operator mirror.

This is an explicit, disabled-by-default cross-check for the existing
procurement collector.  The Registry publication is a compiled/latest-value
snapshot, so this module records observations in dedicated tables and queues
reconciliation candidates.  It never writes ``contracts`` and is excluded
from ``run all`` and public exports.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import structlog

from pipeline import collection, db
from pipeline.archive import get_archive
from pipeline.http import PipelineHTTPClient
from pipeline.opentender import DEFAULT_OCID_PREFIX, ParseSummary, iter_observations, reconcile
from pipeline.opentender_store import OpenTenderStore
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

MODULE = "m40_opentender_registry"
SOURCE_SYSTEM = "opentender_uk_registry"
REGISTRY_URL = "https://data.open-contracting.org/en/publication/92"
PARSER_VERSION = "m40-opentender-v1"


class OpenTenderError(RuntimeError):
    """The configured package cannot be treated as a valid source input."""


def _format(path: Path) -> str:
    with path.open("rb") as stream:
        magic = stream.read(4)
    if magic == b"\x1f\x8b\x08":
        return "gzip-jsonl"
    if magic == b"PK\x03\x04":
        return "zip-json"
    return "jsonl" if path.suffix.lower() in {".jsonl", ".ndjson"} else "json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_spool(spool: Any, *, max_bytes: int) -> tuple[Path, int, str]:
    target = tempfile.NamedTemporaryFile(prefix="opentender-", suffix=".jsonl", delete=False)
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = spool.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise OpenTenderError("OpenTender package exceeds OPENTENDER_MAX_PACKAGE_BYTES")
            digest.update(chunk)
            target.write(chunk)
        target.flush()
        return Path(target.name), size, digest.hexdigest()
    except BaseException:
        Path(target.name).unlink(missing_ok=True)
        raise
    finally:
        target.close()


def _local_package(path: Path, ctx: ModuleContext) -> dict[str, Any]:
    if not path.is_file():
        raise OpenTenderError(f"OpenTender package does not exist: {path}")
    size = path.stat().st_size
    max_bytes = int(getattr(ctx.settings, "opentender_max_package_bytes", 512 * 1024 * 1024))
    if size > max_bytes:
        raise OpenTenderError("OpenTender package exceeds OPENTENDER_MAX_PACKAGE_BYTES")
    digest = _sha256(path)
    archive = get_archive(ctx.settings)
    archived = archive.put_file(SOURCE_SYSTEM, digest, "application/json", path)
    return {
        "path": path, "source_url": getattr(ctx.settings, "opentender_package_url", None) or str(path),
        "retrieved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "payload_sha256": digest, "raw_object_path": archived.logical_path,
        "byte_size": size, "content_type": "application/json", "temporary": False,
    }


def _remote_package(ctx: ModuleContext, url: str) -> dict[str, Any]:
    max_bytes = int(getattr(ctx.settings, "opentender_max_package_bytes", 512 * 1024 * 1024))
    client = PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=ctx.conn)
    try:
        with client.get_streaming(url) as result:
            if not result.ok:
                raise OpenTenderError(f"OpenTender package unavailable ({result.status_code}): {url}")
            path, size, digest = _copy_spool(result.spool, max_bytes=max_bytes)
            if not result.archived_ref:
                raise OpenTenderError("OpenTender package was fetched without an archive reference")
            return {
                "path": path, "source_url": result.url, "retrieved_at": result.retrieved_at.isoformat(),
                "payload_sha256": digest, "raw_object_path": result.archived_ref,
                "byte_size": size, "content_type": result.content_type, "temporary": True,
            }
    finally:
        client.__exit__(None, None, None)


def _configured_package(ctx: ModuleContext) -> dict[str, Any]:
    path_value = getattr(ctx.settings, "opentender_package_path", None)
    url = getattr(ctx.settings, "opentender_package_url", None)
    if path_value and url:
        raise OpenTenderError("configure only one of OPENTENDER_PACKAGE_PATH or OPENTENDER_PACKAGE_URL")
    if path_value:
        return _local_package(Path(path_value), ctx)
    if url:
        return _remote_package(ctx, str(url))
    raise OpenTenderError(
        "OpenTender is enabled but no package is configured; set "
        "OPENTENDER_PACKAGE_PATH or OPENTENDER_PACKAGE_URL")


def _direct_contracts(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT ocid, buyer_name, title, cpv_codes, value_core, currency, date_published "
        "FROM contracts").fetchall()
    return [dict(row) for row in rows]


def _period(observations: list[Any]) -> tuple[str | None, str | None]:
    dates = sorted({str(row.date_published)[:10] for row in observations if row.date_published})
    return (dates[0], dates[-1]) if dates else (None, None)


def collect(ctx: ModuleContext) -> dict[str, int]:
    """Capture one explicitly configured package and reconcile its rows."""
    if not getattr(ctx.settings, "opentender_enabled", False):
        log.info("opentender.disabled", reason="OPENTENDER_ENABLED is false")
        return {"packages": 0, "observations": 0, "failures": 0, "reviews": 0}

    package = None
    with collection.collection_attempt(
        ctx.conn, module=MODULE, source_system=SOURCE_SYSTEM, scope="configured_package"
    ) as attempt:
        try:
            package = _configured_package(ctx)
            summary = ParseSummary()
            observations = list(iter_observations(
                package["path"],
                ocid_prefix=getattr(ctx.settings, "opentender_ocid_prefix", DEFAULT_OCID_PREFIX),
                since=ctx.since,
                limit=ctx.limit,
                summary=summary,
            ))
            if summary.objects == 0:
                raise OpenTenderError("OpenTender package contained no JSON objects")
            if not observations and summary.failures and summary.objects == len(summary.failures):
                raise OpenTenderError("OpenTender package contained no valid compiled releases")

            direct = _direct_contracts(ctx.conn)
            store = OpenTenderStore(ctx.conn)
            period_start, period_end = _period(observations)
            package_id = store.package(
                source_url=package["source_url"], retrieved_at=package["retrieved_at"],
                payload_sha256=package["payload_sha256"], raw_object_path=package["raw_object_path"],
                byte_size=package["byte_size"], content_type=package["content_type"],
                package_format=_format(package["path"]),
                ocid_prefix=getattr(ctx.settings, "opentender_ocid_prefix", DEFAULT_OCID_PREFIX),
                period_start=period_start, period_end=period_end, status="captured",
                row_count=len(observations),
                metadata={"registry_url": REGISTRY_URL, "parser_version": PARSER_VERSION,
                          "objects_seen": summary.objects, "since": ctx.since},
            )
            reviews = 0
            for observation in observations:
                match = reconcile(observation, direct)
                observation_id = store.observation(
                    package_id,
                    source_record_id=observation.source_record_id,
                    ocid=observation.ocid,
                    buyer_name=observation.buyer_name,
                    title=observation.title,
                    cpv_codes=",".join(observation.cpv_codes) or None,
                    value_amount=observation.value_amount,
                    value_currency=observation.value_currency,
                    date_published=observation.date_published,
                    record_sha256=observation.record_sha256,
                    match=match,
                    metadata={"source_url": package["source_url"], "parser_version": PARSER_VERSION},
                )
                if match["status"] != "exact_ocid":
                    db.record_review_item(
                        ctx.conn, MODULE, f"opentender_{match['status']}", observation.ocid,
                        json.dumps({"observation_id": observation_id, "package_id": package_id,
                                    "source_record_id": observation.source_record_id,
                                    "source_url": package["source_url"], "match": match}, sort_keys=True),
                    )
                    reviews += 1
            for failure in summary.failures:
                db.record_parse_failure(
                    ctx.conn, MODULE, failure.field_name, failure.raw_fragment,
                    failure.reason, source_url=package["source_url"],
                )
            attempt.result_count = len(observations)
            attempt.coverage_state = "covered" if observations else "no_results"
            attempt.detail = {"package_id": package_id, "objects_seen": summary.objects,
                              "parse_failures": len(summary.failures), "reviews": reviews,
                              "period_start": period_start, "period_end": period_end}
            if not observations:
                log.info("opentender.empty", source_url=package["source_url"], objects=summary.objects)
            return {"packages": 1, "observations": len(observations),
                    "failures": len(summary.failures), "reviews": reviews}
        finally:
            if package and package.get("temporary"):
                Path(package["path"]).unlink(missing_ok=True)


@register_module(
    MODULE, supports_since=True, operator_only=True,
    since_note="filters the explicitly configured OpenTender package by published date; mirror rows remain separate",
)
def run(ctx: ModuleContext) -> None:
    collect(ctx)

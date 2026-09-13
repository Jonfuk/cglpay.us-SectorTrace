"""Module 36 — bounded OpenAlex discovery shadow collector.

OpenAlex is useful for finding potentially relevant research, institutions,
funders and topics. It is not an authoritative registry of evaluations or
collaborations. This module therefore stays operator-only, stores only
public-shaped entity metadata, puts author and raw-affiliation fields behind
the restricted boundary, and queues every relationship for human review.

The collector uses the shared HTTP client, cursor checkpoints and the paid
``from_updated_date`` filter when a run supplies ``--since``. It never fetches
full text and has bounded query, page and record limits.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "openalex"
QUERY_VERSION = "evaluation-discovery-v1"
DEFAULT_QUERY_TERMS = (
    "substance misuse evaluation",
    "drug and alcohol treatment evaluation",
    "drug and alcohol services evaluation",
    "health services research substance misuse",
    "public health service evaluation",
    "local authority public health evaluation",
)
WORK_SELECT = "id,doi,title,publication_date,type,primary_topic,topics,grants,open_access,updated_date,authorships"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _terms(settings: Any) -> tuple[str, ...]:
    raw = getattr(settings, "openalex_query_terms", "")
    values = tuple(dict.fromkeys(part.strip() for part in raw.split("|") if part.strip()))
    return values or DEFAULT_QUERY_TERMS


def _key(settings: Any) -> str:
    value = getattr(settings, "openalex_api_key", None)
    if not value:
        raise RuntimeError("OPENALEX_API_KEY must be set when OPENALEX_ENABLED=true")
    return value


def _cursor_key(query: str, since: str | None) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return f"m36_openalex:{QUERY_VERSION}:{digest}:{since or 'full'}"


def _source_row(result: Any) -> dict[str, Any]:
    return {
        "source_url": str(result.url),
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _entity_id(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return _entity_id(value.get("id"))
    return None


def _upsert_entity(conn: Any, entity_type: str, entity_id: str,
                   display_name: str | None, payload: dict[str, Any],
                   external_ids: dict[str, Any], updated_at: str | None,
                   source: dict[str, Any]) -> None:
    db.upsert(conn, "openalex_records", {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "display_name": display_name,
        "external_ids_json": _json(external_ids),
        "payload_json": _json(payload),
        "upstream_updated_at": updated_at,
        **source,
    }, ["entity_type", "entity_id"])


def _candidate(conn: Any, work_id: str, relationship_type: str,
               object_type: str, object_id: str, evidence: dict[str, Any],
               source: dict[str, Any]) -> None:
    candidate_id = hashlib.sha256(
        f"{work_id}|{relationship_type}|{object_type}|{object_id}".encode()
    ).hexdigest()
    db.upsert(conn, "openalex_relationship_candidates", {
        "candidate_id": candidate_id,
        "work_id": work_id,
        "relationship_type": relationship_type,
        "object_type": object_type,
        "object_id": object_id,
        "evidence_json": _json(evidence),
        # This is an explicit source relationship, not a model probability.
        "confidence": None,
        "status": "pending_review",
        **source,
    }, ["candidate_id"], preserve=["status", "confidence"])
    db.record_review_item(
        conn, SOURCE_SYSTEM, "openalex_relationship", candidate_id,
        _json({"work_id": work_id, "relationship_type": relationship_type,
               "object_type": object_type, "object_id": object_id}),
    )


def _store_work(conn: Any, work: dict[str, Any], result: Any, query: str) -> int:
    work_id = _entity_id(work.get("id"))
    if not work_id:
        db.record_parse_failure(conn, SOURCE_SYSTEM, "id", _json(work),
                                "work has no OpenAlex id", str(result.url))
        return 0
    source = _source_row(result)
    public = {key: value for key, value in work.items() if key != "authorships"}
    _upsert_entity(conn, "work", work_id, work.get("title"), public,
                   {"doi": work.get("doi")}, work.get("updated_date"), source)
    count = 1

    primary_topic = work.get("primary_topic")
    topics = list(work.get("topics") or [])
    if isinstance(primary_topic, dict) and primary_topic not in topics:
        topics.append(primary_topic)
    seen_topics: set[str] = set()
    for topic in topics:
        topic_id = _entity_id(topic)
        if not topic_id or topic_id in seen_topics:
            continue
        seen_topics.add(topic_id)
        _upsert_entity(conn, "topic", topic_id, topic.get("display_name"),
                       {"id": topic_id, "display_name": topic.get("display_name"),
                        "score": topic.get("score")}, {}, None, source)
        _candidate(conn, work_id, "about_topic", "topic", topic_id,
                   {"source_field": "topics", "query": query,
                    "query_version": QUERY_VERSION}, source)
        count += 1

    for grant in work.get("grants") or []:
        if not isinstance(grant, dict):
            continue
        funder = grant.get("funder")
        funder_id = _entity_id(funder)
        if not funder_id:
            continue
        funder_name = grant.get("funder_display_name")
        if not funder_name and isinstance(funder, dict):
            funder_name = funder.get("display_name")
        _upsert_entity(conn, "funder", funder_id, funder_name,
                       {"id": funder_id, "display_name": funder_name}, {}, None, source)
        _candidate(conn, work_id, "funded_by", "funder", funder_id,
                   {"source_field": "grants", "award_id": grant.get("award_id"),
                    "query": query, "query_version": QUERY_VERSION}, source)
        count += 1

    for position, authorship in enumerate(work.get("authorships") or []):
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") or {}
        author_id = _entity_id(author)
        if not author_id:
            db.record_parse_failure(conn, SOURCE_SYSTEM, "authorship.author.id",
                                    _json(authorship), "authorship has no author id",
                                    str(result.url))
            continue
        author_ids = author.get("ids") if isinstance(author, dict) else {}
        orcid = author.get("orcid") or (author_ids or {}).get("orcid")
        restricted_payload = {
            "author": {"id": author_id, "display_name": author.get("display_name"),
                        "orcid": orcid},
            "author_position": authorship.get("author_position"),
            "is_corresponding": authorship.get("is_corresponding"),
        }
        db.upsert(conn, "restricted_openalex_authorships", {
            "work_id": work_id,
            "author_id": author_id,
            "author_position": position,
            "author_name": author.get("display_name") or authorship.get("raw_author_name"),
            "orcid": orcid,
            "raw_affiliation_strings_json": _json(authorship.get("raw_affiliation_strings") or []),
            "affiliations_json": _json(authorship.get("affiliations") or []),
            "payload_json": _json(restricted_payload),
            **source,
        }, ["work_id", "author_id", "author_position"])
        institutions = authorship.get("institutions") or []
        for institution in institutions:
            institution_id = _entity_id(institution)
            if not institution_id:
                continue
            institution_name = institution.get("display_name") if isinstance(institution, dict) else None
            external_ids = {}
            if isinstance(institution, dict):
                external_ids = {"ror": institution.get("ror")} if institution.get("ror") else {}
            _upsert_entity(conn, "institution", institution_id, institution_name,
                           {"id": institution_id, "display_name": institution_name},
                           external_ids, None, source)
            _candidate(conn, work_id, "affiliated_with", "institution", institution_id,
                       {"source_field": "authorships[].institutions[]",
                        "author_id": author_id, "author_position": position,
                        "query": query, "query_version": QUERY_VERSION}, source)
            count += 1
    return count


def _request_params(query: str, cursor: str, since: str | None, settings: Any) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "search": query,
        "cursor": cursor,
        "per-page": max(1, min(int(getattr(settings, "openalex_page_size", 100)), 100)),
        "select": WORK_SELECT,
    }
    if since:
        params["filter"] = f"from_updated_date:{since}"
    return params


def collect(ctx: ModuleContext, *, http: Any | None = None) -> dict[str, int]:
    settings = ctx.settings
    if not getattr(settings, "openalex_enabled", False):
        log.info("openalex.disabled", reason="OPENALEX_ENABLED is false")
        return {"queries": 0, "pages": 0, "records": 0}
    api_key = _key(settings)
    base_url = str(getattr(settings, "openalex_base_url", "https://api.openalex.org")).rstrip("/")
    max_records = max(1, int(getattr(settings, "openalex_max_records_per_query", 200)))
    max_pages = max(1, int(getattr(settings, "openalex_max_pages_per_query", 20)))
    terms = _terms(settings)
    own_client = http is None
    client = http or PipelineHTTPClient(SOURCE_SYSTEM, settings=settings, conn=ctx.conn)
    pages = records = 0
    try:
        for query in ctx.track(terms, "OpenAlex discovery queries"):
            cursor_key = _cursor_key(query, ctx.since)
            cursor = db.get_cursor(ctx.conn, cursor_key) or "*"
            query_records = 0
            query_complete = False
            for _page in range(max_pages):
                result = client.get(
                    f"{base_url}/works",
                    params=_request_params(query, cursor, ctx.since, settings),
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                pages += 1
                if not result.ok:
                    db.record_review_item(ctx.conn, SOURCE_SYSTEM, "openalex_request_failed",
                                          f"{query}|{result.status_code}",
                                          _json({"query": query, "status": result.status_code,
                                                 "url": str(result.url)}))
                    break
                try:
                    payload = json.loads(result.body.decode("utf-8"))
                    works = payload["results"]
                    if not isinstance(works, list):
                        raise TypeError("results is not a list")
                except (ValueError, KeyError, UnicodeDecodeError, TypeError) as exc:
                    db.record_parse_failure(ctx.conn, SOURCE_SYSTEM, "results",
                                            result.body[:2000].decode("utf-8", "replace"),
                                            f"invalid OpenAlex response: {exc}", str(result.url))
                    break
                remaining = max_records - query_records
                for work in works[:remaining]:
                    if isinstance(work, dict):
                        records += _store_work(ctx.conn, work, result, query)
                        query_records += 1
                next_cursor = ((payload.get("meta") or {}).get("next_cursor"))
                db.set_cursor(ctx.conn, cursor_key, next_cursor or "*")
                if not next_cursor or query_records >= max_records or not works:
                    query_complete = True
                    break
                cursor = next_cursor
            if not query_complete:
                db.record_review_item(ctx.conn, SOURCE_SYSTEM, "openalex_query_capped", query,
                                      _json({"max_pages": max_pages, "max_records": max_records}))
            else:
                db.set_cursor(ctx.conn, cursor_key, "*")
            if not ctx.dry_run:
                ctx.conn.commit()
    finally:
        if own_client:
            client.__exit__(None, None, None)
    log.info("openalex.finished", queries=len(terms), pages=pages, records=records)
    return {"queries": len(terms), "pages": pages, "records": records}


@register_module(
    "m36_openalex", supports_since=True, operator_only=True,
    since_note="uses OpenAlex's paid from_updated_date filter and cursor checkpoints",
)
def run(ctx: ModuleContext) -> None:
    if ctx.since:
        ctx.phase(f"collecting OpenAlex discovery updates since {ctx.since}")
    collect(ctx)

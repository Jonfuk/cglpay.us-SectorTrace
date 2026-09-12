"""The transport contract, implemented over the existing HTTPX path.

This wraps `pipeline.http.PipelineHTTPClient` — it does not replace it, and
no production module is changed to call this instead. Its purpose is to
prove that `TransportResult` is a real contract and not one shaped only
around Scrapy: the same robots/rate-limit/provenance-capturing client that
every module already uses can be read through it without changing a line of
`pipeline/http.py`.

A module wanting the transport contract today would call `fetch_via_httpx`
rather than `PipelineHTTPClient` directly; nothing in this codebase does that
yet, by design (scrapy.md Phase 1 explicitly leaves production modules on
HTTPX).
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from pipeline.config import Settings
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.netguard import BlockedAddress
from pipeline.transports.types import FailureClass, TransportResult


def fetch_via_httpx(
    url: str,
    *,
    source_system: str,
    settings: Settings,
    module: str | None = None,
    conn=None,
    guard_destination: bool = False,
    resolver=None,
) -> TransportResult:
    """Fetch one URL through `PipelineHTTPClient`, returning a `TransportResult`.

    Every branch here maps an existing, already-tested HTTPX behaviour onto a
    `FailureClass` rather than inventing new failure handling: robots and the
    destination guard raise the same exceptions they always have (see
    `pipeline/http.py`, `pipeline/netguard.py`), and this only labels them.
    """
    client = PipelineHTTPClient(
        source_system, settings=settings, conn=conn,
        guard_destination=guard_destination, resolver=resolver,
    )
    attempted_at = datetime.now(timezone.utc)
    try:
        result = client.get(url)
    except RobotsDisallowed as exc:
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=url, retrieved_at=attempted_at, ok=False,
            failure_class=FailureClass.ROBOTS_DISALLOWED, failure_detail=str(exc),
        )
    except BlockedAddress as exc:
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=url, retrieved_at=attempted_at, ok=False,
            failure_class=FailureClass.BLOCKED_DESTINATION, failure_detail=str(exc),
        )
    except httpx.TimeoutException as exc:
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=url, retrieved_at=attempted_at, ok=False,
            failure_class=FailureClass.TIMEOUT, failure_detail=str(exc),
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=url, retrieved_at=attempted_at, ok=False,
            failure_class=FailureClass.HTTP_ERROR, status_code=status,
            failure_detail=str(exc),
        )
    except httpx.TransportError as exc:
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=url, retrieved_at=attempted_at, ok=False,
            failure_class=FailureClass.TRANSPORT_ERROR, failure_detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - deliberately caught and labelled
        # A response this pipeline has not been taught to recognise must
        # become a visible failure, never a silently empty success — the
        # design constraint scrapy.md states explicitly. Whatever this is, it
        # is reported, not swallowed.
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=url, retrieved_at=attempted_at, ok=False,
            failure_class=FailureClass.UNRECOGNISED,
            failure_detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        client.close()

    if result.status_code >= 400:
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=result.url, final_url=result.final_url,
            status_code=result.status_code, retrieved_at=result.retrieved_at,
            ok=False, failure_class=FailureClass.HTTP_ERROR,
            failure_detail=f"HTTP {result.status_code}",
            headers=dict(result.headers), payload_sha256=result.payload_sha256,
            raw_archive_ref=result.archived_ref,
        )
    if not result.body:
        return TransportResult(
            transport="httpx", source_system=source_system, module=module,
            requested_url=result.url, final_url=result.final_url,
            status_code=result.status_code, retrieved_at=result.retrieved_at,
            ok=False, failure_class=FailureClass.EMPTY_RESPONSE,
            failure_detail="response carried no body",
            headers=dict(result.headers),
        )

    return TransportResult(
        transport="httpx", source_system=source_system, module=module,
        requested_url=result.url, final_url=result.final_url,
        status_code=result.status_code, retrieved_at=result.retrieved_at,
        ok=True, failure_class=FailureClass.NONE,
        headers=dict(result.headers), body=result.body,
        payload_sha256=result.payload_sha256, raw_archive_ref=result.archived_ref,
        transport_meta={"not_modified": result.not_modified},
    )

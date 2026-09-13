"""SQL boundary for the operator-only OpenTender mirror tables."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, default=str)


def stable_id(prefix: str, *parts: object) -> str:
    material = "\0".join("" if part is None else str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


class OpenTenderStore:
    """Keep mirror writes distinct from the canonical procurement tables."""

    def __init__(self, conn: Any):
        self.conn = conn

    def package(self, *, source_url: str, retrieved_at: str, payload_sha256: str,
                raw_object_path: str, byte_size: int, content_type: str | None,
                package_format: str, ocid_prefix: str, period_start: str | None,
                period_end: str | None, status: str, row_count: int,
                metadata: dict[str, Any] | None = None) -> str:
        package_id = stable_id("ot-package", source_url, payload_sha256)
        self.conn.execute(
            "INSERT INTO procurement_mirror_packages "
            "(package_id, source_system, source_url, retrieved_at, payload_sha256, "
            "raw_object_path, byte_size, content_type, package_format, ocid_prefix, "
            "period_start, period_end, licence_id, export_disposition, status, "
            "row_count, metadata_json, created_at) "
            "VALUES (%s, 'opentender_uk_registry', %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, 'opentender_cc_by_nc_sa', 'operator_only', %s, %s, %s::jsonb, %s) "
            "ON CONFLICT (source_url, payload_sha256) DO UPDATE SET "
            "retrieved_at = excluded.retrieved_at, raw_object_path = excluded.raw_object_path, "
            "byte_size = excluded.byte_size, content_type = excluded.content_type, "
            "package_format = excluded.package_format, period_start = excluded.period_start, "
            "period_end = excluded.period_end, status = excluded.status, row_count = excluded.row_count, "
            "metadata_json = excluded.metadata_json",
            (package_id, source_url, retrieved_at, payload_sha256, raw_object_path,
             byte_size, content_type, package_format, ocid_prefix, period_start,
             period_end, status, row_count, _json(metadata), _now()),
        )
        return package_id

    def observation(self, package_id: str, *, source_record_id: str, ocid: str,
                    buyer_name: str | None, title: str | None, cpv_codes: str | None,
                    value_amount: float | None, value_currency: str | None,
                    date_published: str | None, record_sha256: str,
                    match: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
        observation_id = stable_id("ot-observation", package_id, source_record_id, record_sha256)
        self.conn.execute(
            "INSERT INTO procurement_mirror_observations "
            "(observation_id, package_id, source_record_id, ocid, buyer_name, title, cpv_codes, "
            "value_amount, value_currency, date_published, record_sha256, parser_version, "
            "match_status, matched_ocid, match_basis, candidate_count, metadata_json, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'm40-opentender-v1', "
            "%s, %s, %s, %s, %s::jsonb, %s) "
            "ON CONFLICT (observation_id) DO UPDATE SET match_status = excluded.match_status, "
            "matched_ocid = excluded.matched_ocid, match_basis = excluded.match_basis, "
            "candidate_count = excluded.candidate_count, metadata_json = excluded.metadata_json",
            (observation_id, package_id, source_record_id, ocid, buyer_name, title,
             cpv_codes, value_amount, value_currency, date_published, record_sha256,
             match.get("status"), match.get("matched_ocid"), match.get("basis"),
             match.get("candidate_count", 0), _json(metadata), _now()),
        )
        return observation_id

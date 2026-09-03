"""Compact analysis manifests, checkpoints, candidate queues and retention."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Iterator

from pipeline.analysis.operations import utcnow

EMPTY_ORDERED_DIGEST = hashlib.sha256(b"").hexdigest()


def chain_digest(previous: str, item: dict[str, Any]) -> str:
    """A resumable ordered-input digest chain."""
    canonical = json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(bytes.fromhex(previous) + canonical.encode()).hexdigest()


def get_or_create_manifest(conn, *, run_id: str, release_id: str, domain_id: str,
                           source_tables: Iterable[str], configuration: dict[str, Any],
                           prefilter_version: str,
                           prefilter_result_sha256: str | None = None,
                           suppression_enabled: bool = False) -> dict[str, Any]:
    row = conn.execute(
        "SELECT m.* FROM analysis_input_manifests m JOIN analysis_domain_runs d "
        "ON d.domain_run_id = m.domain_run_id WHERE d.run_id = %s AND d.domain_id = %s",
        (run_id, domain_id)).fetchone()
    if row:
        return dict(row)
    domain = conn.execute(
        "SELECT domain_run_id FROM analysis_domain_runs WHERE run_id = %s AND domain_id = %s",
        (run_id, domain_id)).fetchone()
    if domain is None:
        raise KeyError(f"missing domain run for {run_id}/{domain_id}")
    manifest_id = f"analysis-input-{uuid.uuid4()}"
    now = utcnow()
    config_digest = hashlib.sha256(json.dumps(
        configuration, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    conn.execute(
        "INSERT INTO analysis_input_manifests (input_manifest_id, domain_run_id, run_id, release_id, "
        "domain_id, source_tables_json, ordered_input_sha256, configuration_sha256, "
        "prefilter_version, prefilter_result_sha256, suppression_enabled, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (manifest_id, domain["domain_run_id"], run_id, release_id, domain_id,
         json.dumps(sorted(source_tables)), EMPTY_ORDERED_DIGEST, config_digest,
         prefilter_version, prefilter_result_sha256, int(suppression_enabled), now, now))
    return dict(conn.execute(
        "SELECT * FROM analysis_input_manifests WHERE input_manifest_id = %s",
        (manifest_id,)).fetchone())


def checkpoint(conn, manifest: dict[str, Any], *, rows: list[dict[str, Any]],
               accumulator_state: dict[str, Any], accepted: list[tuple[int, str, bool]]) -> dict[str, Any]:
    digest = manifest["ordered_input_sha256"]
    count = int(manifest["input_count"] or 0)
    for row in rows:
        count += 1
        digest = chain_digest(digest, {
            "ordinal": count, "document_id": row["document_id"],
            "sequence": row["sequence"], "element_id": row["document_element_id"],
            "text_sha256": row.get("text_sha256"),
        })
    candidate_rows = []
    for ordinal, element_id, matched in accepted:
        candidate_key = hashlib.sha256(
            f"{manifest['input_manifest_id']}\0{element_id}".encode()).hexdigest()
        candidate_rows.append((
            f"candidate-{candidate_key}", manifest["input_manifest_id"], ordinal,
            element_id, int(matched), "[]", utcnow()))
    conn.executemany(
        "INSERT INTO analysis_candidates (candidate_id, input_manifest_id, ordinal, "
        "document_element_id, prefilter_matched, critical_categories_json, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        candidate_rows)
    tail = rows[-1]
    conn.execute(
        "UPDATE analysis_input_manifests SET input_count = %s, ordered_input_sha256 = %s, "
        "candidate_count = candidate_count + %s, checkpoint_document_id = %s, "
        "checkpoint_sequence = %s, checkpoint_element_id = %s, accumulator_json = %s, "
        "updated_at = %s WHERE input_manifest_id = %s",
        (count, digest, len(candidate_rows), tail["document_id"], tail["sequence"],
         tail["document_element_id"], json.dumps(accumulator_state, sort_keys=True),
         utcnow(), manifest["input_manifest_id"]))
    manifest.update({
        "input_count": count, "ordered_input_sha256": digest,
        "candidate_count": int(manifest["candidate_count"] or 0) + len(candidate_rows),
        "checkpoint_document_id": tail["document_id"],
        "checkpoint_sequence": tail["sequence"],
        "checkpoint_element_id": tail["document_element_id"],
        "accumulator_json": json.dumps(accumulator_state, sort_keys=True),
    })
    return manifest


def accumulate_themes(conn, input_manifest_id: str, passages: list[dict[str, Any]], *,
                      first_ordinal: int, max_evidence_per_theme: int = 25,
                      max_evidence_total: int = 5_000) -> dict[str, int]:
    """Accumulate exact counts/distincts in PostgreSQL with bounded samples."""
    keyed, counts, first, documents, subjects = _theme_batch_summary(
        passages, first_ordinal=first_ordinal)
    conn.executemany(
        "INSERT INTO analysis_theme_counts (input_manifest_id, theme_key, first_ordinal, passage_count) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (input_manifest_id, theme_key) DO UPDATE SET "
        "passage_count = analysis_theme_counts.passage_count + excluded.passage_count",
        [(input_manifest_id, key, first[key], count) for key, count in counts.items()])
    conn.executemany(
        "INSERT INTO analysis_theme_documents (input_manifest_id, theme_key, document_id) "
        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        [(input_manifest_id, key, document_id)
         for key, document_id in documents])
    conn.executemany(
        "INSERT INTO analysis_theme_subjects (input_manifest_id, theme_key, subject_id) "
        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        [(input_manifest_id, key, subject_id)
         for key, subject_id in subjects])
    total = int(conn.execute(
        "SELECT COUNT(*) AS count FROM analysis_theme_evidence WHERE input_manifest_id = %s",
        (input_manifest_id,)).fetchone()["count"])
    existing = {row["theme_key"]: int(row["count"]) for row in conn.execute(
        "SELECT theme_key, COUNT(*) AS count FROM analysis_theme_evidence "
        "WHERE input_manifest_id = %s GROUP BY theme_key", (input_manifest_id,))}
    evidence = []
    for ordinal, key, passage in keyed:
        if total >= max_evidence_total or existing.get(key, 0) >= max_evidence_per_theme:
            continue
        item = {**passage, "representative_quote": str(passage.get("text") or "").strip()[:240]}
        evidence.append((input_manifest_id, key, ordinal,
                         json.dumps(item, sort_keys=True, default=str)))
        existing[key] = existing.get(key, 0) + 1
        total += 1
    conn.executemany(
        "INSERT INTO analysis_theme_evidence (input_manifest_id, theme_key, ordinal, passage_json) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", evidence)
    return {"theme_count": len(counts), "retained_evidence": total}


def _theme_batch_summary(passages: list[dict[str, Any]], *, first_ordinal: int):
    """Build deterministic batch aggregates in one bounded traversal."""
    from collections import Counter

    from pipeline.analysis.narrative import theme_key_for_text

    keyed = []
    counts: Counter[str] = Counter()
    first: dict[str, int] = {}
    documents: set[tuple[str, str]] = set()
    subjects: set[tuple[str, str]] = set()
    for index, passage in enumerate(passages):
        ordinal = first_ordinal + index
        key = theme_key_for_text(str(passage.get("text") or ""))
        keyed.append((ordinal, key, passage))
        counts[key] += 1
        first.setdefault(key, ordinal)
        if passage.get("document_id"):
            documents.add((key, str(passage["document_id"])))
        if passage.get("subject_id"):
            subjects.add((key, str(passage["subject_id"])))
    return keyed, counts, first, sorted(documents), sorted(subjects)


def accumulated_themes(conn, input_manifest_id: str, *, novelty_threshold: float = .85,
                       recurrence_bar: dict[str, int] | None = None) -> list[dict[str, Any]]:
    bar = {"passages": 10, "documents": 5, "subjects": 3} | (recurrence_bar or {})
    rows = conn.execute(
        "SELECT c.theme_key, c.first_ordinal, c.passage_count, "
        "COALESCE(d.document_count, 0) AS document_count, "
        "COALESCE(s.subject_count, 0) AS subject_count "
        "FROM analysis_theme_counts c "
        "LEFT JOIN (SELECT input_manifest_id, theme_key, COUNT(*) AS document_count "
        "FROM analysis_theme_documents WHERE input_manifest_id = %s "
        "GROUP BY input_manifest_id, theme_key) d ON d.input_manifest_id = c.input_manifest_id "
        "AND d.theme_key = c.theme_key "
        "LEFT JOIN (SELECT input_manifest_id, theme_key, COUNT(*) AS subject_count "
        "FROM analysis_theme_subjects WHERE input_manifest_id = %s "
        "GROUP BY input_manifest_id, theme_key) s ON s.input_manifest_id = c.input_manifest_id "
        "AND s.theme_key = c.theme_key WHERE c.input_manifest_id = %s "
        "ORDER BY c.first_ordinal",
        (input_manifest_id, input_manifest_id, input_manifest_id)).fetchall()
    evidence: dict[str, list[dict[str, Any]]] = {}
    for row in conn.execute(
            "SELECT theme_key, passage_json FROM analysis_theme_evidence "
            "WHERE input_manifest_id = %s ORDER BY ordinal", (input_manifest_id,)):
        evidence.setdefault(row["theme_key"], []).append(json.loads(row["passage_json"]))
    themes = []
    for row in rows:
        count = int(row["passage_count"])
        documents = int(row["document_count"])
        subjects = int(row["subject_count"])
        is_outlier = row["theme_key"] == "outlier" or count == 1
        themes.append({
            "theme_key": row["theme_key"], "passage_count": count,
            "document_count": documents, "subject_count": subjects,
            "novelty_similarity": 0.0 if is_outlier else min(.84, .5 + 1 / max(count, 1)),
            "outlier": is_outlier, "passages": evidence.get(row["theme_key"], []),
            "status": "promotion_ready" if count >= bar["passages"] and
            documents >= bar["documents"] and subjects >= bar["subjects"] and
            (0.0 if is_outlier else .5) < novelty_threshold else "shadow",
        })
    return themes


def candidate_batches(conn, input_manifest_id: str, *, batch_size: int) -> Iterator[list[dict[str, Any]]]:
    last_ordinal = -1
    last_candidate = ""
    while True:
        rows = conn.execute(
            "SELECT c.candidate_id, c.ordinal, c.document_element_id AS evidence_ref, "
            "de.text, d.document_id, d.source_key FROM analysis_candidates c "
            "JOIN document_elements de ON de.document_element_id = c.document_element_id "
            "JOIN document_versions dv ON dv.document_version_id = de.document_version_id "
            "JOIN document_records d ON d.document_id = dv.document_id "
            "WHERE c.input_manifest_id = %s AND c.status = 'pending' "
            "AND (c.ordinal > %s OR (c.ordinal = %s AND c.candidate_id > %s)) "
            "ORDER BY c.ordinal, c.candidate_id LIMIT %s",
            (input_manifest_id, last_ordinal, last_ordinal, last_candidate, batch_size)).fetchall()
        if not rows:
            return
        batch = [dict(row) for row in rows]
        yield batch
        last_ordinal = batch[-1]["ordinal"]
        last_candidate = batch[-1]["candidate_id"]


def mark_candidates(conn, candidate_ids: Iterable[str], status: str,
                    error_detail: str | None = None) -> None:
    values = [(status, error_detail, candidate_id) for candidate_id in candidate_ids]
    conn.executemany(
        "UPDATE analysis_candidates SET status = %s, error_detail = %s WHERE candidate_id = %s",
        values)


def output_digest(conn, *, release_id: str, domain_id: str | None = None) -> str:
    """Hash analytical outputs in stable table/key order without materialising them."""
    digest = hashlib.sha256()
    direct = ("automated_signals", "emerging_themes", "analysis_topics",
              "analysis_prevalence_diagnostics", "analysis_model_calls")
    key_by_table = {
        "automated_signals": "signal_id", "emerging_themes": "theme_id",
        "analysis_topics": "topic_id", "analysis_prevalence_diagnostics": "prevalence_id",
        "analysis_model_calls": "model_call_id",
    }
    queries: list[tuple[str, str, list[Any]]] = []
    for table in direct:
        where = "release_id = %s"
        params: list[Any] = [release_id]
        if domain_id:
            where += " AND domain_id = %s"
            params.append(domain_id)
        queries.append((table, f"SELECT * FROM {table} WHERE {where} ORDER BY {key_by_table[table]}", params))
    signal_domain = " AND a.domain_id = %s" if domain_id else ""
    signal_params: list[Any] = [release_id] + ([domain_id] if domain_id else [])
    queries.extend([
        ("structured_signals",
         "SELECT s.* FROM structured_signals s JOIN automated_signals a ON a.signal_id = s.signal_id "
         f"WHERE a.release_id = %s{signal_domain} ORDER BY s.structured_signal_id", signal_params),
        ("analysis_verifier_results",
         "SELECT v.* FROM analysis_verifier_results v JOIN automated_signals a ON a.signal_id = v.signal_id "
         f"WHERE a.release_id = %s{signal_domain} ORDER BY v.verifier_result_id", signal_params),
    ])
    if domain_id is None:
        queries.append((
            "cross_source_signal_links",
            "SELECT * FROM cross_source_signal_links WHERE release_id = %s ORDER BY link_id",
            [release_id]))
    for table, sql, params in queries:
        cursor = conn.execute(sql, params)
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for row in rows:
                digest.update(table.encode() + b"\0")
                digest.update(json.dumps(dict(row), sort_keys=True, separators=(",", ":"),
                                         default=str).encode() + b"\n")
    return digest.hexdigest()


def complete_and_purge(conn, input_manifest_id: str, *, expected_output_sha256: str) -> None:
    manifest = conn.execute(
        "SELECT release_id, domain_id FROM analysis_input_manifests WHERE input_manifest_id = %s",
        (input_manifest_id,)).fetchone()
    if manifest is None:
        raise KeyError(input_manifest_id)
    verified = output_digest(conn, release_id=manifest["release_id"], domain_id=manifest["domain_id"])
    if verified != expected_output_sha256:
        raise RuntimeError("analysis output digest changed before detail cleanup")
    now = utcnow()
    conn.execute(
        "UPDATE analysis_input_manifests SET output_sha256 = %s, status = 'complete', "
        "detail_purged_at = %s, accumulator_json = '{}', updated_at = %s "
        "WHERE input_manifest_id = %s",
        (verified, now, now, input_manifest_id))
    for table in ("analysis_candidates", "analysis_theme_evidence",
                  "analysis_theme_documents", "analysis_theme_subjects",
                  "analysis_theme_counts"):
        conn.execute(f"DELETE FROM {table} WHERE input_manifest_id = %s", (input_manifest_id,))
    conn.execute(
        "DELETE FROM analysis_windows WHERE domain_run_id = (SELECT domain_run_id FROM "
        "analysis_input_manifests WHERE input_manifest_id = %s)", (input_manifest_id,))


def mark_failed(conn, input_manifest_id: str) -> None:
    conn.execute(
        "UPDATE analysis_input_manifests SET status = 'failed', updated_at = %s "
        "WHERE input_manifest_id = %s", (utcnow(), input_manifest_id))


def purge_failed_detail(conn, *, retention_days: int = 7,
                        now: datetime | None = None) -> int:
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(
        days=max(1, int(retention_days)))).isoformat()
    rows = conn.execute(
        "SELECT input_manifest_id FROM analysis_input_manifests "
        "WHERE status = 'failed' AND detail_purged_at IS NULL AND updated_at < %s",
        (cutoff,)).fetchall()
    ids = [row["input_manifest_id"] for row in rows]
    if not ids:
        return 0
    marks = ", ".join("%s" for _ in ids)
    for table in ("analysis_candidates", "analysis_theme_evidence",
                  "analysis_theme_documents", "analysis_theme_subjects",
                  "analysis_theme_counts"):
        conn.execute(f"DELETE FROM {table} WHERE input_manifest_id IN ({marks})", ids)
    conn.execute(
        f"DELETE FROM analysis_windows WHERE domain_run_id IN (SELECT domain_run_id FROM "
        f"analysis_input_manifests WHERE input_manifest_id IN ({marks}))", ids)
    conn.execute(
        f"UPDATE analysis_input_manifests SET detail_purged_at = %s, accumulator_json = '{{}}', "
        f"updated_at = %s WHERE input_manifest_id IN ({marks})", (utcnow(), utcnow(), *ids))
    return len(ids)

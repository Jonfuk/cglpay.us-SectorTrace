"""The 034G readiness gate, as a report.

034G (SetFit few-shot classifiers) is gated -- not on a bare count, on a set
of conditions that must all hold before training a model is worth doing:

  * >= `min_per_class` decided POSITIVE and >= `min_per_class` decided
    NEGATIVE examples per category;
  * source-system, provider and time spread across those examples (not 90
    from one council in one year);
  * enough double-reviewed items to say inter-reviewer agreement is
    acceptable;
  * room to carve a held-out eval set off before training.

This module answers "are we there yet, and if not, what is missing?" from
`claim_candidate_decisions` (034F, second cut). It is read-only and offline;
it trains nothing and writes nothing.

Positive / negative for a category C (predicate P):
  * positive -- `approved` with predicate P and `AFFIRMED`; or `corrected`
    whose `corrected_predicate` is P (the reviewer says P is right).
  * negative -- `rejected` with predicate P; or `corrected` away from P; or
    `approved` with predicate P but `NEGATED` / `HISTORICAL` / `THIRD_PARTY`
    (the chunk is about C but does not affirm it now).
One decided candidate can be a positive for one category and a negative for
another -- that is the point of capturing corrections.
"""
from __future__ import annotations

# category -> the relations.yml predicate it classifies. The plan's five;
# edit here, not in the SQL.
GATE_CATEGORIES: dict[str, str] = {
    "recruitment_pressure": "workforce.has_recruitment_pressure",
    "pay_concern": "workforce.has_pay_concern",
    "high_caseload": "workforce.has_high_caseload",
    "funding_reduction": "finance.has_funding_reduction",
    "access_problem": "service.has_access_pressure",
}

MIN_PER_CLASS = 50
HELDOUT_PER_CLASS = 15
MIN_SOURCE_SYSTEMS = 2
MIN_PROVIDERS = 5
MIN_YEARS = 3
AGREEMENT_FLOOR = 0.80
MIN_DOUBLE_REVIEWED = 10

_NEGATIVE_STATUSES = frozenset({"NEGATED", "HISTORICAL", "THIRD_PARTY", "UNKNOWN"})

_DECIDED_SQL = """
SELECT d.claim_candidate_id, d.decision, d.decided_by, d.corrected_predicate,
       c.predicate, c.assertion_status, c.subject_hint,
       e.source_system,
       substr(COALESCE(dr.published_at, e.retrieved_at, ''), 1, 4) AS year,
       dem.entity_id AS subject_entity_id
FROM claim_candidate_decisions d
JOIN document_claim_candidates c ON c.claim_candidate_id = d.claim_candidate_id
JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id
JOIN document_versions v ON v.document_version_id = dc.document_version_id
JOIN document_records dr ON dr.document_id = v.document_id
JOIN evidence_records e ON e.evidence_id = dr.evidence_id
LEFT JOIN document_concept_mentions m
       ON m.document_concept_mention_id = c.subject_mention_id
LEFT JOIN document_entity_mentions dem
       ON dem.document_element_id = m.document_element_id
      AND dem.start_offset = m.element_char_start
      AND dem.end_offset = m.element_char_end
      AND dem.matched_text = m.span_text
ORDER BY d.decided_at
"""


def _label_for(row, predicate: str) -> str | None:
    decision = row["decision"]
    if decision == "approved" and row["predicate"] == predicate:
        return "positive" if row["assertion_status"] == "AFFIRMED" else "negative"
    if decision == "corrected" and row["corrected_predicate"] == predicate:
        return "positive"
    if decision == "corrected" and row["predicate"] == predicate \
            and row["corrected_predicate"] != predicate:
        return "negative"
    if decision == "rejected" and row["predicate"] == predicate:
        return "negative"
    return None


def _provider_key(row) -> str:
    return row["subject_entity_id"] or (row["subject_hint"] or "").strip().lower() or "unknown"


def _inter_reviewer(rows: list, min_double_reviewed: int) -> dict:
    by_candidate: dict[str, dict[str, str]] = {}
    for row in rows:
        by_candidate.setdefault(row["claim_candidate_id"], {})[row["decided_by"]] = row["decision"]
    doubled = [v for v in by_candidate.values() if len(v) >= 2]
    if not doubled:
        return {"double_reviewed": 0, "agreement": None, "assessed": False}
    agreed = sum(1 for v in doubled if len(set(v.values())) == 1)
    return {
        "double_reviewed": len(doubled),
        "agreement": round(agreed / len(doubled), 4),
        "assessed": len(doubled) >= min_double_reviewed,
    }


def check(conn, *, min_per_class: int = MIN_PER_CLASS,
          heldout_per_class: int = HELDOUT_PER_CLASS,
          min_source_systems: int = MIN_SOURCE_SYSTEMS,
          min_subjects: int = MIN_PROVIDERS,
          min_years: int = MIN_YEARS,
          min_double_reviewed: int = MIN_DOUBLE_REVIEWED,
          agreement_floor: float = AGREEMENT_FLOOR) -> dict:
    rows = conn.execute(_DECIDED_SQL).fetchall()
    inter = _inter_reviewer(rows, min_double_reviewed)

    categories: dict[str, dict] = {}
    blocking: list[str] = []
    for name, predicate in GATE_CATEGORIES.items():
        pos = [r for r in rows if _label_for(r, predicate) == "positive"]
        neg = [r for r in rows if _label_for(r, predicate) == "negative"]
        examples = pos + neg

        source_systems = sorted({r["source_system"] for r in examples})
        providers = {_provider_key(r) for r in examples}
        years = sorted({r["year"] for r in examples if r["year"]})

        need = min_per_class + heldout_per_class
        shortfalls: list[str] = []
        if len(pos) < need:
            shortfalls.append(f"positives {len(pos)} < {need} (need {min_per_class} to train "
                              f"+ {heldout_per_class} held out)")
        if len(neg) < need:
            shortfalls.append(f"negatives {len(neg)} < {need}")
        if len(source_systems) < min_source_systems:
            shortfalls.append(f"source systems {len(source_systems)} < {min_source_systems}")
        if len(providers) < min_subjects:
            shortfalls.append(f"distinct subjects {len(providers)} < {min_subjects}")
        if len(years) < min_years:
            shortfalls.append(f"distinct years {len(years)} < {min_years}")

        ready = not shortfalls
        categories[name] = {
            "predicate": predicate,
            "positive": len(pos),
            "negative": len(neg),
            "source_systems": source_systems,
            "distinct_subjects": len(providers),
            "years": years,
            "heldout_feasible": len(pos) >= need and len(neg) >= need,
            "shortfalls": shortfalls,
            "ready": ready,
        }
        blocking.extend(f"{name}: {s}" for s in shortfalls)

    reviewer_ok = bool(inter["assessed"]) and (inter["agreement"] or 0.0) >= agreement_floor
    if not inter["assessed"]:
        blocking.append(f"inter-reviewer agreement not assessed "
                        f"({inter['double_reviewed']}/{min_double_reviewed} double-reviewed)")
    elif not reviewer_ok:
        blocking.append(f"inter-reviewer agreement {inter['agreement']} < {agreement_floor}")

    return {
        "min_per_class": min_per_class,
        "heldout_per_class": heldout_per_class,
        "thresholds": {"source_systems": min_source_systems, "distinct_subjects": min_subjects,
                       "years": min_years, "agreement": agreement_floor},
        "n_decisions": len(rows),
        "n_decided_candidates": len({r["claim_candidate_id"] for r in rows}),
        "inter_reviewer": inter,
        "categories": categories,
        "ready": all(c["ready"] for c in categories.values()) and reviewer_ok,
        "blocking": blocking,
    }

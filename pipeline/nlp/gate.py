"""The 034G readiness gate, as a report.

034G (SetFit few-shot classifiers) is gated -- not on a bare count, on a set
of conditions before training a model is worth doing. Per category:

  * >= `min_per_class` decided POSITIVE and >= `min_per_class` decided
    NEGATIVE examples. This floor was 50 + a 15 held-out margin (65). After
    D-08 the relation patterns were rebuilt for precision, and model-assisted
    triage over the whole corpus then showed the honest supply: ~20-40 real
    affirmative claims per gate predicate, not 65 -- England-wide committee
    papers discuss these pressures mostly as things being managed *down*. The
    floor is now 25 + a 10 held-out margin (35), a deliberate compromise: a
    SetFit head on 25 positives is thin, few-shot's own premise, and any
    figure it later supports carries that in its caveat. Below 25 do not
    train the head at all;
  * authority and time spread across those examples (not 40 from one council
    in one year) -- authority, not source_system: the whole NLP corpus is two
    source systems, but every committee paper carries an authority_ons_code,
    and the council is the unit that must vary. `source_systems` stays in the
    report for the record;
  * room to carve a held-out eval set off before training.

And across the set:

  * `min_categories_ready` of the categories clearing the per-category bar --
    a quorum, not all of them. SetFit builds one binary head per category, so
    a category the corpus cannot yet feed (`funding_reduction` today: ~54
    AFFIRMED candidates exist, below the floor) should not hold back training
    the heads that are ready. Laggards are reported by name in `advisory`,
    not `blocking`;
  * enough double-reviewed items to say inter-reviewer agreement is
    acceptable. This one has no quorum and no code route around it -- it needs
    a second named reviewer.

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

# category -> the relations.yml predicate it classifies. Edit here, not in the
# SQL.
#
# These six are not the plan's original five. The original set
# (recruitment_pressure, pay_concern, high_caseload, funding_reduction,
# access_problem) was chosen before any extraction had run. After one full NLP
# cycle the counts are in, and three of those five cannot reach the gate's
# per-class floor no matter how the review pass goes -- the corpus simply does
# not contain 65 affirmed candidates for them (pay_concern 21, high_caseload 6,
# recruitment_pressure 44). access_problem's predicate
# (service.has_access_pressure) is never emitted at all; the signal lands as
# service.reports_waiting_time.
#
# A gate that can never go green reports nothing useful. This set is redrawn
# around the predicates the one completed cycle actually produced in volume,
# keeping the original's "adverse condition, not a process event" character
# (so commissioning.is_recommissioning, the single largest bucket at ~1k, is
# deliberately left out -- it is churn, not a pressure claim a pay-campaign
# classifier needs). funding_reduction survives from the original set on
# 117 affirmed; it and cost_pressure have the thinnest easy-negative pools
# (~44 and ~36 non-affirmed) and will lean on review rejections to reach 65.
GATE_CATEGORIES: dict[str, str] = {
    "vacancy_pressure": "workforce.has_vacancy_pressure",
    "agency_reliance": "workforce.relies_on_agency",
    "tupe_transfer": "workforce.undergoes_tupe",
    "funding_reduction": "finance.has_funding_reduction",
    "cost_pressure": "finance.has_cost_pressure",
    "waiting_time": "service.reports_waiting_time",
}

MIN_PER_CLASS = 25        # was 50. Lowered after D-08 -- the corpus supplies
                          # ~20-40 real affirmative claims per gate predicate,
                          # not 50+. A deliberate compromise; see the module
                          # docstring. Do not train a head below this.
HELDOUT_PER_CLASS = 10    # was 15.
MIN_AUTHORITIES = 3        # distinct local authorities behind a category's
                          # examples. Replaces a source-system count: the whole
                          # NLP corpus is two source systems, but every
                          # committee paper carries an authority_ons_code, and
                          # "not 40 rows from one council" is the collapse this
                          # actually guards against.
MIN_PROVIDERS = 5
MIN_YEARS = 3
AGREEMENT_FLOOR = 0.80
MIN_DOUBLE_REVIEWED = 10
MIN_CATEGORIES_READY = 5   # of len(GATE_CATEGORIES). A category the corpus
                          # cannot yet feed does not block training the heads
                          # that are ready; it stays named in `advisory`.

_NEGATIVE_STATUSES = frozenset({"NEGATED", "HISTORICAL", "THIRD_PARTY", "UNKNOWN"})

_DECIDED_SQL = """
SELECT d.claim_candidate_id, d.decision, d.decided_by, d.corrected_predicate,
       c.predicate, c.assertion_status, c.subject_hint,
       e.source_system, dr.source_key,
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


def _authority_key(row) -> str:
    """The local authority behind a decided example. `source_key` for
    committee_papers / cdp_documents is "<authority_ons_code>|<url>"; a key with
    no pipe (any other document source) is used whole."""
    key = row["source_key"] or ""
    return key.split("|", 1)[0] or "unknown"


def _provider_key(row) -> str:
    # a resolved entity is the true subject; without one, the authority is a
    # better distinctness signal than the generic anaphor ("the service",
    # "staff") the gate_coverage slice (promote.py) produces in bulk.
    return row["subject_entity_id"] or _authority_key(row)


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
          min_authorities: int = MIN_AUTHORITIES,
          min_subjects: int = MIN_PROVIDERS,
          min_years: int = MIN_YEARS,
          min_double_reviewed: int = MIN_DOUBLE_REVIEWED,
          min_categories_ready: int = MIN_CATEGORIES_READY,
          agreement_floor: float = AGREEMENT_FLOOR) -> dict:
    rows = conn.execute(_DECIDED_SQL).fetchall()
    inter = _inter_reviewer(rows, min_double_reviewed)

    categories: dict[str, dict] = {}
    for name, predicate in GATE_CATEGORIES.items():
        pos = [r for r in rows if _label_for(r, predicate) == "positive"]
        neg = [r for r in rows if _label_for(r, predicate) == "negative"]
        examples = pos + neg

        source_systems = sorted({r["source_system"] for r in examples})
        authorities = {_authority_key(r) for r in examples}
        providers = {_provider_key(r) for r in examples}
        years = sorted({r["year"] for r in examples if r["year"]})

        need = min_per_class + heldout_per_class
        shortfalls: list[str] = []
        if len(pos) < need:
            shortfalls.append(f"positives {len(pos)} < {need} (need {min_per_class} to train "
                              f"+ {heldout_per_class} held out)")
        if len(neg) < need:
            shortfalls.append(f"negatives {len(neg)} < {need}")
        if len(authorities) < min_authorities:
            shortfalls.append(f"distinct authorities {len(authorities)} < {min_authorities}")
        if len(providers) < min_subjects:
            shortfalls.append(f"distinct subjects {len(providers)} < {min_subjects}")
        if len(years) < min_years:
            shortfalls.append(f"distinct years {len(years)} < {min_years}")

        categories[name] = {
            "predicate": predicate,
            "positive": len(pos),
            "negative": len(neg),
            "source_systems": source_systems,
            "distinct_authorities": len(authorities),
            "distinct_subjects": len(providers),
            "years": years,
            "heldout_feasible": len(pos) >= need and len(neg) >= need,
            "shortfalls": shortfalls,
            "ready": not shortfalls,
        }

    ready_names = [n for n, c in categories.items() if c["ready"]]
    laggards = [n for n, c in categories.items() if not c["ready"]]
    quorum_ok = len(ready_names) >= min_categories_ready

    blocking: list[str] = []
    advisory: list[str] = []
    # a laggard's detail blocks only while the quorum is unmet; once it is met
    # the same lines are advisory -- the head is corpus-limited, not the gate.
    for name in laggards:
        (advisory if quorum_ok else blocking).extend(
            f"{name}: {s}" for s in categories[name]["shortfalls"])
    if not quorum_ok:
        blocking.append(f"only {len(ready_names)}/{len(categories)} categories ready "
                        f"(need {min_categories_ready})")
    elif laggards:
        advisory.append(f"{len(ready_names)}/{len(categories)} categories ready; "
                        f"corpus-limited, not blocking: {', '.join(sorted(laggards))}")

    reviewer_ok = bool(inter["assessed"]) and (inter["agreement"] or 0.0) >= agreement_floor
    if not inter["assessed"]:
        blocking.append(f"inter-reviewer agreement not assessed "
                        f"({inter['double_reviewed']}/{min_double_reviewed} double-reviewed)")
    elif not reviewer_ok:
        blocking.append(f"inter-reviewer agreement {inter['agreement']} < {agreement_floor}")

    return {
        "min_per_class": min_per_class,
        "heldout_per_class": heldout_per_class,
        "thresholds": {"distinct_authorities": min_authorities, "distinct_subjects": min_subjects,
                       "years": min_years, "agreement": agreement_floor,
                       "categories_ready": min_categories_ready},
        "n_decisions": len(rows),
        "n_decided_candidates": len({r["claim_candidate_id"] for r in rows}),
        "inter_reviewer": inter,
        "categories": categories,
        "categories_ready": len(ready_names),
        "ready": quorum_ok and reviewer_ok,
        "blocking": blocking,
        "advisory": advisory,
    }

"""Machine claim candidates -- spans in one sentence -> `document_claim_candidates`.

034F, the high-volume machine layer. A candidate is a (subject, predicate,
object) triple assembled from 034D spans and 034E assertion status using the
ontology's CONTROLLED predicate vocabulary. Two triggers, and only these:

  * a controlled concept -> predicate mapping (`CONCEPT_PREDICATE`), fired
    only when that concept's phrase is actually present in the sentence; or
  * a predicate pattern from `ontology/patterns/*.yml` (`kind: predicate`).

Co-occurrence alone never yields a candidate: two spans sitting in the same
sentence is not a claim. The subject must be a span of the kind the
predicate's `subject` allows, or -- for `service` / `workforce` predicates --
an explicit anaphor ("the service", "staff", …), recorded in `subject_hint`.

Nothing here is evidence or a claim. `relation_score` ranks candidates for a
reviewer and is never multiplied into a figure. Promotion into `review_queue`
is a separate policy (`pipeline/nlp/promote.py`); only a person's decision
produces a `graph_claims` draft.
"""
from __future__ import annotations

import hashlib
import re

from pipeline.nlp import ontology as ontology_mod
from pipeline.nlp import runs
from pipeline.nlp.context import CueTagger, split_sentences

STAGE = "relations"
EXTRACTOR = "nlp-rule"

# The ontology's controlled situation-concept -> predicate map. Editing this is
# a deliberate widening of what the layer will propose, the same weight as
# adding a predicate to relations.yml.
CONCEPT_PREDICATE: dict[str, str] = {
    "workforce.recruitment_difficulty": "workforce.has_recruitment_pressure",
    "workforce.retention_difficulty": "workforce.has_retention_pressure",
    "workforce.vacancy": "workforce.has_vacancy_pressure",
    "workforce.turnover": "workforce.has_turnover",
    "workforce.caseload": "workforce.has_high_caseload",
    "workforce.agency_reliance": "workforce.relies_on_agency",
    "workforce.pay_concern": "workforce.has_pay_concern",
    "workforce.morale": "workforce.has_low_morale",
    "workforce.sickness_absence": "workforce.has_sickness_absence",
    "workforce.tupe": "workforce.undergoes_tupe",
    "finance.funding_reduction": "finance.has_funding_reduction",
    "finance.cost_pressure": "finance.has_cost_pressure",
    "finance.savings_target": "finance.has_savings_target",
    "commissioning.recommissioning": "commissioning.is_recommissioning",
    "commissioning.contract_extension": "commissioning.extended_contract",
    "outcome.waiting_time": "service.reports_waiting_time",
    "outcome.unmet_need": "outcome.has_unmet_need",
    "outcome.drug_related_death": "outcome.reports_drug_related_deaths",
}

_SUBJECT_LABELS: dict[str, frozenset[str]] = {
    "provider": frozenset({"PROVIDER"}),
    "service": frozenset({"SERVICE"}),
    "commissioner": frozenset({"COMMISSIONER"}),
    "area": frozenset({"LOCATION"}),
    # a workforce claim is about the ORGANISATION whose staff it is -- the
    # ROLE span ("recovery workers") is context, not the subject entity.
    "workforce": frozenset({"PROVIDER", "COMMISSIONER"}),
}
# Tried only when the primary label isn't in the sentence: a provider stands
# in for the service it runs, a service (or a bare ROLE) for a workforce
# claim, a commissioner (a local authority) for its area.
_SUBJECT_FALLBACK_LABELS: dict[str, frozenset[str]] = {
    "service": frozenset({"PROVIDER"}),
    "workforce": frozenset({"SERVICE", "ROLE"}),
    "area": frozenset({"COMMISSIONER"}),
}
# subjects where a bare anaphor is an acceptable last resort.
_ANAPHORIC_SUBJECTS = frozenset({"service", "workforce"})
_ANAPHOR = re.compile(
    r"\b(the (service|provider|team|scheme|contract|partnership)|our (service|staff|team)|"
    r"\bstaff\b|the workforce|the (?:local )?authority)\b", re.IGNORECASE)

_LITERAL_PATTERNS = {
    "money": re.compile(r"£\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:m|bn|k|million|billion))?"
                        r"|\b\d[\d,]*(?:\.\d+)?\s?per cent\b|\b\d[\d,]*(?:\.\d+)?%"),
    "count": re.compile(r"\b\d[\d,]*(?:\.\d+)?%?\b"),
    "date": re.compile(r"\bQ[1-4]\s?(?:19|20)\d{2}\b|\b(?:19|20)\d{2}(?:[/-]\d{2})?\b"),
}


def _score(pattern_strength: float, gap: int, assertion_confidence: float) -> float:
    proximity = 1.0 - min(gap, 140) / 140
    raw = 0.30 + 0.25 * pattern_strength + 0.25 * proximity + 0.20 * assertion_confidence
    return round(max(0.0, min(1.0, raw)), 4)


def _extract_literal(sentence: str, kind: str, near: int) -> str | None:
    pattern = _LITERAL_PATTERNS.get(kind)
    if pattern is None:
        return None
    best: tuple[int, str] | None = None
    for m in pattern.finditer(sentence):
        gap = abs(m.start() - near)
        if best is None or gap < best[0]:
            best = (gap, m.group(0).strip())
    return best[1] if best else None


class _SentenceSpan:
    __slots__ = ("mention_id", "label", "concept_id", "start", "end",
                 "assertion_status", "assertion_confidence")

    def __init__(self, mention_id, label, concept_id, start, end,
                 assertion_status, assertion_confidence):
        self.mention_id = mention_id
        self.label = label
        self.concept_id = concept_id
        self.start = start
        self.end = end
        self.assertion_status = assertion_status
        self.assertion_confidence = assertion_confidence


class CandidateTriple:
    __slots__ = ("subject_mention_id", "subject_hint", "predicate",
                 "object_concept_id", "object_literal", "assertion_status",
                 "assertion_confidence", "score", "trigger_start", "trigger_end")

    def __init__(self, *, subject_mention_id, subject_hint, predicate,
                 object_concept_id, object_literal, assertion_status,
                 assertion_confidence, score, trigger_start, trigger_end):
        self.subject_mention_id = subject_mention_id
        self.subject_hint = subject_hint
        self.predicate = predicate
        self.object_concept_id = object_concept_id
        self.object_literal = object_literal
        self.assertion_status = assertion_status
        self.assertion_confidence = assertion_confidence
        self.score = score
        self.trigger_start = trigger_start
        self.trigger_end = trigger_end


def _closest(spans: list[_SentenceSpan], labels: frozenset[str], before: int):
    pool = [s for s in spans if s.label in labels]
    if not pool:
        return None
    preceding = [s for s in pool if s.end <= before]
    return min(preceding or pool, key=lambda s: abs(s.start - before))


def _find_subject(rel, spans: list[_SentenceSpan], before: int):
    """The closest acceptable subject span for `rel`: the predicate's own
    subject label first, then the documented fallbacks. None if neither is in
    the sentence."""
    return (_closest(spans, _SUBJECT_LABELS.get(rel.subject, frozenset()), before)
            or _closest(spans, _SUBJECT_FALLBACK_LABELS.get(rel.subject, frozenset()), before))


def assemble(onto: ontology_mod.Ontology, sentence: str,
             spans: list[_SentenceSpan]) -> list[CandidateTriple]:
    tagger = CueTagger()
    out: list[CandidateTriple] = []
    made: set[tuple] = set()

    def _emit(predicate, trigger_start, trigger_end, pattern_strength):
        rel = onto.relation(predicate)
        if rel is None:
            return
        subject = _find_subject(rel, spans, trigger_start)
        subject_hint = None
        if subject is None:
            if rel.subject in _ANAPHORIC_SUBJECTS and (anaphor := _ANAPHOR.search(sentence)):
                subject_hint = anaphor.group(0)
            else:
                return
        object_concept_id = object_literal = None
        object_penalty = 1.0
        if rel.object.startswith("concept:"):
            category = rel.object.split(":", 1)[1]
            obj = next((s for s in onto.match_spans(sentence)
                        if category in (onto.concept(s.concept_id).categories if onto.concept(s.concept_id) else ())
                        and not (trigger_start <= s.char_start < trigger_end)), None)
            if obj is None:
                return
            object_concept_id = obj.concept_id
        elif rel.object.startswith("literal:"):
            # The literal is what a reviewer records; when the sentence carries
            # none, the triple still matters (a negated or historical
            # "funding reduction" with no figure is a real signal) -- keep it,
            # at a softer score.
            object_literal = _extract_literal(sentence, rel.object.split(":", 1)[1], trigger_end)
            if object_literal is None:
                object_penalty = 0.7

        # The assertion that matters is the one on the TRIGGER (the pressure
        # concept / predicate phrase), not on the subject: "CGL reports no
        # recruitment difficulties" negates the difficulties, not CGL.
        call = tagger.tag(sentence, trigger_start, trigger_end)
        status, confidence = call.status, call.confidence

        anchor = subject.end if subject is not None else trigger_start
        gap = abs(trigger_start - anchor)
        key = (subject.mention_id if subject else subject_hint, predicate,
               object_concept_id, object_literal)
        if key in made:
            return
        made.add(key)
        out.append(CandidateTriple(
            subject_mention_id=subject.mention_id if subject else None,
            subject_hint=subject_hint, predicate=predicate,
            object_concept_id=object_concept_id, object_literal=object_literal,
            assertion_status=status, assertion_confidence=confidence,
            score=round(_score(pattern_strength, gap, confidence) * object_penalty, 4),
            trigger_start=trigger_start, trigger_end=trigger_end))

    # 1) controlled concept -> predicate
    for cspan in onto.match_spans(sentence):
        predicate = CONCEPT_PREDICATE.get(cspan.concept_id)
        if predicate:
            _emit(predicate, cspan.char_start, cspan.char_end, pattern_strength=0.7)

    # 2) predicate patterns
    for group in onto.patterns.values():
        for pattern in group:
            if pattern.kind != "predicate":
                continue
            for m in re.finditer(pattern.regex, sentence, re.IGNORECASE):
                _emit(pattern.target, m.start(), m.end(), pattern_strength=0.85)

    return out


# --- the stage -----------------------------------------------------

def _candidate_id(chunk_id, subject_mention_id, predicate, obj, char_start, char_end) -> str:
    seed = f"{chunk_id}|{subject_mention_id}|{predicate}|{obj}|{char_start}|{char_end}|{EXTRACTOR}"
    return "cc-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _chunk_spans(conn, chunk_id: str) -> list:
    return conn.execute(
        "SELECT m.document_concept_mention_id AS mid, m.label, m.concept_id, "
        "m.char_start, m.char_end, a.assertion_status, a.detector_confidence "
        "FROM document_concept_mentions m "
        "LEFT JOIN document_assertions a ON a.concept_mention_id = m.document_concept_mention_id "
        "  AND a.superseded = 0 "
        "WHERE m.document_chunk_id = ? AND m.superseded = 0 ORDER BY m.char_start",
        (chunk_id,)).fetchall()


def relations_for_chunk(conn, onto, chunk_row, nlp_run_id, version: str) -> int:
    spans = _chunk_spans(conn, chunk_row["document_chunk_id"])
    conn.execute(
        "DELETE FROM document_claim_candidates WHERE document_chunk_id = ? "
        "AND relation_extractor = ? AND relation_extractor_version = ?",
        (chunk_row["document_chunk_id"], EXTRACTOR, version))
    text = chunk_row["text"] or ""
    now = runs.utcnow()
    written = 0
    for sentence, offset in split_sentences(text):
        in_sentence = [
            _SentenceSpan(s["mid"], s["label"], s["concept_id"],
                          s["char_start"] - offset, s["char_end"] - offset,
                          s["assertion_status"], s["detector_confidence"])
            for s in spans
            if offset <= s["char_start"] and s["char_end"] <= offset + len(sentence)]
        for triple in assemble(onto, sentence, in_sentence):
            obj = triple.object_concept_id or triple.object_literal
            cid = _candidate_id(chunk_row["document_chunk_id"], triple.subject_mention_id,
                                triple.predicate, obj, offset, offset + len(sentence))
            conn.execute(
                "INSERT INTO document_claim_candidates (claim_candidate_id, document_chunk_id, "
                "subject_mention_id, subject_hint, predicate, object_concept_id, object_literal, "
                "assertion_status, relation_extractor, relation_extractor_version, relation_score, "
                "evidence_span, char_start, char_end, status, superseded, nlp_run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', 0, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (cid, chunk_row["document_chunk_id"], triple.subject_mention_id,
                 triple.subject_hint, triple.predicate, triple.object_concept_id,
                 triple.object_literal, triple.assertion_status, EXTRACTOR, version,
                 triple.score, sentence, offset, offset + len(sentence), nlp_run_id, now))
            written += 1
    return written


def _live_chunks(conn, source_system, limit):
    sql = (
        "SELECT dc.document_chunk_id, dc.text FROM document_chunks dc "
        "JOIN document_concept_mentions m ON m.document_chunk_id = dc.document_chunk_id "
        "  AND m.superseded = 0 "
        "JOIN document_versions v ON v.document_version_id = dc.document_version_id "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE dc.superseded = 0")
    params: list = []
    if source_system:
        sql += " AND e.source_system = ?"
        params.append(source_system)
    sql += " GROUP BY dc.document_chunk_id ORDER BY MIN(dc.created_at), dc.document_chunk_id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def run(conn, *, source_system: str | None = None, limit: int | None = None,
        dry_run: bool = False) -> dict:
    """Assemble machine claim candidates for every chunk that has spans.
    Bounded by `limit`; safe to repeat. Fetches nothing."""
    onto = ontology_mod.default()
    version = f"{EXTRACTOR}-1@{onto.version[:14]}"
    config = {"extractor": EXTRACTOR, "version": version, "ontology_version": onto.version,
              "source_system": source_system, "limit": limit}
    run_id = runs.start_run(conn, STAGE, config=config, ontology_version=onto.version,
                            input_scope={"source_system": source_system, "limit": limit})
    chunks = _live_chunks(conn, source_system, limit)
    written = 0
    try:
        for chunk_row in chunks:
            written += relations_for_chunk(conn, onto, chunk_row, run_id, version)
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(conn, run_id, status="failed", rows_processed=len(chunks),
                        rows_written=written, error=f"{type(exc).__name__}: {exc}")
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=len(chunks), rows_written=written)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"run_id": run_id, "extractor_version": version, "chunks": len(chunks),
            "candidates": written, "dry_run": dry_run}

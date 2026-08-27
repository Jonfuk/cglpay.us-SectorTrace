"""Assertion / context detection -- `document_concept_mentions` ->
`document_assertions`.

034E. For each labelled span, decide whether its sentence AFFIRMS the
concept, NEGATES it, places it in the past (HISTORICAL), makes it
HYPOTHETICAL or CONDITIONAL, or attributes it to a THIRD_PARTY -- so
"no recruitment difficulties this year" is not stored as the same fact as
"recruitment difficulties remain a significant risk".

Two detectors:

* ``cue`` -- an always-on stdlib cue tagger. Regex cue families with a
  direction and a scope window; the target span is modified by a cue on the
  correct side unless a termination word (`but`, `however`, `;`, …) breaks
  the scope first. When several families apply, precedence is
  NEGATED > HISTORICAL > HYPOTHETICAL > CONDITIONAL > THIRD_PARTY.
* ``medspacy`` -- medSpaCy `ConText` where that optional path is installed
  (not in the `nlp` extra by default: spaCy pipeline models do not install
  as clean dependencies -- `pip install medspacy` plus a spaCy model, then
  `--detector medspacy`).

`assertion_status` and `detector_confidence` are stored separately.
`UNKNOWN` is only for a span whose sentence cannot be located -- never a
default; a span with no cue is `AFFIRMED` at a deliberately modest
confidence.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from pipeline.nlp import runs

STAGE = "context"

STATUSES = ("AFFIRMED", "NEGATED", "HISTORICAL", "HYPOTHETICAL",
            "CONDITIONAL", "THIRD_PARTY", "UNKNOWN")

DETECTOR_NAME = "cue-tagger"
DETECTOR_VERSION = "1"

# How far from the target a cue may sit and still modify it.
_WINDOW = 70

_TERMINATION = re.compile(
    r"\b(but|however|although|whereas|nonetheless|nevertheless|though|yet)\b|;", re.IGNORECASE)

# (compiled cue, status, direction). direction: 'f' cue precedes target,
# 'b' cue follows target, 'x' either side.
_CUES: list[tuple[re.Pattern, str, str]] = []


def _cue(pattern: str, status: str, direction: str) -> None:
    _CUES.append((re.compile(pattern, re.IGNORECASE), status, direction))


# --- NEGATED -------------------------------------------------------------
for _p in (r"\bno\b", r"\bnot\b", r"\bnone\b", r"\bnever\b", r"\bwithout\b",
           r"\bdenies?\b", r"\bdenied\b", r"\bdid not\b", r"\b(was|were|has|have|had) not\b",
           r"\bthere (is|are|was|were) no\b", r"\bno (evidence|indication|sign|reports?) of\b",
           r"\bno significant\b", r"\bfree (from|of)\b", r"\babsence of\b", r"\bruled out\b",
           r"\bnot (an )?(issue|problem|concern)\b"):
    _cue(_p, "NEGATED", "f")
for _p in (r"\bnot (identified|found|reported|raised|noted|present|observed)\b",
           r"\b(were|was) (excluded|not identified)\b", r"\bunremarkable\b",
           r"\bhave not been (identified|reported|raised)\b"):
    _cue(_p, "NEGATED", "b")

# --- HISTORICAL --------------------------------------------------------
for _p in (r"\bhistory of\b", r"\bpreviously\b", r"\bformerly\b", r"\bin the past\b",
           r"\bused to\b", r"\bhad (been|previously)\b", r"\bhistorically\b",
           r"\bprior to\b", r"\bearlier (this|last) (year|month|quarter)\b",
           r"\blast year\b", r"\bin (19|20)\d{2}\b"):
    _cue(_p, "HISTORICAL", "f")
for _p in (r"\b(has|had|have|since|now) (since )?(been )?resolved\b", r"\bno longer\b",
           r"\bhad resolved\b", r"\bceased\b", r"\bdiscontinued\b", r"\bwas resolved\b",
           r"\bhad been (addressed|resolved)\b"):
    _cue(_p, "HISTORICAL", "x")

# --- HYPOTHETICAL ----------------------------------------------------
for _p in (r"\bproposed\b", r"\bplanned\b", r"\bplans? to\b", r"\bunder consideration\b",
           r"\bbeing considered\b", r"\bpotential(ly)?\b", r"\bpossible\b",
           r"\bpossibility of\b", r"\brisk (of|that)\b", r"\b(may|might|could|would|should)\b",
           r"\bto (prevent|avoid|mitigate)\b", r"\bin the event of\b", r"\banticipated\b",
           r"\bexpected to\b", r"\bforecast\b", r"\bprojected\b", r"\bif .* were to\b"):
    _cue(_p, "HYPOTHETICAL", "f")

# --- CONDITIONAL ---------------------------------------------------
for _p in (r"\bif\b", r"\bunless\b", r"\bsubject to\b", r"\bprovided (that|the)\b",
           r"\bcontingent on\b", r"\bdepend(ing|ent) on\b", r"\bshould the\b",
           r"\bonly if\b", r"\bin cases where\b", r"\bconditional on\b"):
    _cue(_p, "CONDITIONAL", "f")

# --- THIRD_PARTY ------------------------------------------------
for _p in (r"\bother (authorities|providers|areas|councils|boards|local authorities|regions|"
           r"partnerships?|parts of the country)\b",
           r"\banother (council|authority|provider|area|board)\b",
           r"\bneighbouring (authorit|area|council|board)\w*\b",
           r"\belsewhere\b", r"\bnationally\b", r"\bregionally\b", r"\bthe national picture\b",
           r"\bacross the country\b", r"\bin other (areas|parts|regions)\b",
           r"\baccording to\b", r"\bthe report (states|notes|says|found|indicates)\b",
           r"\bas reported (by|in)\b", r"\bit was reported that\b", r"\breportedly\b"):
    _cue(_p, "THIRD_PARTY", "x")

_PRECEDENCE = {"NEGATED": 0, "HISTORICAL": 1, "HYPOTHETICAL": 2,
               "CONDITIONAL": 3, "THIRD_PARTY": 4}
_STRENGTH = {"NEGATED": 0.85, "HISTORICAL": 0.75, "HYPOTHETICAL": 0.7,
             "CONDITIONAL": 0.7, "THIRD_PARTY": 0.7}
_AFFIRMED_CONFIDENCE = 0.6

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'‘“])")


class ContextUnavailable(RuntimeError):
    """The requested detector needs a dependency that is not installed."""


@dataclass(frozen=True)
class Assertion:
    status: str
    confidence: float
    cue_text: str | None
    cue_start: int | None
    cue_end: int | None


# --- sentence handling -------------------------------------------------

def split_sentences(text: str) -> list[tuple[str, int]]:
    """(sentence, offset_into_text) for each sentence. A newline is also a
    hard boundary -- chunked committee-paper text is full of heading-like
    fragments that never end in a full stop."""
    out: list[tuple[str, int]] = []
    for line_match in re.finditer(r"[^\n]+", text or ""):
        base = line_match.start()
        line = line_match.group(0)
        pos = 0
        for part in _SENTENCE_SPLIT.split(line):
            idx = line.index(part, pos)
            out.append((part, base + idx))
            pos = idx + len(part)
    return out


def sentence_for(text: str, span_start: int, span_end: int) -> tuple[str, int, int] | None:
    """The sentence containing [span_start, span_end), and the span's offsets
    inside it. None when the span falls outside every sentence."""
    for sentence, offset in split_sentences(text):
        if offset <= span_start and span_end <= offset + len(sentence):
            return sentence, span_start - offset, span_end - offset
    return None


# --- the cue tagger --------------------------------------------------

class CueTagger:
    name = DETECTOR_NAME
    version = DETECTOR_VERSION

    def tag(self, sentence: str, span_start: int, span_end: int) -> Assertion:
        best: tuple[int, float, re.Match, str] | None = None  # (precedence, confidence, cue, status)
        for pattern, status, direction in _CUES:
            for cue in pattern.finditer(sentence):
                gap = self._gap(sentence, cue, span_start, span_end, direction)
                if gap is None or gap > _WINDOW:
                    continue
                confidence = round(_STRENGTH[status] * (1.0 - min(gap, _WINDOW) / (_WINDOW * 3)), 4)
                rank = (_PRECEDENCE[status], -confidence)
                if best is None or rank < (best[0], -best[1]):
                    best = (_PRECEDENCE[status], confidence, cue, status)
        if best is None:
            return Assertion("AFFIRMED", _AFFIRMED_CONFIDENCE, None, None, None)
        _, confidence, cue, status = best
        return Assertion(status, confidence, cue.group(0), cue.start(), cue.end())

    @staticmethod
    def _gap(sentence: str, cue: re.Match, span_start: int, span_end: int,
             direction: str) -> int | None:
        """Character gap between cue and target on the allowed side, or None if
        the cue is on the wrong side or a termination word sits between."""
        if direction in ("f", "x") and cue.end() <= span_start:
            between = sentence[cue.end():span_start]
            if not _TERMINATION.search(between):
                return span_start - cue.end()
        if direction in ("b", "x") and cue.start() >= span_end:
            between = sentence[span_end:cue.start()]
            if not _TERMINATION.search(between):
                return cue.start() - span_end
        return None


class MedspacyContextTagger:
    name = "medspacy-context"

    def __init__(self):
        self._nlp = None
        self.version = "medspacy"

    def _load(self):
        if self._nlp is not None:
            return
        try:
            import medspacy  # noqa: PLC0415 - optional path
        except ImportError as exc:  # pragma: no cover
            raise ContextUnavailable(
                "medSpaCy is not installed. `pip install medspacy` plus a spaCy "
                "model, then --detector medspacy. The stdlib cue tagger is the "
                "default and needs nothing."
            ) from exc
        self._nlp = medspacy.load(medspacy_enable=["medspacy_context"])
        self.version = f"medspacy-{getattr(medspacy, '__version__', '?')}"

    def tag(self, sentence: str, span_start: int, span_end: int) -> Assertion:  # pragma: no cover
        self._load()
        doc = self._nlp(sentence)
        target_text = sentence[span_start:span_end].strip()
        mapping = {
            "NEGATED_EXISTENCE": "NEGATED", "HISTORICAL": "HISTORICAL",
            "HYPOTHETICAL": "HYPOTHETICAL", "POSSIBLE_EXISTENCE": "HYPOTHETICAL",
            "FAMILY": "THIRD_PARTY", "OTHER_EXPERIENCER": "THIRD_PARTY",
        }
        for ent in doc.ents:
            if ent.text.strip() != target_text:
                continue
            for modifier in getattr(ent._, "modifiers", []):
                mapped = mapping.get(str(modifier.category).upper())
                if mapped:
                    cue = modifier.modifier_span
                    return Assertion(mapped, 0.8, cue.text, cue.start_char, cue.end_char)
        return Assertion("AFFIRMED", _AFFIRMED_CONFIDENCE, None, None, None)


def get_tagger(name: str | None):
    if not name or name == "cue":
        return CueTagger()
    if name == "medspacy":
        return MedspacyContextTagger()
    raise ContextUnavailable(f"unknown detector {name!r} (expected 'cue' or 'medspacy')")


# --- the stage -----------------------------------------------------

def _assertion_id(concept_mention_id: str, detector_name: str, detector_version: str) -> str:
    seed = f"{concept_mention_id}|{detector_name}|{detector_version}"
    return "da-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _entity_mention_id(conn, mention) -> str | None:
    row = conn.execute(
        "SELECT document_entity_mention_id FROM document_entity_mentions "
        "WHERE document_element_id = ? AND start_offset = ? AND end_offset = ? "
        "AND matched_text = ? LIMIT 1",
        (mention["document_element_id"], mention["element_char_start"],
         mention["element_char_end"], mention["span_text"])).fetchone()
    return row["document_entity_mention_id"] if row else None


def tag_chunk(conn, tagger, chunk_row, nlp_run_id: str | None) -> int:
    mentions = conn.execute(
        "SELECT document_concept_mention_id, document_element_id, span_text, "
        "char_start, char_end, element_char_start, element_char_end "
        "FROM document_concept_mentions WHERE document_chunk_id = ? AND superseded = 0",
        (chunk_row["document_chunk_id"],)).fetchall()
    if not mentions:
        return 0
    conn.execute(
        "DELETE FROM document_assertions WHERE document_chunk_id = ? AND detector_name = ? "
        "AND detector_version = ?",
        (chunk_row["document_chunk_id"], tagger.name, tagger.version))

    chunk_text = chunk_row["text"] or ""
    now = runs.utcnow()
    written = 0
    for mention in mentions:
        located = sentence_for(chunk_text, mention["char_start"], mention["char_end"])
        if located is None:
            sentence, status, result = "", "UNKNOWN", Assertion("UNKNOWN", 0.0, None, None, None)
        else:
            sentence, s_start, s_end = located
            result = tagger.tag(sentence, s_start, s_end)
            status = result.status
        conn.execute(
            "INSERT INTO document_assertions (document_assertion_id, document_chunk_id, "
            "concept_mention_id, entity_mention_id, assertion_status, detector_name, "
            "detector_version, detector_confidence, cue_text, cue_start, cue_end, "
            "sentence_sha256, superseded, nlp_run_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?) "
            "ON CONFLICT(concept_mention_id, detector_name, detector_version) DO UPDATE SET "
            "assertion_status=excluded.assertion_status, detector_confidence=excluded.detector_confidence, "
            "cue_text=excluded.cue_text, cue_start=excluded.cue_start, cue_end=excluded.cue_end, "
            "sentence_sha256=excluded.sentence_sha256, entity_mention_id=excluded.entity_mention_id, "
            "superseded=0, nlp_run_id=excluded.nlp_run_id, created_at=excluded.created_at",
            (_assertion_id(mention["document_concept_mention_id"], tagger.name, tagger.version),
             chunk_row["document_chunk_id"], mention["document_concept_mention_id"],
             _entity_mention_id(conn, mention), status, tagger.name, tagger.version,
             result.confidence, result.cue_text, result.cue_start, result.cue_end,
             hashlib.sha256(sentence.encode("utf-8")).hexdigest(), nlp_run_id, now))
        written += 1
    return written


def _live_chunks(conn, source_system: str | None, limit: int | None) -> list:
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


def run(conn, *, detector: str | None = None, source_system: str | None = None,
        limit: int | None = None, dry_run: bool = False) -> dict:
    """Classify every span on every chunk that has spans. Bounded by `limit`;
    safe to repeat. Offline by default (the cue tagger needs nothing)."""
    tagger = get_tagger(detector)
    config = {"detector": detector or "cue", "detector_name": tagger.name,
              "detector_version": tagger.version, "source_system": source_system, "limit": limit}
    run_id = runs.start_run(conn, STAGE, config=config, model_key=tagger.name,
                            input_scope={"source_system": source_system, "limit": limit})
    chunks = _live_chunks(conn, source_system, limit)
    written = 0
    try:
        for chunk_row in chunks:
            written += tag_chunk(conn, tagger, chunk_row, run_id)
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
    return {"run_id": run_id, "detector": tagger.name, "detector_version": tagger.version,
            "chunks": len(chunks), "assertions": written, "dry_run": dry_run}

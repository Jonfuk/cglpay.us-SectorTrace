"""Span-level entity extraction — `document_chunks` -> `document_concept_mentions`.

034D. Where 034C wrote element-level ontology topic *counts*, this writes
span-level *mentions*: a labelled character range inside a chunk, carrying
the offsets 034E's assertion detector and 034F's relation extractor need.

Two extractors, one path:

* ``stub`` -- offline, deterministic, no download. Regex whole-word matching
  of the 034B ontology's SUBSTANCE / TREATMENT / ROLE / SERVICE / COMMISSIONER
  concepts, plus the maintained provider name variants
  (`keywords.SUPPLIER_NAME_VARIANTS`) as PROVIDER spans. It does not do
  LOCATION or PROGRAMME, or novel provider names -- only the real model does.
  `extraction_score` is 1.0 (exact dictionary hit), `concept_id` is filled
  in for the ontology-backed labels.
* ``gliner`` -- GLiNER zero-shot NER (CPU, no fine-tune), imported lazily,
  present only with the `nlp` extra. Emits the full entity label set;
  `concept_id` is always NULL (a GLiNER span is the model's, not the
  ontology's) and `extraction_score` is the model's own token->label score.

Label set, and only this: PROVIDER, COMMISSIONER, SERVICE, SUBSTANCE,
TREATMENT, ROLE, LOCATION, PROGRAMME. Abstract situations (workforce
pressure, funding pressure, …) are 034C's ontology layer and 034G's
classifiers -- never a span label.

This table NEVER carries `entity_id`. Resolving a PROVIDER / COMMISSIONER
span to a registered entity is `pipeline/nlp/resolve.py`, a separate
deterministic step. A model span is a candidate a person confirms.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from pipeline.keywords import SUPPLIER_NAME_VARIANTS
from pipeline.nlp import models, runs
from pipeline.nlp import ontology as ontology_mod

STAGE = "spans"

LABELS = ("PROVIDER", "COMMISSIONER", "SERVICE", "SUBSTANCE",
          "TREATMENT", "ROLE", "LOCATION", "PROGRAMME")

# ontology category -> the span label it contributes to in the stub.
_CATEGORY_LABEL = {
    "substance": "SUBSTANCE",
    "medication": "TREATMENT",
    "treatment": "TREATMENT",
    "role": "ROLE",
    "service": "SERVICE",
    "commissioner": "COMMISSIONER",
}

# Provider name variants too ambiguous to match bare in running text; mirrors
# m08/m28. The full multi-word variants for the same provider still match.
_UNSAFE_PROVIDER_VARIANTS = frozenset({"cgl", "via", "inclusion"})

STUB_NAME = "ontology-stub"
STUB_VERSION = "1"
GLINER_DEFAULT_MODEL = "urchade/gliner_small-v2.1"


class SpanExtractionUnavailable(RuntimeError):
    """The requested extractor needs a dependency that is not installed."""


@dataclass(frozen=True)
class Span:
    label: str
    text: str
    char_start: int      # into the text passed to the extractor (a chunk)
    char_end: int
    score: float | None
    concept_id: str | None = None


# --- the stub -----------------------------------------------------------

def _alias_regex(alias: str) -> re.Pattern:
    """Whole-word, case-insensitive, with an optional trailing -s on the last
    token so `workers`/`worker` both match (the 034B fold, at the surface)."""
    parts = [re.escape(tok) for tok in alias.split()]
    if parts:
        parts[-1] += "s?"
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)


class StubSpanExtractor:
    name = STUB_NAME
    version = STUB_VERSION

    def __init__(self, onto: ontology_mod.Ontology | None = None):
        onto = onto or ontology_mod.default()
        self._patterns: list[tuple[re.Pattern, str, str | None]] = []
        for concept in onto.concepts.values():
            labels = {_CATEGORY_LABEL[c] for c in concept.categories if c in _CATEGORY_LABEL}
            if not labels:
                continue
            label = sorted(labels)[0]  # stable if a concept spans two mapped categories
            for alias in concept.aliases:
                norm = ontology_mod._normalise(alias)
                if not norm or norm in ontology_mod._UNSAFE_VARIANTS:
                    continue
                self._patterns.append((_alias_regex(alias), label, concept.id))
        for provider_key, variants in SUPPLIER_NAME_VARIANTS.items():
            for variant in variants:
                if variant.strip().lower() in _UNSAFE_PROVIDER_VARIANTS:
                    continue
                self._patterns.append((_alias_regex(variant), "PROVIDER", None))

    def extract(self, text: str) -> list[Span]:
        text = text or ""
        out: list[Span] = []
        seen: set[tuple[int, int, str]] = set()
        for pattern, label, concept_id in self._patterns:
            for m in pattern.finditer(text):
                key = (m.start(), m.end(), label)
                if key in seen:
                    continue
                seen.add(key)
                out.append(Span(label, m.group(0), m.start(), m.end(), 1.0, concept_id))
        out.sort(key=lambda s: (s.char_start, s.char_end, s.label))
        return out

    def register(self, conn) -> None:  # symmetry with the embedders; nothing to pin
        return None


# --- GLiNER -----------------------------------------------------------

class GlinerSpanExtractor:
    def __init__(self, model_id: str = GLINER_DEFAULT_MODEL, threshold: float = 0.5):
        self.model_id = model_id
        self.name = "gliner"
        self.version = model_id
        self.threshold = threshold
        self._model = None
        self._revision: str | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from gliner import GLiNER  # noqa: PLC0415 - lazy: only with the `nlp` extra
        except ImportError as exc:  # pragma: no cover - the path without the extra
            raise SpanExtractionUnavailable(
                f"GLiNER model {self.model_id!r} needs the `nlp` extra "
                "(`uv sync --extra nlp`). Use --extractor stub for an offline run."
            ) from exc
        self._model = GLiNER.from_pretrained(self.model_id)
        try:
            from huggingface_hub import model_info  # noqa: PLC0415
            self._revision = model_info(self.model_id).sha
        except Exception:  # noqa: BLE001 - provenance nicety
            self._revision = None
        self.version = f"{self.model_id}@{self._revision}" if self._revision else self.model_id

    def extract(self, text: str) -> list[Span]:
        self._load()
        found = self._model.predict_entities(
            text or "", [label.lower() for label in LABELS], threshold=self.threshold)
        spans = [
            Span(item["label"].upper(), item["text"], int(item["start"]), int(item["end"]),
                 float(item.get("score", 0.0)), None)
            for item in found
            if item["label"].upper() in LABELS]
        spans.sort(key=lambda s: (s.char_start, s.char_end, s.label))
        return spans

    def register(self, conn) -> None:
        self._load()
        models.upsert_model(
            conn, model_key="spans:" + self.model_id.rsplit("/", 1)[-1].lower(),
            model_provider="gliner", model_id=self.model_id, revision_sha=self._revision,
            framework="gliner", dimension=None, distance_metric="none", normalised=False)


def get_extractor(name: str | None):
    if not name or name == "stub":
        return StubSpanExtractor()
    if name == "gliner":
        return GlinerSpanExtractor()
    return GlinerSpanExtractor(name)


# --- the stage --------------------------------------------------------

def _mention_id(chunk_id: str, extractor: str, version: str, start: int, end: int, label: str) -> str:
    seed = f"{chunk_id}|{extractor}|{version}|{start}|{end}|{label}"
    return "dcm-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _chunk_elements(conn, chunk_row) -> list[tuple[str, str]]:
    """(element_id, text) for the elements a chunk covers, in sequence order."""
    rows = conn.execute(
        "SELECT de.document_element_id AS eid, de.text AS text "
        "FROM document_elements de "
        "JOIN document_elements s ON s.document_element_id = %s "
        "JOIN document_elements e ON e.document_element_id = %s "
        "WHERE de.document_version_id = %s AND de.sequence BETWEEN s.sequence AND e.sequence "
        "ORDER BY de.sequence",
        (chunk_row["element_start_id"], chunk_row["element_end_id"],
         chunk_row["document_version_id"])).fetchall()
    return [(r["eid"], r["text"] or "") for r in rows]


def _locate(char_start: int, char_end: int,
            element_offsets: list[tuple[str, int, int]]) -> tuple[str | None, int | None, int | None]:
    """Map a chunk-relative span to (element_id, element_char_start,
    element_char_end). `element_offsets` is (element_id, offset_in_chunk,
    element_len) in order."""
    for element_id, offset, length in element_offsets:
        if offset <= char_start < offset + length + 1:  # +1 for the joining newline
            return element_id, max(0, char_start - offset), min(length, char_end - offset)
    return None, None, None


def extract_chunk(conn, extractor, chunk_row, nlp_run_id: str | None) -> int:
    """(Re)extract one chunk's spans. Idempotent per (chunk, extractor,
    version): its own rows are cleared then rewritten. Returns rows written."""
    elements = _chunk_elements(conn, chunk_row)
    offsets: list[tuple[str, int, int]] = []
    acc = 0
    for element_id, text in elements:
        offsets.append((element_id, acc, len(text)))
        acc += len(text) + 1  # the "\n" the chunker joined on

    conn.execute(
        "DELETE FROM document_concept_mentions WHERE document_chunk_id = %s "
        "AND extractor_name = %s AND extractor_version = %s",
        (chunk_row["document_chunk_id"], extractor.name, extractor.version))

    now = runs.utcnow()
    written = 0
    for span in extractor.extract(chunk_row["text"] or ""):
        element_id, el_start, el_end = _locate(span.char_start, span.char_end, offsets)
        conn.execute(
            "INSERT INTO document_concept_mentions (document_concept_mention_id, document_chunk_id, "
            "document_element_id, label, concept_id, span_text, char_start, char_end, "
            "element_char_start, element_char_end, extractor_name, extractor_version, "
            "extraction_score, superseded, nlp_run_id, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s) "
            "ON CONFLICT(document_chunk_id, extractor_name, extractor_version, char_start, char_end, label) "
            "DO UPDATE SET span_text=excluded.span_text, concept_id=excluded.concept_id, "
            "document_element_id=excluded.document_element_id, "
            "element_char_start=excluded.element_char_start, element_char_end=excluded.element_char_end, "
            "extraction_score=excluded.extraction_score, superseded=0, "
            "nlp_run_id=excluded.nlp_run_id, created_at=excluded.created_at",
            (_mention_id(chunk_row["document_chunk_id"], extractor.name, extractor.version,
                         span.char_start, span.char_end, span.label),
             chunk_row["document_chunk_id"], element_id, span.label, span.concept_id,
             span.text, span.char_start, span.char_end, el_start, el_end,
             extractor.name, extractor.version, span.score, nlp_run_id, now))
        written += 1
    return written


def _live_chunks(conn, source_system: str | None, limit: int | None) -> list:
    sql = (
        "SELECT dc.document_chunk_id, dc.document_version_id, dc.text, "
        "dc.element_start_id, dc.element_end_id "
        "FROM document_chunks dc "
        "JOIN document_versions v ON v.document_version_id = dc.document_version_id "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE dc.superseded = 0")
    params: list = []
    if source_system:
        sql += " AND e.source_system = %s"
        params.append(source_system)
    sql += " ORDER BY dc.created_at, dc.document_chunk_id"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def run(conn, *, extractor: str | None = None, source_system: str | None = None,
        limit: int | None = None, dry_run: bool = False) -> dict:
    """Extract entity spans from every live chunk (optionally scoped by source
    system) into `document_concept_mentions`. Bounded by `limit`; safe to
    repeat. Offline by default (`extractor='stub'`)."""
    ex = get_extractor(extractor)
    ex.register(conn)
    config = {"extractor": extractor or "stub", "extractor_name": ex.name,
              "extractor_version": ex.version, "source_system": source_system, "limit": limit}
    run_id = runs.start_run(conn, STAGE, config=config, model_key=ex.name,
                            model_revision=getattr(ex, "_revision", None),
                            input_scope={"source_system": source_system, "limit": limit})
    chunks = _live_chunks(conn, source_system, limit)
    written = 0
    try:
        for chunk_row in chunks:
            written += extract_chunk(conn, ex, chunk_row, run_id)
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
    return {"run_id": run_id, "extractor": ex.name, "extractor_version": ex.version,
            "chunks": len(chunks), "mentions": written, "dry_run": dry_run}

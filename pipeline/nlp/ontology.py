"""The SectorTrace ontology loader — `pipeline/nlp/ontology/*.yml` into a
validated, versioned, in-memory model.

Stdlib + PyYAML only. 034C's deterministic classifier depends on this and is
always-on, so nothing here may need the `nlp` extra.

Matching follows the m28 idiom (`m28_sar_reports.find_provider_mentions`): a
surface form is normalised (lowercased, punctuation to spaces, corporate
suffixes dropped, whitespace collapsed) and compared as a whole-token
sliding window. An alias therefore never matches inside a longer word, and a
two-word concept never matches on one of its words alone. Short or ambiguous
aliases that would still fire on nonsense are dropped via `_UNSAFE_VARIANTS`.

`version` is a SHA-256 over the canonical content of the concept, relation
and pattern definitions — independent of YAML formatting, comments and key
order — and is what a consuming stage records as `ontology_version` on its
`nlp_run`. Editing the ontology is expected; a bumped version recomputes
downstream annotations alongside the old, never in place.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent / "ontology"

# The five kinds of thing a claim can be *about*. `workforce` means the staff
# group at a provider or service, never a named individual.
_SUBJECTS = frozenset({"provider", "service", "commissioner", "area", "workforce"})
_LITERALS = frozenset({"count", "money", "date"})

# Aliases that normalise to something too short or too common to match safely
# in free text. Mirrors m08/m28's list; extend it, never widen a match past
# it silently.
_UNSAFE_VARIANTS = frozenset({
    "via", "cgl", "inclusion", "key", "nps", "nos", "oat", "ost", "hiv",
    "pcc", "ccg", "icb", "ics", "phe", "bbv", "cpd", "nmp", "ohid", "dhsc",
    "hep c", "afc", "phg",
})
# ^ acronyms live here because a bare three-letter token in a committee paper
# is very often something else. A concept still matches on its spelled-out
# aliases; the acronym is a convenience that is not worth a false positive.


class OntologyError(RuntimeError):
    """A malformed or internally inconsistent ontology. Raised at load time so
    a broken edit fails the offline suite, not a pipeline run."""


def _normalise(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fold(token: str) -> str:
    """A crude singular fold so `workers`/`worker`, `caseloads`/`caseload`,
    `deaths`/`death` match one alias without a stemmer. Deliberately shallow:
    only a trailing `-s` on a token of 4+ characters that does not end in
    `ss` (`access`, `premises` -> unchanged / harmless). English `-y` -> `-ies`
    is not covered, so `difficulties` still needs its own alias."""
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _fold_tokens(tokens: list[str]) -> tuple[str, ...]:
    return tuple(_fold(t) for t in tokens)


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    categories: tuple[str, ...]
    aliases: tuple[str, ...]
    related: tuple[str, ...]
    notes: str | None
    # (surface alias, its normalised token tuple) for every alias that survives
    # normalisation and the unsafe list. Built once at load.
    alias_tokens: tuple[tuple[str, tuple[str, ...]], ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class Relation:
    id: str
    label: str
    subject: str
    object: str          # 'none' | 'concept:<category>' | 'literal:<type>'
    pressure: bool
    notes: str | None

    @property
    def object_concept_category(self) -> str | None:
        return self.object.split(":", 1)[1] if self.object.startswith("concept:") else None

    @property
    def object_literal_type(self) -> str | None:
        return self.object.split(":", 1)[1] if self.object.startswith("literal:") else None


@dataclass(frozen=True)
class Pattern:
    id: str
    kind: str            # 'concept' | 'predicate'
    target: str          # a concept id or a relation id
    regex: str
    notes: str | None
    source: str          # the pattern file's stem


@dataclass(frozen=True)
class Match:
    concept_id: str
    alias: str
    start_token: int     # index into _normalise(text).split()
    end_token: int       # exclusive


@dataclass(frozen=True)
class Ontology:
    schema_version: str
    categories: frozenset[str]
    concepts: dict[str, Concept]
    relations: dict[str, Relation]
    patterns: dict[str, tuple[Pattern, ...]]
    version: str

    def concept(self, concept_id: str) -> Concept | None:
        return self.concepts.get(concept_id)

    def relation(self, relation_id: str) -> Relation | None:
        return self.relations.get(relation_id)

    def by_category(self, category: str) -> list[Concept]:
        return [c for c in self.concepts.values() if category in c.categories]

    def pressure_concepts(self) -> list[Concept]:
        return self.by_category("pressure")

    def match(self, text: str, *, max_span: int = 8) -> list[Match]:
        """Every ontology concept named in `text`, as whole-token spans over
        the normalised token stream. Overlaps are kept — a passage can be
        about two concepts at once — but a single (concept, span) is reported
        once. `max_span` caps the alias length considered."""
        raw = _normalise(text).split()
        if not raw:
            return []
        tokens = _fold_tokens(raw)
        found: list[Match] = []
        seen: set[tuple[str, int, int]] = set()
        for concept in self.concepts.values():
            for alias, alias_tokens in concept.alias_tokens:
                width = len(alias_tokens)
                if width == 0 or width > max_span or width > len(tokens):
                    continue
                for start in range(len(tokens) - width + 1):
                    if tokens[start:start + width] == alias_tokens:
                        key = (concept.id, start, start + width)
                        if key not in seen:
                            seen.add(key)
                            found.append(Match(concept.id, alias, start, start + width))
        found.sort(key=lambda m: (m.start_token, m.end_token, m.concept_id))
        return found

    def match_counts(self, text: str) -> dict[str, int]:
        """concept_id -> number of distinct spans in `text`. The shape 034C
        writes into `document_topics.match_count`."""
        counts: dict[str, int] = {}
        for m in self.match(text):
            counts[m.concept_id] = counts.get(m.concept_id, 0) + 1
        return counts


# --- loading & validation --------------------------------------------------

def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise OntologyError(f"{path.name}: not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise OntologyError(f"{path.name}: expected a mapping at the top level")
    return data


def _load_concepts(root: Path) -> tuple[str, frozenset[str], dict[str, Concept]]:
    raw = _read_yaml(root / "concepts.yml")
    schema_version = str(raw.get("schema_version") or "").strip()
    if not schema_version:
        raise OntologyError("concepts.yml: schema_version is required")
    categories = raw.get("categories") or []
    if not isinstance(categories, list) or not all(isinstance(c, str) for c in categories):
        raise OntologyError("concepts.yml: `categories` must be a list of strings")
    category_set = frozenset(categories)

    concepts: dict[str, Concept] = {}
    for entry in raw.get("concepts") or []:
        cid = str(entry.get("id") or "").strip()
        if not cid or not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", cid):
            raise OntologyError(f"concepts.yml: bad or missing concept id {entry.get('id')!r} "
                                "(expected `group.name`, lowercase)")
        if cid in concepts:
            raise OntologyError(f"concepts.yml: duplicate concept id {cid!r}")
        cats = tuple(entry.get("categories") or ())
        if not cats:
            raise OntologyError(f"concepts.yml: {cid} has no categories")
        unknown = [c for c in cats if c not in category_set]
        if unknown:
            raise OntologyError(f"concepts.yml: {cid} uses undeclared categories {unknown}")
        aliases = tuple(dict.fromkeys(str(a) for a in (entry.get("aliases") or ()) if str(a).strip()))
        if not aliases:
            raise OntologyError(f"concepts.yml: {cid} has no aliases")
        alias_tokens: list[tuple[str, tuple[str, ...]]] = []
        for alias in aliases:
            norm = _normalise(alias)
            if not norm or norm in _UNSAFE_VARIANTS:
                continue
            alias_tokens.append((alias, _fold_tokens(norm.split())))
        if not alias_tokens:
            raise OntologyError(
                f"concepts.yml: {cid} has no usable alias after normalisation "
                "(all empty or on the unsafe list)")
        concepts[cid] = Concept(
            id=cid, label=str(entry.get("label") or cid),
            categories=cats, aliases=aliases,
            related=tuple(str(r) for r in (entry.get("related") or ())),
            notes=(str(entry["notes"]).strip() if entry.get("notes") else None),
            alias_tokens=tuple(alias_tokens))

    for concept in concepts.values():
        for ref in concept.related:
            if ref not in concepts:
                raise OntologyError(
                    f"concepts.yml: {concept.id} relates to unknown concept {ref!r}")
    return schema_version, category_set, concepts


def _load_relations(root: Path, categories: frozenset[str]) -> dict[str, Relation]:
    raw = _read_yaml(root / "relations.yml")
    relations: dict[str, Relation] = {}
    for entry in raw.get("relations") or []:
        rid = str(entry.get("id") or "").strip()
        if not rid or not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", rid):
            raise OntologyError(f"relations.yml: bad or missing relation id {entry.get('id')!r}")
        if rid in relations:
            raise OntologyError(f"relations.yml: duplicate relation id {rid!r}")
        subject = str(entry.get("subject") or "").strip()
        if subject not in _SUBJECTS:
            raise OntologyError(
                f"relations.yml: {rid} subject {subject!r} not one of {sorted(_SUBJECTS)}")
        obj = str(entry.get("object") or "").strip()
        if obj != "none" and not obj.startswith(("concept:", "literal:")):
            raise OntologyError(
                f"relations.yml: {rid} object {obj!r} must be 'none', 'concept:<category>' "
                "or 'literal:<type>'")
        if obj.startswith("concept:") and obj.split(":", 1)[1] not in categories:
            raise OntologyError(f"relations.yml: {rid} object references unknown category "
                                f"{obj.split(':', 1)[1]!r}")
        if obj.startswith("literal:") and obj.split(":", 1)[1] not in _LITERALS:
            raise OntologyError(f"relations.yml: {rid} object literal type must be one of "
                                f"{sorted(_LITERALS)}")
        relations[rid] = Relation(
            id=rid, label=str(entry.get("label") or rid), subject=subject, object=obj,
            pressure=bool(entry.get("pressure", False)),
            notes=(str(entry["notes"]).strip() if entry.get("notes") else None))
    return relations


def _load_patterns(root: Path, concepts: dict[str, Concept],
                   relations: dict[str, Relation]) -> dict[str, tuple[Pattern, ...]]:
    out: dict[str, tuple[Pattern, ...]] = {}
    patterns_dir = root / "patterns"
    if not patterns_dir.is_dir():
        return out
    for path in sorted(patterns_dir.glob("*.yml")):
        raw = _read_yaml(path)
        stem = path.stem
        items: list[Pattern] = []
        seen: set[str] = set()
        for entry in raw.get("patterns") or []:
            pid = str(entry.get("id") or "").strip()
            if not pid:
                raise OntologyError(f"{path.name}: a pattern has no id")
            if pid in seen:
                raise OntologyError(f"{path.name}: duplicate pattern id {pid!r}")
            seen.add(pid)
            kind = str(entry.get("kind") or "").strip()
            if kind not in ("concept", "predicate"):
                raise OntologyError(f"{path.name}: {pid} kind must be 'concept' or 'predicate'")
            regex = entry.get("regex")
            if not isinstance(regex, str) or not regex:
                raise OntologyError(f"{path.name}: {pid} has no regex string")
            if kind == "concept":
                target = str(entry.get("concept") or "").strip()
                if target not in concepts:
                    raise OntologyError(f"{path.name}: {pid} names unknown concept {target!r}")
            else:
                target = str(entry.get("predicate") or "").strip()
                if target not in relations:
                    raise OntologyError(f"{path.name}: {pid} names unknown predicate {target!r}")
            items.append(Pattern(
                id=pid, kind=kind, target=target, regex=regex,
                notes=(str(entry["notes"]).strip() if entry.get("notes") else None),
                source=stem))
        out[stem] = tuple(items)
    return out


def _fingerprint(schema_version: str, concepts: dict[str, Concept],
                 relations: dict[str, Relation],
                 patterns: dict[str, tuple[Pattern, ...]]) -> str:
    payload = {
        "schema_version": schema_version,
        "concepts": sorted(
            [c.id, c.label, sorted(c.categories), list(c.aliases), sorted(c.related)]
            for c in concepts.values()),
        "relations": sorted(
            [r.id, r.label, r.subject, r.object, r.pressure] for r in relations.values()),
        "patterns": sorted(
            [p.source, p.id, p.kind, p.target, p.regex]
            for group in patterns.values() for p in group),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "onto-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load(root: Path | None = None) -> Ontology:
    """Read, validate and version the ontology under `root` (defaults to the
    bundled `pipeline/nlp/ontology/`). Raises `OntologyError` on any
    inconsistency."""
    root = Path(root) if root is not None else _ROOT
    schema_version, categories, concepts = _load_concepts(root)
    relations = _load_relations(root, categories)
    patterns = _load_patterns(root, concepts, relations)
    return Ontology(
        schema_version=schema_version, categories=categories, concepts=concepts,
        relations=relations, patterns=patterns,
        version=_fingerprint(schema_version, concepts, relations, patterns))


@lru_cache(maxsize=1)
def default() -> Ontology:
    """The bundled ontology, loaded once per process."""
    return load()


def version() -> str:
    """The bundled ontology's `ontology_version` string, for `nlp_runs`."""
    return default().version

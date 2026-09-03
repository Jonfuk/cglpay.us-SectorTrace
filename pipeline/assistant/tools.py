"""The closed, public-safe analyst tool catalogue (BETA-109).

Exactly eleven typed, in-process, side-effect-free tools sit between a natural
question and the warehouse's existing read-only query code:

  * ``search_document_passages``  — hybrid retrieval over parsed committee and
    partnership documents (`pipeline.nlp.semantic_search`);
  * ``inspect_claim_candidates``  — bounded aggregate counts of machine claim
    candidates by predicate, assertion status and lifecycle;
  * ``inspect_claim_gate``        — the 034G readiness report
    (`pipeline.nlp.gate`);
  * ``inspect_source_coverage``   — the evidence-by-authority coverage summary
    (`pipeline.web.health.coverage`), reduced to per-column covered/total
    counts plus a per-region authority count;
  * ``inspect_freshness``         — newest/oldest ``retrieved_at`` per table
    (`pipeline.web.health.freshness`).

Why a closed catalogue rather than SQL or HTTP access for the model: the
database already has read-only, caveated, provenance-rich views. The tools
reuse them and add only argument validation. There is deliberately no
argument that names a table, a URL, a file path, a SQL fragment or a write —
`validate_args` rejects those shapes outright, and every wrapper runs on a
read-only connection.

Each tool returns the same envelope::

    {"tool": ..., "args": <validated>, "caveat": ...,
     "result_ids": [<result-local identifiers a later answer may cite>],
     "data": <the tool's own payload>}

``result_ids`` is the whitelist BETA-111's citation check validates against.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Callable

TOOL_NAMES = (
    "search_document_passages",
    "inspect_claim_candidates",
    "inspect_claim_gate",
    "inspect_source_coverage",
    "inspect_freshness",
    "inspect_automated_signals",
    "inspect_emerging_themes",
    "compare_structured_metrics",
    "inspect_cross_source_links",
    "trace_signal_lineage",
    "inspect_analysis_health",
)

_MAX_QUERY_LEN = 400
_MAX_LIMIT = 20
_DEFAULT_LIMIT = 8

# A source_system / predicate / table token: lowercase words, digits, dot,
# hyphen, underscore. Anything with a slash, a scheme, a space, a quote or a
# semicolon never matches and is rejected — that is the point.
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Shapes an argument must never take. Checked on every string value regardless
# of which field it is, so a model cannot smuggle one in through `query`
# either (retrieval treats it as literal text anyway; this fails loudly).
_UNSAFE = (
    re.compile(r"[a-z]+://", re.I),                       # a URL scheme
    re.compile(r"\.\./|/etc/|[A-Za-z]:\\\\|~/"),          # a filesystem path
    re.compile(r"\b(drop|delete|insert|update|alter|create|attach|pragma|"
               r"truncate|grant|vacuum)\b", re.I),        # a write / DDL verb
    re.compile(r";\s*\w"),                                # stacked statements
    re.compile(r"--|/\*"),                                # a SQL comment
)


class ToolError(ValueError):
    """A bad tool name or bad arguments — surfaced to the caller, never a 500
    and never a tool execution."""


# --- argument schemas ---------------------------------------------------------
#
# Deliberately hand-rolled and tiny. A field is (kind, required, extra). No
# field anywhere is a table name, a URL, a path or a SQL fragment.

_SCHEMAS: dict[str, dict[str, tuple]] = {
    "search_document_passages": {
        "query": ("text", True, {"max": _MAX_QUERY_LEN}),
        "source_system": ("token", False, {}),
        "date_from": ("date", False, {}),
        "date_to": ("date", False, {}),
        "mode": ("enum", False, {"choices": ("keyword", "semantic", "hybrid")}),
        "limit": ("int", False, {"min": 1, "max": _MAX_LIMIT}),
    },
    "inspect_claim_candidates": {
        "source_system": ("token", False, {}),
        "predicate": ("token", False, {}),
        "assertion_status": ("enum", False, {
            "choices": ("AFFIRMED", "NEGATED", "HISTORICAL", "THIRD_PARTY",
                        "UNKNOWN")}),
        "status": ("enum", False, {
            "choices": ("new", "queued", "promoted", "rejected", "superseded")}),
        "limit": ("int", False, {"min": 1, "max": _MAX_LIMIT}),
    },
    "inspect_claim_gate": {},
    "inspect_source_coverage": {
        "tier": ("enum", False, {"choices": ("upper", "all")}),
    },
    "inspect_freshness": {
        "table": ("token", False, {}),
    },
    "inspect_automated_signals": {
        "release_id": ("token", False, {}), "domain_id": ("token", False, {}),
        "subject_id": ("token", False, {}), "limit": ("int", False, {"min": 1, "max": _MAX_LIMIT}),
    },
    "inspect_emerging_themes": {
        "domain_id": ("token", False, {}), "status": ("enum", False, {"choices": ("shadow", "promotion_ready", "promoted")}),
        "limit": ("int", False, {"min": 1, "max": _MAX_LIMIT}),
    },
    "compare_structured_metrics": {
        "subject_id": ("token", True, {}), "metric": ("token", False, {}),
        "limit": ("int", False, {"min": 1, "max": _MAX_LIMIT}),
    },
    "inspect_cross_source_links": {
        "release_id": ("token", False, {}), "subject_id": ("token", False, {}),
        "relationship_type": ("enum", False, {"choices": ("same_event", "entity_overlap", "temporal_context", "metric_context", "value_conflict", "narrative_structured_alignment")}),
        "limit": ("int", False, {"min": 1, "max": _MAX_LIMIT}),
    },
    "trace_signal_lineage": {"signal_id": ("token", True, {})},
    "inspect_analysis_health": {
        "source_table": ("token", False, {}), "limit": ("int", False, {"min": 1, "max": _MAX_LIMIT}),
    },
}


def tool_accepts(name: str, field: str) -> bool:
    """Whether tool `name` has an argument called `field` — used by the
    orchestrator to decide which turn-level filters it may fold in."""
    return field in _SCHEMAS.get(name, {})


def tool_schemas() -> dict:
    """The catalogue as plain JSON-serialisable metadata, for the router
    prompt and for `/api/admin/assistant` introspection."""
    out: dict[str, dict] = {}
    for name, fields in _SCHEMAS.items():
        out[name] = {
            "description": _DESCRIPTIONS[name],
            "arguments": {
                field: {"kind": kind, "required": required, **extra}
                for field, (kind, required, extra) in fields.items()
            },
        }
    return out


# These strings go into the router prompt verbatim on every call, so they are
# the router's only guide to which tool fits. BETA-115 rewrote them after the
# first live eval: several route prompts were missed because the description
# did not advertise a capability the wrapper actually has (per-region authority
# counts in `inspect_source_coverage`; "decided examples per category" in
# `inspect_claim_gate`) or led with a caveat ("No per-authority detail") that
# read as "cannot answer 'how many authorities …'". Keep each one a plain
# statement of what the tool answers, with example phrasings.
_DESCRIPTIONS = {
    "search_document_passages":
        "Retrieve paragraph-level passages of parsed committee papers and drug "
        "partnership documents, matched by wording, embedding similarity, or "
        "both. Use for any question answered by quoting document text: what "
        "papers say about a topic, where something is discussed, the reported "
        "impact or effect of something, 'find/show text on X'. Optional "
        "source_system / date filters.",
    "inspect_claim_candidates":
        "Counts of machine-extracted claim candidates, grouped by predicate, "
        "assertion status (AFFIRMED / NEGATED / HISTORICAL / THIRD_PARTY / "
        "UNKNOWN) and lifecycle stage, optionally filtered by source_system. "
        "Use for 'how many / count / break down' questions about candidate "
        "claims, including by topic or predicate. Counts only, no sentence "
        "text.",
    "inspect_claim_gate":
        "The 034G / SetFit training-readiness report: per category, how many "
        "human-decided positive and negative review examples exist, whether "
        "there is enough spread and inter-reviewer agreement, whether a "
        "held-out set can be carved, and what is still missing before claim "
        "classifiers can be trained.",
    "inspect_source_coverage":
        "Evidence coverage across the responsible (public-health) authorities: "
        "for each evidence kind (contracts, FOI, committee papers, CQC, public "
        "health grant, …) how many authorities have at least one row out of the "
        "total, plus a count of authorities per region. Use for 'how many "
        "authorities have / are missing X evidence' and 'which region has the "
        "fewest / most authorities'. Aggregate counts, not a named-authority "
        "list.",
    "inspect_freshness":
        "The newest and oldest retrieved_at, and the row count, per evidence "
        "table — the honest 'how stale is this' signal. Optionally for one "
        "named table (e.g. contracts, cqc_locations, committee_papers).",
    "inspect_automated_signals": "Inspect validated admin-only automated signals by release, domain or canonical subject. Results include direction, assertion status, provenance references and the immutable release identity.",
    "inspect_emerging_themes": "Inspect shadow and promotion-ready emerging themes, including recurrence counts and grounded representative passages.",
    "compare_structured_metrics": "Compare deterministic structured metric calculations for one canonical subject. Values, periods, units and anomaly scores come from validated source rows; the assistant cannot calculate or alter them.",
    "inspect_cross_source_links": "Inspect deterministic cross-source links and conflicts. Source evidence remains independently addressable and absence is never a contradiction.",
    "trace_signal_lineage": "Trace one automated signal to its release, source evidence, model calls and verifier results.",
    "inspect_analysis_health": "Inspect source freshness, schema/parse health, topic outliers, model agreement, verifier pass rates, cost and adaptation proposals.",
}


def _check_string(value: str, field: str) -> None:
    for pattern in _UNSAFE:
        if pattern.search(value):
            raise ToolError(
                f"argument {field!r} has a disallowed shape (URL, path, SQL or "
                f"write verb)")


def _coerce(name: str, field: str, kind: str, value: Any, extra: dict) -> Any:
    if kind in ("text", "token", "date", "enum"):
        if not isinstance(value, str):
            raise ToolError(f"{name}.{field} must be a string")
        value = value.strip()
        _check_string(value, field)
        if not value:
            raise ToolError(f"{name}.{field} is empty")
        if kind == "text" and len(value) > extra["max"]:
            raise ToolError(f"{name}.{field} is longer than {extra['max']} chars")
        if kind == "token" and not _TOKEN_RE.match(value):
            raise ToolError(f"{name}.{field} is not a bare identifier")
        if kind == "date":
            if not _DATE_RE.match(value):
                raise ToolError(f"{name}.{field} must be an ISO date (YYYY-MM-DD)")
            try:
                _dt.date.fromisoformat(value)
            except ValueError:
                raise ToolError(f"{name}.{field} is not a real calendar date") from None
        if kind == "enum" and value not in extra["choices"]:
            raise ToolError(
                f"{name}.{field} must be one of {list(extra['choices'])}")
        return value
    if kind == "int":
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ToolError(f"{name}.{field} must be an integer") from None
        return max(extra["min"], min(n, extra["max"]))
    raise ToolError(f"unknown field kind {kind!r}")  # pragma: no cover


def validate_args(name: str, args: dict | None) -> dict:
    """Return the cleaned, bounded argument dict for `name`, or raise
    `ToolError`. Unknown keys, wrong types and unsafe shapes are all rejected;
    nothing is executed here."""
    if name not in _SCHEMAS:
        raise ToolError(f"unknown tool {name!r}; the catalogue is "
                        f"{list(TOOL_NAMES)}")
    args = dict(args or {})
    schema = _SCHEMAS[name]
    unknown = sorted(set(args) - set(schema))
    if unknown:
        raise ToolError(f"{name} got unknown argument(s) {unknown}")

    cleaned: dict[str, Any] = {}
    for field, (kind, required, extra) in schema.items():
        if field not in args or args[field] in (None, ""):
            if required:
                raise ToolError(f"{name} requires {field!r}")
            continue
        cleaned[field] = _coerce(name, field, kind, args[field], extra)
    return cleaned


# --- the five wrappers ------------------------------------------------------
#
# Each takes (conn, settings, **validated args) and returns the tool's own
# payload plus the `result_ids` a downstream answer may cite. Read-only.

def _t_search(conn, settings, *, query, source_system=None, date_from=None,
              date_to=None, mode="hybrid", limit=_DEFAULT_LIMIT) -> tuple[dict, list]:
    from pipeline.nlp import semantic_search

    result = semantic_search.search(
        conn, query, mode=mode, limit=limit, source_system=source_system,
        date_from=date_from, date_to=date_to,
        model=settings.nlp_embedding_model)
    ids = [r["document_chunk_id"] for r in result.get("results", [])]
    return result, ids


def _t_claim_candidates(conn, settings, *, source_system=None, predicate=None,
                        assertion_status=None, status=None,
                        limit=_MAX_LIMIT) -> tuple[dict, list]:
    where = ["c.superseded = 0"]
    params: list = []
    if predicate:
        where.append("c.predicate = %s")
        params.append(predicate)
    if assertion_status:
        where.append("c.assertion_status = %s")
        params.append(assertion_status)
    if status:
        where.append("c.status = %s")
        params.append(status)
    join = ""
    if source_system:
        join = (" JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id "
                " JOIN document_versions v ON v.document_version_id = dc.document_version_id "
                " JOIN document_records d ON d.document_id = v.document_id "
                " JOIN evidence_records e ON e.evidence_id = d.evidence_id")
        where.append("e.source_system = %s")
        params.append(source_system)
    rows = conn.execute(
        "SELECT c.predicate AS predicate, c.assertion_status AS assertion_status, "
        "c.status AS status, COUNT(*) AS n "
        f"FROM document_claim_candidates c{join} "
        f"WHERE {' AND '.join(where)} "
        "GROUP BY c.predicate, c.assertion_status, c.status "
        "ORDER BY n DESC, c.predicate LIMIT %s", (*params, limit)).fetchall()
    groups = [dict(r) for r in rows]
    total = sum(g["n"] for g in groups)
    predicates = sorted({g["predicate"] for g in groups if g["predicate"]})
    data = {
        "groups": groups,
        "total_in_groups": total,
        "predicates": predicates,
        "filters": {"source_system": source_system, "predicate": predicate,
                    "assertion_status": assertion_status, "status": status},
        "caveat": "Counts of machine-extracted candidates, not findings. A "
                  "candidate is a sentence a model thought asserted something; "
                  "only human review turns one into evidence.",
    }
    return data, predicates


def _t_claim_gate(conn, settings) -> tuple[dict, list]:
    from pipeline.nlp import gate

    report = gate.check(conn)
    return report, sorted(report.get("categories", {}))


def _t_source_coverage(conn, settings, *, tier="upper") -> tuple[dict, list]:
    from pipeline.web import health

    full = health.coverage(conn, tier=tier)
    # Reduce the per-authority matrix to the per-column summary — bounded, and
    # still the answer to "how much X evidence is there". Per-region totals
    # are a small, non-sensitive aggregate on top.
    by_region: dict[str, int] = {}
    for auth in full.get("authorities", []):
        by_region[auth["region"] or "unknown"] = (
            by_region.get(auth["region"] or "unknown", 0) + 1)
    data = {
        "tier": full["tier"],
        "authority_count": full["authority_count"],
        "authorities_by_region": by_region,
        "columns": full["columns"],
        "caveat": "Coverage is 'how many responsible authorities have at least "
                  "one row of this evidence kind', against the tier that is "
                  "actually responsible for public health — never against all "
                  "347 authorities.",
    }
    return data, [c["label"] for c in full["columns"]]


def _t_freshness(conn, settings, *, table=None) -> tuple[dict, list]:
    from pipeline.web import health

    rows = health.freshness(conn)
    names = [r["table"] for r in rows]
    if table is not None:
        if table not in names:
            raise ToolError(
                f"no freshness row for {table!r}; tables are {names}")
        rows = [r for r in rows if r["table"] == table]
    data = {
        "tables": rows,
        "caveat": "Freshness is the newest retrieved_at of the rows themselves, "
                  "not when a module last ran. A module can run and fetch "
                  "nothing new.",
    }
    return data, [r["table"] for r in rows]


def _t_automated_signals(conn, settings, *, release_id=None, domain_id=None,
                         subject_id=None, limit=_MAX_LIMIT) -> tuple[dict, list]:
    from pipeline.analysis.store import list_signals
    rows = list_signals(conn, release_id=release_id, domain_id=domain_id,
                        subject_id=subject_id, limit=limit)
    return {"signals": rows, "caveat": "Automated signals are not verified claims."}, [r["signal_id"] for r in rows]


def _t_emerging_themes(conn, settings, *, domain_id=None, status=None,
                       limit=_MAX_LIMIT) -> tuple[dict, list]:
    where, params = [], []
    if domain_id:
        where.append("domain_id = %s")
        params.append(domain_id)
    if status:
        where.append("status = %s")
        params.append(status)
    params.append(limit)
    sql = "SELECT * FROM emerging_themes" + ((" WHERE " + " AND ".join(where)) if where else "") + " ORDER BY created_at DESC LIMIT %s"
    rows = [dict(row) for row in conn.execute(sql, params)]
    return {"themes": rows, "caveat": "Emerging themes remain in shadow until admin promotion."}, [r["theme_id"] for r in rows]


def _t_structured(conn, settings, *, subject_id, metric=None, limit=_MAX_LIMIT) -> tuple[dict, list]:
    where = ["a.subject_id = %s"]
    params = [subject_id]
    if metric:
        where.append("s.metric = %s")
        params.append(metric)
    params.append(limit)
    rows = [dict(row) for row in conn.execute("SELECT s.*, a.domain_id, a.subject_id, a.direction FROM structured_signals s JOIN automated_signals a ON a.signal_id = s.signal_id WHERE " + " AND ".join(where) + " ORDER BY s.created_at DESC LIMIT %s", params)]
    return {"structured": rows, "caveat": "Arithmetic and direction are deterministic; no model-generated numbers are included."}, [r["structured_signal_id"] for r in rows]


def _t_links(conn, settings, *, release_id=None, subject_id=None,
             relationship_type=None, limit=_MAX_LIMIT) -> tuple[dict, list]:
    from pipeline.analysis.linking import list_links
    rows = list_links(conn, release_id=release_id, subject_id=subject_id,
                      relationship_type=relationship_type, limit=limit)
    return {"links": rows, "caveat": "Links are temporal/metric context, not causal findings."}, [r["link_id"] for r in rows]


def _t_lineage(conn, settings, *, signal_id) -> tuple[dict, list]:
    signal = conn.execute("SELECT * FROM automated_signals WHERE signal_id = %s", (signal_id,)).fetchone()
    if signal is None:
        raise ToolError(f"no automated signal {signal_id!r}")
    calls = [dict(row) for row in conn.execute("SELECT * FROM analysis_model_calls WHERE release_id = %s AND domain_id = %s", (signal["release_id"], signal["domain_id"]))]
    verifiers = [dict(row) for row in conn.execute("SELECT * FROM analysis_verifier_results WHERE signal_id = %s", (signal_id,))]
    return {"signal": dict(signal), "model_calls": calls, "verifiers": verifiers}, [signal_id]


def _t_health(conn, settings, *, source_table=None, limit=_MAX_LIMIT) -> tuple[dict, list]:
    where, params = [], []
    if source_table:
        where.append("source_table = %s")
        params.append(source_table)
    params.append(limit)
    sql = "SELECT * FROM analysis_health_snapshots" + ((" WHERE " + " AND ".join(where)) if where else "") + " ORDER BY collected_at DESC LIMIT %s"
    rows = [dict(row) for row in conn.execute(sql, params)]
    proposals = [dict(row) for row in conn.execute("SELECT * FROM adaptation_proposals WHERE status = 'pending' ORDER BY created_at DESC LIMIT %s", (limit,))]
    return {"health": rows, "proposals": proposals}, [r["health_snapshot_id"] for r in rows]


_WRAPPERS: dict[str, Callable] = {
    "search_document_passages": _t_search,
    "inspect_claim_candidates": _t_claim_candidates,
    "inspect_claim_gate": _t_claim_gate,
    "inspect_source_coverage": _t_source_coverage,
    "inspect_freshness": _t_freshness,
    "inspect_automated_signals": _t_automated_signals,
    "inspect_emerging_themes": _t_emerging_themes,
    "compare_structured_metrics": _t_structured,
    "inspect_cross_source_links": _t_links,
    "trace_signal_lineage": _t_lineage,
    "inspect_analysis_health": _t_health,
}

_CAVEAT_BY_TOOL = {name: fn for name, fn in _WRAPPERS.items()}


def run_tool(name: str, args: dict | None, conn, settings) -> dict:
    """Validate `args`, run one tool read-only, return the standard envelope.

    Raises `ToolError` for a bad name or bad arguments — the caller turns that
    into a clarification, never a crash. The tool itself is side-effect free;
    nothing is written, promoted or attributed.
    """
    cleaned = validate_args(name, args)
    data, result_ids = _WRAPPERS[name](conn, settings, **cleaned)
    caveat = data.get("caveat") if isinstance(data, dict) else None
    return {
        "tool": name,
        "args": cleaned,
        "caveat": caveat,
        "result_ids": list(result_ids),
        "data": data,
    }

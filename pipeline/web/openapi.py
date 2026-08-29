"""An OpenAPI 3.1 description of the public portal API, served at
`/api/openapi.json` (BETA-048).

The point is a *testable inventory* of what is intentionally public. The
route table below is a compact hand-maintained structure, one entry per
public route, and `tests/test_web_openapi.py` binds it to the frozen surface
in `tests/test_portal_isolation.py` in both directions — a new `/api/v1/`
route that is not described here fails, and a described route that the server
does not serve fails too.

No framework and no generated-client toolchain: this is a dict and a
`json.dumps`, the same "stdlib web server, no build step" rule the rest of
`pipeline/web/` follows.

Every response body across the API carries provenance (a source URL and a
`retrieved_at`) and, wherever it reports a figure, the caveat that governs
it. That is stated once here rather than repeated per route.
"""
from __future__ import annotations

# --- reusable parameter fragments -----------------------------------------

_LIMIT = {"name": "limit", "in": "query", "required": False,
          "schema": {"type": "integer"},
          "description": "Maximum rows to return; each route documents its own cap."}
_OFFSET = {"name": "offset", "in": "query", "required": False,
           "schema": {"type": "integer", "minimum": 0},
           "description": "Row offset for stable pagination."}
_SINCE = {"name": "since_retrieved_at", "in": "query", "required": False,
          "schema": {"type": "string", "format": "date-time"},
          "description": "Only rows collected on or after this ISO timestamp."}


def _p(name, *, where="query", required=False, typ="string", desc=""):
    return {"name": name, "in": where, "required": required,
            "schema": {"type": typ}, "description": desc}


# --- the route table -----------------------------------------------------
#
# `surface` is the exact string this route appears as in
# tests/test_portal_isolation.py — a name in PUBLIC_API_ROUTES, a regex in
# PUBLIC_API_PATTERNS, or PUBLIC_API_EXTRA ("export"). The parity test keys
# off it, so it must stay verbatim.

ROUTES: dict[str, dict] = {
    "/api/v1/summary": {
        "surface": "summary",
        "summary": "Headline counts across the corpus, each with its caveat.",
        "parameters": [],
    },
    "/api/v1/meta": {
        "surface": "meta",
        "summary": "Release identity: revision, build time, schema and capability flags.",
        "parameters": [],
    },
    "/api/v1/providers": {
        "surface": "providers",
        "summary": "One entry per tracked provider.",
        "parameters": [],
    },
    "/api/v1/providers/{provider_key}/timeline": {
        "surface": r"providers/([a-z0-9_]+)/timeline",
        "summary": "Dated evidence events for one provider.",
        "parameters": [_p("provider_key", where="path", required=True,
                           desc="A provider_key from /api/v1/providers.")],
    },
    "/api/v1/providers/{provider_key}/lineage": {
        "surface": r"providers/([a-z0-9_]+)/lineage",
        "summary": "Verified administrative lineage — renamed/merged/dissolved "
                   "edges and the forward chain to the surviving entity; not a "
                   "statement about continuity of service or workforce.",
        "parameters": [_p("provider_key", where="path", required=True,
                           desc="A provider_key from /api/v1/providers.")],
    },
    "/api/v1/provider_compare": {
        "surface": "provider_compare",
        "summary": "Two to four providers across four separate pay-evidence layers; "
                   "no ranking, score, difference or ratio.",
        "parameters": [
            {"name": "provider_key", "in": "query", "required": True,
             "schema": {"type": "array", "items": {"type": "string"},
                        "minItems": 2, "maxItems": 4},
             "description": "Repeatable. Between 2 and 4 distinct providers."}],
    },
    "/api/v1/authorities": {
        "surface": "authorities",
        "summary": "Every English local authority with public-health responsibility.",
        "parameters": [],
    },
    "/api/v1/authorities/{ons_code}": {
        "surface": r"authorities/([A-Z][0-9]{8})",
        "summary": "One authority's own evidence and comparator datasets.",
        "parameters": [_p("ons_code", where="path", required=True,
                           desc="A letter followed by eight digits, e.g. E08000025.")],
    },
    "/api/v1/compare": {
        "surface": "compare",
        "summary": "Existing series for two or more authorities or providers on shared axes.",
        "parameters": [
            {"name": "ons_code", "in": "query", "required": False,
             "schema": {"type": "array", "items": {"type": "string"}},
             "description": "Repeatable authority code."},
            {"name": "provider_key", "in": "query", "required": False,
             "schema": {"type": "array", "items": {"type": "string"}},
             "description": "Repeatable provider key. At least one of ons_code/provider_key."}],
    },
    "/api/v1/relationships": {
        "surface": "relationships",
        "summary": "One authority or provider's one-hop commissioning neighbourhood.",
        "parameters": [_p("ons_code", desc="Exactly one of ons_code or provider_key."),
                       _p("provider_key")],
    },
    "/api/v1/relationships/{relationship_id}": {
        "surface": r"relationships/(relationship:[0-9a-f]{64})",
        "summary": "One AWARDED_TO edge and the dated contract notices behind the pair.",
        "parameters": [_p("relationship_id", where="path", required=True,
                           desc="A relationship_id from an /api/v1/relationships edges entry.")],
    },
    "/api/v1/contracts": {
        "surface": "contracts",
        "summary": "Procurement notices, filterable and paged.",
        "parameters": [
            _p("q", desc="Case-insensitive substring over buyer and supplier names."),
            _p("provider_key"), _p("buyer_ons_code"),
            _p("year_from"), _p("year_to"), _SINCE, _LIMIT, _OFFSET],
    },
    "/api/v1/contracts/process/{ocid}": {
        "surface": r"contracts/process/([A-Za-z0-9_-]{1,100})",
        "summary": "Notices sharing one OCID, grouped into published OCDS "
                   "lifecycle stages; no stage or performance is inferred.",
        "parameters": [_p("ocid", where="path", required=True,
                           desc="An OCDS release id from a contract notice.")],
    },
    "/api/v1/document_search": {
        "surface": "document_search",
        "summary": "Ranked full-text search over parsed committee papers and CDP documents.",
        "parameters": [
            _p("q", required=True, desc="Search term(s); quotes/OR/-term honoured."),
            _p("source_system", desc="One of the facets.source_system values."),
            _p("document_type"), _p("year_from"), _p("year_to"), _SINCE,
            _LIMIT, _OFFSET],
    },
    "/api/v1/documents/{document_id}": {
        "surface": r"documents/([A-Za-z0-9_-]{1,80})",
        "summary": "A bounded passage around one matched element of a document.",
        "parameters": [
            _p("document_id", where="path", required=True,
               desc="A document_id from a search result."),
            _p("element_id", desc="A document_element_id to centre the window on."),
            _p("context", typ="integer", desc="Elements either side of the anchor; max 3.")],
    },
    "/api/v1/catalogue": {
        "surface": "catalogue",
        "summary": "Every dataset the portal holds, with source, licence, cadence and one caveat.",
        "parameters": [],
    },
    "/api/v1/catalogue/{dataset_id}": {
        "surface": r"catalogue/([a-z0-9-]{1,64})",
        "summary": "One catalogue entry with the full licence statement.",
        "parameters": [_p("dataset_id", where="path", required=True,
                           desc="A dataset_id from /api/v1/catalogue.")],
    },
    "/api/v1/publication_calendar": {
        "surface": "publication_calendar",
        "summary": "Each source's stated vs observed release cadence, last "
                   "retrieval held here, next-expected date and "
                   "overdue/unknown status. The stated cadence is the only "
                   "asserted figure; the observed interval is a labelled "
                   "estimate and the two are never merged.",
        "parameters": [
            _p("today", desc="ISO date to evaluate against; defaults to the "
                             "server's current date. For reproducible views."),
        ],
    },
    "/api/v1/changes": {
        "surface": "changes",
        "summary": "Derived chronology of what the warehouse recorded changing "
                   "— release, refreshed, reparsed, superseded, verified. "
                   "Collection / parser / human-review changes are distinct "
                   "kinds and never summed.",
        "parameters": [
            _p("kind", desc="release, refreshed, reparsed, superseded or verified."),
            _p("source"), _p("evidence_type"), _SINCE, _LIMIT,
        ],
    },
    "/api/v1/pay": {
        "surface": "pay",
        "summary": "The campaign's central pay evidence, every figure caveated.",
        "parameters": [
            _p("provider_key"), _p("year_from"), _p("year_to"),
            _p("role", desc="Case-insensitive substring on each source's role "
                            "text. Narrows rows; combines nothing."),
            _p("source", desc="One source group: indicative_wage, "
                              "advertised_roles, published_statutory, "
                              "workforce_census, external_comparators."),
            _p("pay_unit", desc="hourly, annual or other."),
        ],
    },
    "/api/v1/council_spend": {
        "surface": "council_spend",
        "summary": "Published council payment lines.",
        "parameters": [_p("authority_ons_code"), _p("provider_key"), _LIMIT],
    },
    "/api/v1/geography": {
        "surface": "geography",
        "summary": "Evidence coverage per authority for one metric.",
        "parameters": [_p("metric", desc="Default grant_total."), _p("year")],
    },
    "/api/v1/boundaries": {
        "surface": "boundaries",
        "summary": "Authority boundary geometry (large payload; day-cached).",
        "parameters": [],
    },
    "/api/v1/fingertips": {
        "surface": "fingertips",
        "summary": "OHID Fingertips local-authority indicators, each with its interval.",
        "parameters": [_p("indicator_id"), _p("topic"), _p("ons_code"), _p("substance")],
    },
    "/api/v1/treatment_metrics": {
        "surface": "treatment_metrics",
        "summary": "Catalogue of treatment metrics — definition, unit, whether a "
                   "95% CI is published, exact periods, coverage and provenance.",
        "parameters": [],
    },
    "/api/v1/ndtms": {
        "surface": "ndtms",
        "summary": "NDTMS published estimates with their confidence intervals.",
        "parameters": [_p("ons_code"), _p("table_ref")],
    },
    "/api/v1/pfd": {
        "surface": "pfd",
        "summary": "Prevention of Future Deaths reports and SAR documents.",
        "parameters": [],
    },
    "/api/v1/safety": {
        "surface": "safety",
        "summary": "HSE enforcement notices served on a tracked provider "
                   "(exact name match; individuals excluded; result verbatim).",
        "parameters": [],
    },
    "/api/v1/safety_legal": {
        "surface": "safety_legal",
        "summary": "One filterable chronology over PFD, SAR, HSE, tribunal and "
                   "CQC evidence. Each event carries exactly one relationship "
                   "label; counts by source and relationship, never summed.",
        "parameters": [
            _p("source", desc="pfd, sar, hse, tribunal or cqc."),
            _p("relationship", desc="addressed_to, named_in, matched_to or "
                                     "regulated_by."),
            _p("provider_key"), _p("year_from"), _p("year_to"),
        ],
    },
    "/api/v1/cqc_locations": {
        "surface": "cqc_locations",
        "summary": "Tracked providers' CQC-registered locations, filtered and "
                   "paged; not a service map, a count is not coverage, no "
                   "personal data.",
        "parameters": [
            _p("provider_key"), _p("authority_ons_code"),
            _p("registration_status", desc="One of the facets.registration_status values."),
            _p("regulated_activity", desc="Contains match on the comma-joined activities."),
            _p("service_type", desc="Exact gacServiceType name; one of the facets."),
            _p("rating", desc="Overall rating, API or bulk-export fallback."),
            _LIMIT, _OFFSET],
    },
    "/api/v1/claims": {
        "surface": "claims",
        "summary": "Campaign claims with the evidence rows behind each.",
        "parameters": [],
    },
    "/api/v1/freshness": {
        "surface": "freshness",
        "summary": "Newest retrieved_at per source table.",
        "parameters": [],
    },
    "/api/v1/layers": {
        "surface": "layers",
        "summary": "The geography map's overlay layers, each with its own caveats.",
        "parameters": [],
    },
    "/api/v1/atlas_layers": {
        "surface": "atlas_layers",
        "summary": "Closed registry of the evidence atlas's layers — one shown "
                   "at a time, no overlay, no composite score.",
        "parameters": [],
    },
    "/api/v1/export": {
        "surface": "export",
        "summary": "Any listed endpoint's rows as CSV or JSON, with provenance in the file.",
        "parameters": [
            _p("endpoint", required=True, desc="One of the exportable endpoint names."),
            _p("format", desc="csv (default) or json."),
        ],
    },
}


def document(*, server_url: str = "/") -> dict:
    """The OpenAPI 3.1 document as a plain dict."""
    error_schema = {
        "type": "object",
        "properties": {"error": {"type": "string"}},
        "required": ["error"],
        "description": "Every 4xx failure is this shape, with a message for a person.",
    }
    common_responses = {
        "200": {"description": "Success. The body carries provenance (source URL, "
                               "retrieved_at) and, for any figure, its caveat."},
        "400": {"description": "A bad or missing parameter.",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
        "404": {"description": "No such route or resource.",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
    }

    paths: dict[str, dict] = {}
    for path, spec in ROUTES.items():
        paths[path] = {
            "get": {
                "summary": spec["summary"],
                "parameters": [
                    {k: v for k, v in param.items() if k != "surface"}
                    for param in spec["parameters"]
                ],
                "responses": common_responses,
            }
        }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "SectorTrace public evidence API",
            "version": "1",
            "description": (
                "The read-only, unauthenticated API behind the public evidence "
                "portal. GET only; there is no write route under /api/v1/. Same-"
                "origin (no CORS). Responses are cached for five minutes. "
                "Personal data is unreachable — every query declares the tables "
                "it reads and is refused if one holds personal data. Nothing is "
                "inferred: an unparsable value is null with a logged reason."),
            "license": {
                "name": "Open Government Licence v3.0 (most sources; see /api/v1/catalogue)",
                "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
            },
        },
        "servers": [{"url": server_url}],
        "paths": paths,
        "components": {"schemas": {"Error": error_schema}},
    }

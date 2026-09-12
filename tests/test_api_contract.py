"""Compatibility classification for the public OpenAPI surface.

The route inventory in ``pipeline.web.openapi`` is the source of the current
contract. This smaller approved baseline is intentionally kept here as a
review point: adding a route is additive, marking one deprecated is visible,
and removing a route or making an input newly required is breaking. A breaking
change must update this baseline in the same reviewed change, rather than
silently changing what the Nuxt clients can rely on.
"""
from __future__ import annotations

from copy import deepcopy

from pipeline.web import openapi

APPROVED_PATHS = frozenset({
    "/api/v1/atlas_layers",
    "/api/v1/authorities",
    "/api/v1/authorities/{ons_code}",
    "/api/v1/boundaries",
    "/api/v1/catalogue",
    "/api/v1/catalogue/{dataset_id}",
    "/api/v1/changes",
    "/api/v1/claims",
    "/api/v1/compare",
    "/api/v1/contract_diary",
    "/api/v1/contracts",
    "/api/v1/contracts/process/{ocid}",
    "/api/v1/cooccurrence",
    "/api/v1/council_spend",
    "/api/v1/coverage_timeline",
    "/api/v1/cqc_locations",
    "/api/v1/discrepancies",
    "/api/v1/document_search",
    "/api/v1/document_tables",
    "/api/v1/documents/{document_id}",
    "/api/v1/export",
    "/api/v1/feed/changes.atom",
    "/api/v1/fingertips",
    "/api/v1/freshness",
    "/api/v1/geography",
    "/api/v1/layers",
    "/api/v1/meta",
    "/api/v1/ndtms",
    "/api/v1/pay",
    "/api/v1/pfd",
    "/api/v1/provider_compare",
    "/api/v1/providers",
    "/api/v1/providers/{provider_key}/lineage",
    "/api/v1/providers/{provider_key}/timeline",
    "/api/v1/publication_calendar",
    "/api/v1/record_diff",
    "/api/v1/relationship_path",
    "/api/v1/relationships",
    "/api/v1/relationships/{relationship_id}",
    "/api/v1/safety",
    "/api/v1/safety_legal",
    "/api/v1/source_link",
    "/api/v1/summary",
    "/api/v1/treatment_metrics",
})

# Required inputs are the part of a request contract whose tightening breaks
# an existing caller. Optional query additions remain compatible and are
# already checked for correct OpenAPI shape by test_web_openapi.py.
APPROVED_REQUIRED_PARAMETERS = {
    "/api/v1/authorities/{ons_code}": {"ons_code"},
    "/api/v1/catalogue/{dataset_id}": {"dataset_id"},
    "/api/v1/contracts/process/{ocid}": {"ocid"},
    "/api/v1/document_search": {"q"},
    "/api/v1/documents/{document_id}": {"document_id"},
    "/api/v1/export": {"endpoint"},
    "/api/v1/provider_compare": {"provider_key"},
    "/api/v1/providers/{provider_key}/lineage": {"provider_key"},
    "/api/v1/providers/{provider_key}/timeline": {"provider_key"},
    "/api/v1/relationship_path": {"from_id", "to_id"},
    "/api/v1/relationships/{relationship_id}": {"relationship_id"},
}


def _required_parameters(path_spec: dict) -> set[str]:
    return {
        parameter["name"]
        for parameter in path_spec.get("get", {}).get("parameters", [])
        if parameter.get("required")
    }


def classify(current: dict[str, dict]) -> dict[str, object]:
    current_paths = set(current)
    added = sorted(current_paths - APPROVED_PATHS)
    removed = sorted(APPROVED_PATHS - current_paths)
    required_changed = sorted(
        path for path in current_paths & APPROVED_PATHS
        if _required_parameters(current[path])
        != APPROVED_REQUIRED_PARAMETERS.get(path, set())
    )
    deprecated = sorted(
        path for path in current_paths & APPROVED_PATHS
        if current[path].get("get", {}).get("deprecated")
    )

    if removed or required_changed:
        label = "breaking"
    elif deprecated:
        label = "deprecated"
    elif added:
        label = "additive"
    else:
        label = "compatible"
    return {
        "classification": label,
        "added": added,
        "removed": removed,
        "required_changed": required_changed,
        "deprecated": deprecated,
    }


def test_public_contract_is_approved_and_classified() -> None:
    result = classify(openapi.document()["paths"])
    assert result["classification"] != "breaking", (
        "API contract classified as breaking; record an explicit compatibility "
        f"decision before changing the approved baseline: {result}"
    )


def test_openapi_required_parameters_match_the_approved_contract() -> None:
    paths = openapi.document()["paths"]
    assert set(paths) == APPROVED_PATHS
    for path in APPROVED_PATHS:
        assert _required_parameters(paths[path]) == APPROVED_REQUIRED_PARAMETERS.get(path, set())


def test_contract_classifier_distinguishes_the_four_compatibility_outcomes() -> None:
    baseline = openapi.document()["paths"]

    assert classify(baseline)["classification"] == "compatible"
    assert classify({**baseline, "/api/v1/new": {"get": {}}})["classification"] == "additive"
    deprecated = deepcopy(baseline)
    deprecated["/api/v1/summary"]["get"]["deprecated"] = True
    assert classify(deprecated)["classification"] == "deprecated"
    assert classify({path: spec for path, spec in baseline.items() if path != "/api/v1/summary"})[
        "classification"
    ] == "breaking"
    required_changed = deepcopy(baseline)
    required_changed["/api/v1/summary"]["get"]["parameters"] = [
        {"name": "q", "required": True}
    ]
    assert classify(required_changed)[
        "classification"
    ] == "breaking"

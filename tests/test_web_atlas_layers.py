"""Unified evidence atlas registry (BETA-078).

One closed registry of every layer the geography atlas can show. Exactly one
is drawn at a time — no overlay, no arithmetic between layers, no composite
score. Each entry is self-describing: the endpoint that serves it, the
legend, the unit, the caveat, the GeoJSON key and the accessible-table
columns.
"""
from __future__ import annotations

from pipeline.web import public_queries as pq


def test_the_registry_is_closed_and_self_describing() -> None:
    out = pq.atlas_layers()
    keys = {layer["key"] for layer in out["layers"]}
    assert keys == {
        "grant_drug_alcohol", "grant_total", "grant_per_head",
        "budget_public_health", "treatment_numbers", "contract_value",
        "cqc_locations", "coverage",
    }
    for layer in out["layers"]:
        assert layer["kind"] in ("choropleth", "points", "authority")
        assert layer["endpoint"] in ("geography", "layers")
        assert layer["legend"] and layer["unit"] and layer["caveat"]
        assert layer["geometry_key"]
        assert isinstance(layer["table_columns"], list) and layer["table_columns"]


def test_the_registry_states_the_no_composite_rule() -> None:
    note = pq.atlas_layers()["note"].lower()
    assert "one layer" in note and "composite" in note


def test_choropleth_layers_point_at_a_geography_metric() -> None:
    for layer in pq.atlas_layers()["layers"]:
        if layer["kind"] == "choropleth":
            assert layer["endpoint"] == "geography"
            assert layer["param"]["metric"] == layer["key"]
            assert layer["key"] in pq.GEOGRAPHY_METRICS


def test_point_and_authority_layers_name_a_layers_sublayer() -> None:
    for layer in pq.atlas_layers()["layers"]:
        if layer["kind"] in ("points", "authority"):
            assert layer["endpoint"] == "layers"
            assert layer["layer"] in ("contracts", "cqc_locations",
                                       "treatment", "coverage")


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/atlas_layers" in openapi.document()["paths"]

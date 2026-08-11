from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pipeline.exports import PERSONAL_DATA_COLUMNS, RESTRICTED_PREFIX
from pipeline.exports import docs as docs_export
from pipeline.exports import echarts as echarts_export
from pipeline.exports import geojson as geojson_export
from pipeline.exports import sheets as sheets_export
from pipeline.exports.schema import TABS

MIGRATIONS = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"


# --- the schema test the brief requires ------------------------------------------

def test_no_tab_query_returns_a_restricted_or_personal_column(conn):
    """Runs every tab's real SQL against the real schema and asserts nothing
    restricted comes back. This is the guard that must never be removed.
    """
    for tab in TABS:
        columns, _ = sheets_export.run_tab_query(conn, tab)
        for column in columns:
            assert not column.startswith(RESTRICTED_PREFIX), f"{tab.name}.{column}"
            assert column not in PERSONAL_DATA_COLUMNS, f"{tab.name}.{column}"


def test_no_tab_reads_from_a_restricted_table_directly():
    """restricted_ tables may appear as provenance contributors (officer
    counts derive from one) but must never be the source of exported columns.
    """
    for tab in TABS:
        assert RESTRICTED_PREFIX not in tab.sql, tab.name


def test_every_tab_declares_its_columns_and_they_match_the_query(conn):
    for tab in TABS:
        columns, _ = sheets_export.run_tab_query(conn, tab)
        assert columns == tab.columns, f"{tab.name}: declared columns differ from query output"


def test_there_are_nine_tabs():
    assert len(TABS) == 9
    assert len({t.name for t in TABS}) == 9


def test_every_tab_has_a_description_and_at_least_one_caveat():
    for tab in TABS:
        assert tab.description.strip()
        assert tab.caveats, f"{tab.name} has no caveats"


# --- sheets export ------------------------------------------------------------------

def test_sheets_export_writes_csv_and_provenance(conn, tmp_path):
    paths = sheets_export.export_sheets(conn, tmp_path)
    assert len(paths) == 9
    for path in paths:
        assert path.exists()
        provenance = path.with_suffix(path.suffix + ".provenance.json")
        assert provenance.exists(), f"no provenance for {path.name}"
        data = json.loads(provenance.read_text())
        assert data["export_type"] == "google_sheets_tab_csv"
        assert "generated_at" in data
        assert "contributions" in data
        assert data["caveats"]


def test_csv_carries_its_caveats_above_the_header(conn, tmp_path):
    sheets_export.export_sheets(conn, tmp_path)
    rows = list(csv.reader((tmp_path / "07_Tribunal_Cases.csv").open(encoding="utf-8")))
    caveat_rows = [r for r in rows if r and r[0].startswith("# CAVEAT:")]
    assert caveat_rows
    joined = " ".join(r[0] for r in caveat_rows)
    assert "claims-per-employee" in joined  # the one that matters most


# --- geojson export --------------------------------------------------------------------

def test_geojson_layers_are_separate_files(conn, tmp_path):
    paths = geojson_export.export_all(conn, tmp_path)
    names = {p.name for p in paths}
    assert names == {"contracts.geojson", "cqc_locations.geojson",
                      "treatment_numbers.geojson", "pfd_reports.geojson"}


def test_each_geojson_layer_carries_its_caveats_and_provenance(conn, tmp_path):
    for path in geojson_export.export_all(conn, tmp_path):
        payload = json.loads(path.read_text())
        assert payload["type"] == "FeatureCollection"
        assert payload["metadata"]["caveats"], f"{path.name} has no caveats"
        assert path.with_suffix(path.suffix + ".provenance.json").exists()


def test_cqc_layer_states_it_is_not_a_service_map(conn, tmp_path):
    geojson_export.export_all(conn, tmp_path)
    payload = json.loads((tmp_path / "cqc_locations.geojson").read_text())
    joined = " ".join(payload["metadata"]["caveats"])
    assert "not a map of services" in joined.lower() or "NOT a map of services" in joined


# --- echarts export ------------------------------------------------------------------------

def test_every_echarts_series_has_a_meta_block(conn, tmp_path):
    for path in echarts_export.export_all(conn, tmp_path):
        payload = json.loads(path.read_text())
        assert payload["series"], path.name
        for series in payload["series"]:
            meta = series.get("meta")
            assert meta, f"{path.name}: series {series.get('name')!r} has no meta"
            assert "source_systems" in meta
            assert "retrieved_at" in meta
            assert meta["caveats"], f"{path.name}: series has no caveats"


def test_echarts_files_have_provenance(conn, tmp_path):
    for path in echarts_export.export_all(conn, tmp_path):
        assert path.with_suffix(path.suffix + ".provenance.json").exists()


# --- data dictionary --------------------------------------------------------------------------

def test_data_dictionary_is_generated_from_the_live_schema(conn, tmp_path):
    path = docs_export.write_data_dictionary(conn, MIGRATIONS, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "do not edit by hand" in text.lower()
    # a table that exists in the schema must appear
    assert "`authorities`" in text
    assert "`contracts`" in text


def test_data_dictionary_marks_restricted_columns(conn, tmp_path):
    path = docs_export.write_data_dictionary(conn, MIGRATIONS, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "## Restricted tables" in text
    assert "restricted" in text


def test_data_dictionary_picks_up_migration_comments(conn, tmp_path):
    notes = docs_export.collect_table_notes(MIGRATIONS)
    assert "authorities" in notes
    assert notes["authorities"]


# --- provenance completeness ----------------------------------------------------------------------

def test_all_exports_produce_a_provenance_companion(conn, tmp_path):
    """Constraint 1: nothing leaves the warehouse without its provenance."""
    export_root = tmp_path / "exports"
    sheets_export.export_sheets(conn, export_root / "sheets")
    geojson_export.export_all(conn, export_root / "geojson")
    echarts_export.export_all(conn, export_root / "echarts")

    # Scoped to the export tree: tmp_path also holds the test fixture's own
    # warehouse.db, which is not an export.
    payloads = [p for p in export_root.rglob("*")
                 if p.is_file() and not p.name.endswith(".provenance.json")]
    assert payloads
    missing = [p.name for p in payloads
                if not p.with_suffix(p.suffix + ".provenance.json").exists()]
    assert missing == []

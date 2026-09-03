"""One zip of the evidence, and a manifest that accounts for all of it.

W-16: "the evidence" was nine CSVs, four GeoJSONs and five JSONs, each with a
`.provenance.json` beside it that had to be clicked separately. A companion
that needs a second click is a companion that gets lost, which is constraint 1
failing quietly rather than loudly.

The test that matters is the accounting one: the zip contains every file its
manifest names and no file the manifest does not. A bundle whose manifest and
contents disagree is worse than no manifest, because a reader checking one
against the other would conclude the wrong thing about which is right.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from pipeline.exports import bundle
from pipeline.exports import run as export_run
from pipeline.web import artefacts


@pytest.fixture
def exports(settings) -> Path:
    """An export directory in the shape the writers leave it: data files with
    provenance companions, one file without, and one orphan companion."""
    root = artefacts.export_root(settings)
    (root / "sheets").mkdir(parents=True, exist_ok=True)
    (root / "geojson").mkdir(parents=True, exist_ok=True)

    (root / "sheets" / "01_Authorities.csv").write_text(
        "ons_code,name\nE08000025,Birmingham\n", encoding="utf-8", newline="")
    (root / "sheets" / "01_Authorities.csv.provenance.json").write_text(
        json.dumps({"tables": ["authorities"]}), encoding="utf-8")
    (root / "geojson" / "contracts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    (root / "geojson" / "contracts.geojson.provenance.json").write_text(
        json.dumps({"tables": ["contracts"]}), encoding="utf-8")
    # No companion. The bundle has to say so rather than let it pass as one of
    # the rest.
    (root / "stray.csv").write_text("a,b\n1,2\n", encoding="utf-8", newline="")
    # A companion whose subject has gone.
    (root / "sheets" / "02_Grants.csv.provenance.json").write_text(
        json.dumps({"tables": ["public_health_grants"]}), encoding="utf-8")
    return root


def _members(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path) as archive:
        return set(archive.namelist())


def _manifest(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as archive:
        return json.loads(archive.read(bundle.MANIFEST_NAME))


# --- the accounting -------------------------------------------------------------


def test_the_zip_contains_every_file_its_manifest_names_and_no_other(exports):
    [written] = bundle.write_bundle(exports)
    manifest = _manifest(written)

    named = {entry["path"] for entry in manifest["files"]}
    named |= {entry["provenance"] for entry in manifest["files"] if entry["provenance"]}
    named |= set(manifest["orphan_provenance"])
    named |= set(manifest["also_included"])

    assert _members(written) == named


def test_every_hash_in_the_manifest_is_the_hash_of_the_file_in_the_zip(exports):
    """The manifest exists so a bundle can be checked after it has travelled.
    A hash taken of something other than what shipped would be worse than
    none."""
    [written] = bundle.write_bundle(exports)
    with zipfile.ZipFile(written) as archive:
        for entry in _manifest(written)["files"]:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]


def test_a_file_with_no_provenance_is_named_rather_than_passed_off(exports):
    [written] = bundle.write_bundle(exports)
    manifest = _manifest(written)

    assert manifest["without_provenance"] == ["stray.csv"]
    with zipfile.ZipFile(written) as archive:
        readme = archive.read(bundle.README_NAME).decode("utf-8")
    assert "stray.csv" in readme
    assert "no provenance companion" in readme


def test_a_paired_file_carries_its_companion_and_the_companion_is_not_a_row(exports):
    manifest = _manifest(bundle.write_bundle(exports)[0])
    by_path = {entry["path"]: entry for entry in manifest["files"]}

    assert by_path["sheets/01_Authorities.csv"]["provenance"] == \
        "sheets/01_Authorities.csv.provenance.json"
    assert by_path["sheets/01_Authorities.csv"]["provenance_sha256"]
    assert not any(path.endswith(bundle.PROVENANCE_SUFFIX) for path in by_path)


def test_an_orphan_companion_travels_and_is_named_as_one(exports):
    manifest = _manifest(bundle.write_bundle(exports)[0])
    assert manifest["orphan_provenance"] == ["sheets/02_Grants.csv.provenance.json"]


# --- what it refuses ------------------------------------------------------------


def test_bundling_an_empty_directory_is_a_refusal_not_an_empty_zip(settings, tmp_path):
    with pytest.raises(bundle.BundleError, match="Nothing to bundle"):
        bundle.write_bundle(tmp_path / "nothing-here")


def test_a_bundle_never_contains_a_previous_bundle(exports):
    """Otherwise every press of the button doubles the size of the artefact."""
    first = bundle.write_bundle(exports)[0]
    second = bundle.write_bundle(exports)[0]

    assert not any(name.startswith(bundle.BUNDLE_DIR) for name in _members(second))
    # Same day, same name, overwritten rather than accumulated: the date is
    # what a citation carries, and two bundles of the same directory on the
    # same afternoon are not two artefacts.
    assert first == second
    assert len(list((exports / bundle.BUNDLE_DIR).glob("*.zip"))) == 1


def test_a_symlink_out_of_the_export_tree_does_not_travel_in_the_zip(
        exports, tmp_path):
    """The same rule the download route applies: resolve, then check it is
    still under the export root."""
    target = tmp_path / "outside.db"
    target.write_text("outside", encoding="utf-8")
    link = exports / "sheets" / "escape.db"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("this platform/user cannot create symlinks")

    assert "sheets/escape.db" not in _members(bundle.write_bundle(exports)[0])


def test_an_interrupted_bundle_leaves_no_partial_zip_in_the_listing(exports):
    bundle.write_bundle(exports)
    assert not list((exports / bundle.BUNDLE_DIR).glob("*.partial"))


# --- and it is a target like any other --------------------------------------------


def test_bundle_is_a_target_and_runs_last_under_all():
    """`bundle` zips what is in the directory, so under `all` it has to run
    after the targets that put files there."""
    assert export_run.TARGETS[-1] == "bundle"
    assert export_run.resolve_targets("all")[-1] == "bundle"


def test_the_bundle_target_reports_the_file_it_wrote(conn, exports, settings):
    results = export_run.run_targets(
        conn, ["bundle"], exports, exports / "docs", settings)
    [result] = results

    assert result["target"] == "bundle"
    assert result["count"] == 1
    assert result["paths"][0].endswith(".zip")


def test_the_bundle_target_refuses_an_empty_directory_as_an_export_error(
        conn, settings, tmp_path):
    """Through `ExportError`, so the CLI and the job both report it the way
    they report an unknown target rather than as a traceback."""
    with pytest.raises(export_run.ExportError, match="Nothing to bundle"):
        export_run.run_targets(conn, ["bundle"], tmp_path / "empty",
                                tmp_path / "docs", settings)


def test_the_bundle_is_downloadable_from_the_exports_listing(exports, settings):
    """It lands in the export root, so the route that serves every other
    artefact serves this one without a new endpoint."""
    [written] = bundle.write_bundle(exports)
    relative = written.relative_to(exports).as_posix()

    listed = {entry["path"] for entry in artefacts.listing(settings)["files"]}
    assert relative in listed
    assert artefacts.resolve_for_download(settings, relative) == written
    assert artefacts.content_type(written) == "application/zip"

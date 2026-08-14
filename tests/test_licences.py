"""Every figure and every export can state its licence.

Reuse -- and defending reuse -- starts with the licence, and the portal named
none. The footer said "public-domain source" over material that is mostly but
not entirely OGL v3: the workforce census is NHS Benchmarking content with its
own terms, and council documents vary by council. Both are among the most
quotable sources the pipeline holds.

There is one table, in `pipeline/licences.py`, and two consumers. The export
layer reads it directly. The provenance drawer holds a copy, because the
drawer is drawn client-side from the module id the page already knows and this
phase added no route to fetch it over. A copy is only safe while something
fails when it drifts, which is what most of this file is.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline import licences
from pipeline.web import public_export

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "pipeline" / "web" / "static" / "public" / "js" / "components.js"

# The modules directory rather than MODULE_REGISTRY: other suites register
# doubles (`fake_writer_for_tests`) into the registry, and a double collects
# from nowhere and needs no licence. The files on disk are what fetches.
COLLECTING_MODULES = {path.stem for path in (ROOT / "pipeline" / "modules").glob("m*.py")}


# --- the table itself ---------------------------------------------------------


def test_every_module_that_collects_anything_declares_its_licence():
    """A source collected under terms nobody wrote down is a source nothing
    may be published from."""
    assert COLLECTING_MODULES, "no modules found; the glob is wrong"
    missing = sorted(COLLECTING_MODULES - set(licences.MODULE_LICENCES))
    assert not missing, (
        f"no licence recorded for {missing}. Read the module's row in "
        "docs/SOURCES.md and add it to pipeline/licences.py.")


def test_no_licence_is_recorded_for_a_module_that_does_not_exist():
    assert not set(licences.MODULE_LICENCES) - COLLECTING_MODULES


def test_every_module_points_at_a_licence_that_exists():
    for module, key in licences.MODULE_LICENCES.items():
        assert key in licences.LICENCES, f"{module} names unknown licence {key!r}"


def test_the_sources_that_are_not_ogl_are_not_quietly_ogl():
    """The point of the table. If these three ever read `ogl_v3`, the portal
    starts asserting a permission nobody granted."""
    assert licences.MODULE_LICENCES["m06_workforce_census"] == "nhs_benchmarking"
    assert licences.MODULE_LICENCES["m09_cdp_documents"] == "authority_varies"
    assert licences.MODULE_LICENCES["m15_foi"] == "mysociety_mixed"

    for key in ("nhs_benchmarking", "authority_varies", "charity_own",
                 "mysociety_mixed", "nhs_jobs"):
        assert licences.LICENCES[key].caution, (
            f"{key} is not a plain open licence and says nothing about why")


def test_every_exportable_endpoint_has_at_least_one_licence():
    for endpoint in public_export.EXPORTABLE:
        assert licences.for_endpoint(endpoint), (
            f"{endpoint} can be downloaded and names no terms")


# --- the export header --------------------------------------------------------


def test_every_export_header_carries_a_licence_line():
    """The finding, stated directly: a CSV that leaves this server is
    separated from any accompanying note within a day.

    Against `header()` rather than `to_csv`, because since W-06 there are two
    writers over one header — the in-memory one and the streamed one — and the
    licence has to be on both. `to_csv` now refuses the streamed endpoints
    outright, so testing through it would have quietly stopped covering
    contracts, which is the largest export this server offers.
    """
    for endpoint in public_export.EXPORTABLE:
        text = public_export.header(public_export.provenance(endpoint, {}), 1)
        lines = [line for line in text.splitlines() if line.startswith("# licence:")]
        assert lines, f"the {endpoint} export names no licence"
        assert all(len(line) > len("# licence: ") for line in lines)


def test_the_licence_line_names_the_deed_where_there_is_one():
    text = public_export.header(public_export.provenance("contracts", {}), 1)
    assert "# licence: Open Government Licence v3.0" in text
    assert "nationalarchives.gov.uk/doc/open-government-licence" in text
    assert "Contains public sector information" in text, "attribution is a condition"


def test_a_caution_travels_with_the_licence_it_belongs_to():
    """"Varies by authority" on its own invites the reader to assume OGL,
    which is the assumption it exists to prevent."""
    line = licences.statement(licences.LICENCES["authority_varies"])
    assert "Varies by authority" in line
    assert "Check the individual document" in line


def test_an_export_with_no_rows_still_states_its_terms():
    csv = public_export.to_csv([], public_export.provenance("pay", {}))
    assert "# licence:" in csv
    assert "# no rows matched" in csv


def test_the_json_export_and_the_response_header_carry_it_too():
    prov = public_export.provenance("ndtms", {})
    assert prov["licence"] and prov["licence"][0]["name"]
    # The same object goes into the JSON body and the X-Provenance header, so
    # it has to survive json.dumps.
    assert json.loads(json.dumps(prov, default=str))["licence"]


# --- and the drawer's copy has not drifted ------------------------------------


def _js_object(source: str, name: str) -> str:
    start = source.index(f"const {name} = {{")
    depth, cursor = 0, start
    for match in re.finditer(r"[{}]", source[start:]):
        depth += 1 if match.group(0) == "{" else -1
        cursor = start + match.end()
        if depth == 0:
            return source[start:cursor]
    raise AssertionError(f"{name} is not closed")


@pytest.fixture(scope="module")
def components() -> str:
    return COMPONENTS.read_text(encoding="utf-8")


def test_the_drawer_maps_the_same_modules_to_the_same_licences(components):
    block = _js_object(components, "MODULE_LICENCES")
    mirrored = dict(re.findall(r"(m\d\d_\w+): '([a-z0-9_]+)'", block))

    assert mirrored == licences.MODULE_LICENCES, (
        "components.js and pipeline/licences.py disagree about which source is "
        "under which licence. Edit both or neither.")


def _js_entries(source: str) -> dict[str, dict[str, str]]:
    """Each licence in the JS object, with its string fields joined back up.

    The fields are written as `'a ' + 'b'` continuations to stay inside the
    line length, so the pieces are concatenated here the way the browser does,
    and the one shared constant is substituted the way the browser would.
    """
    ogl = re.search(r"const OGL_URL = '([^']*)'", source)
    assert ogl, "components.js no longer declares OGL_URL"
    block = _js_object(source, "LICENCES").replace("OGL_URL", f"'{ogl.group(1)}'")

    entries: dict[str, dict[str, str]] = {}
    for key in re.findall(r"^  (\w+): \{", block, re.M):
        entry = block[block.index(f"  {key}: {{"):]
        entry = entry[:entry.index("\n  },")] if "\n  }," in entry else entry
        fields = {}
        for field in ("name", "url", "attribution", "caution"):
            match = re.search(rf"{field}: (null|(?:'[^']*'(?:\s*\+\s*)?)+)", entry)
            assert match, f"{key} has no {field}"
            raw = match.group(1)
            fields[field] = (None if raw == "null"
                             else "".join(re.findall(r"'([^']*)'", raw)))
        entries[key] = fields
    return entries


def test_the_drawer_holds_the_same_terms_word_for_word(components):
    """Word for word, because the attribution line is there to be copied.
    Two versions of it in circulation is the drift this pins against."""
    mirrored = _js_entries(components)
    assert set(mirrored) == set(licences.LICENCES)

    for key, licence in licences.LICENCES.items():
        entry = mirrored[key]
        # The apostrophe differs by design: the page uses a typographic one,
        # the CSV header stays ASCII.
        assert entry["name"].replace("’", "'") == licence.name, key
        assert entry["url"] == licence.url, key
        assert entry["attribution"].replace("’", "'") == licence.attribution, key
        assert entry["caution"].replace("’", "'") == licence.caution, key


def test_the_drawer_actually_renders_it(components):
    """A table nothing reads is a table that will drift."""
    drawer = components[components.index("export function provenance("):]
    drawer = drawer[:drawer.index("\n}\n")]
    assert "licenceFor(module)" in drawer
    assert "'Licence'" in drawer


def test_the_portal_footer_does_not_claim_everything_is_open():
    index = (COMPONENTS.parent.parent / "index.html").read_text(encoding="utf-8")
    footer = index[index.index("<footer"):]

    assert "Open Government Licence v3.0" in footer
    assert "not all of it" in footer, (
        "the footer should say the exceptions exist, not imply there are none")

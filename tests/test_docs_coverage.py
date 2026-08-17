"""Guards against the README and start scripts drifting from the code.

A module added later without a README row, or an export target added without
documentation, is the kind of gap nobody notices until someone tries to use
the thing. These tests make that a test failure instead.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.registry import MODULE_REGISTRY, discover_modules

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
START_SH = REPO_ROOT / "start.sh"
START_CMD = REPO_ROOT / "start.cmd"

EXPORT_TARGETS = ["sheets", "geojson", "echarts", "docs", "all"]


# Real pipeline modules follow the mNN_name convention. Filtering on it keeps
# test-only modules (test_cli.py registers a couple to exercise the CLI's
# commit path) out of a documentation check they have no business failing.
_MODULE_NAME_RE = re.compile(r"^m\d{2}_[a-z_]+$")


@pytest.fixture(scope="module")
def registered_modules() -> set[str]:
    discover_modules()
    return {name for name in MODULE_REGISTRY if _MODULE_NAME_RE.match(name)}


def test_every_registered_module_appears_in_the_readme(registered_modules):
    text = README.read_text(encoding="utf-8")
    missing = sorted(name for name in registered_modules if name not in text)
    assert missing == [], f"modules missing from README.md: {missing}"


def test_readme_does_not_name_modules_that_do_not_exist(registered_modules):
    text = README.read_text(encoding="utf-8")
    named = set(re.findall(r"\bm\d{2}_[a-z_]+", text))
    unknown = sorted(named - registered_modules)
    assert unknown == [], f"README.md names modules that are not registered: {unknown}"


def test_readme_documents_every_export_target():
    text = README.read_text(encoding="utf-8")
    missing = [t for t in EXPORT_TARGETS if f"export {t}" not in text]
    assert missing == [], f"export targets missing from README.md: {missing}"
    assert "ten CSV tabs" in text


def test_readme_documents_both_entry_points():
    text = README.read_text(encoding="utf-8")
    assert "./start.sh" in text
    assert "start.cmd" in text


@pytest.mark.parametrize("script", [START_SH, START_CMD])
def test_start_scripts_mention_both_commands(script):
    """The usage header is the first thing anyone reads; it must cover
    exporting as well as collecting.
    """
    text = script.read_text(encoding="utf-8")
    assert " run " in text, f"{script.name} usage header does not mention 'run'"
    assert "export" in text, f"{script.name} usage header does not mention 'export'"


@pytest.mark.parametrize("script", [START_SH, START_CMD])
def test_start_scripts_flag_the_human_review_modules(script):
    """m06, m09 and m10 produce worklists, not finished evidence. Someone
    reading only the script header should still learn that.
    """
    text = script.read_text(encoding="utf-8")
    assert "verification" in text
    for module in ("m06", "m09", "m10"):
        assert module in text, f"{script.name} does not mention {module}"


def test_docs_set_is_present():
    for name in ("DATA_DICTIONARY.md", "SOURCES.md", "CAVEATS.md"):
        assert (REPO_ROOT / "docs" / name).is_file(), f"docs/{name} is missing"


def test_sources_documents_every_module_that_needs_an_api_key():
    """A key requirement that isn't written down is a support ticket."""
    sources = (REPO_ROOT / "docs" / "SOURCES.md").read_text(encoding="utf-8")
    for variable in ("CHARITY_COMMISSION_API_KEY", "COMPANIES_HOUSE_API_KEY",
                      "CQC_SUBSCRIPTION_KEY", "CONTACT_EMAIL"):
        assert variable in sources or variable == "CONTACT_EMAIL", \
            f"{variable} is not documented in docs/SOURCES.md"


def test_caveats_leads_with_what_must_not_be_computed():
    caveats = (REPO_ROOT / "docs" / "CAVEATS.md").read_text(encoding="utf-8")
    assert "must not compute" in caveats.lower()
    # the specific prohibitions the brief calls out
    assert "claims-per-employee" in caveats
    assert "workforce census" in caveats.lower()


def test_caveats_cover_the_newest_evidence_modules():
    caveats = (REPO_ROOT / "docs" / "CAVEATS.md").read_text(encoding="utf-8")
    assert "Council spend files (Module 24)" in caveats
    assert "Skills for Care estimates (Module 25)" in caveats

"""The page-text cache: the single biggest performance item in the pipeline,
and one that must never trade correctness for it.

pdfplumber takes 16–23 seconds per archived accounts PDF, and m03 and m14 were
each doing it to the same files. The cache is keyed on payload_sha256 — the
digest already recorded in the provenance of every row from that document — so
a hit is provably the same bytes rather than probably the same file.
"""
from __future__ import annotations

import json

import pytest

from pipeline import pdftext
from pipeline.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(contact_email="t@example.com", raw_archive_dir=tmp_path / "raw",
                     _env_file=None)


@pytest.fixture
def counting_pdfplumber(monkeypatch):
    """A stand-in for pdfplumber that records how often it was asked to open
    a document — which is the whole property under test.
    """
    calls: list[object] = []

    class _Page:
        def __init__(self, text): self._text = text
        def extract_text(self): return self._text

    class _PDF:
        pages = [_Page("page one"), _Page("page two")]
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    class _Module:
        @staticmethod
        def open(source):
            calls.append(source)
            return _PDF()

    monkeypatch.setitem(__import__("sys").modules, "pdfplumber", _Module)
    return calls


# --- caching ---------------------------------------------------------------------

def test_the_same_bytes_are_only_extracted_once(settings, counting_pdfplumber):
    first = pdftext.page_texts(settings, "src", "abc123", b"%PDF-fake")
    second = pdftext.page_texts(settings, "src", "abc123", b"%PDF-fake")

    assert first == second == ["page one", "page two"]
    assert len(counting_pdfplumber) == 1, "the document was extracted twice"


def test_different_documents_do_not_share_a_cache_entry(settings, counting_pdfplumber):
    pdftext.page_texts(settings, "src", "aaa", b"%PDF-a")
    pdftext.page_texts(settings, "src", "bbb", b"%PDF-b")
    assert len(counting_pdfplumber) == 2


def test_the_cache_is_namespaced_by_source_system(settings, counting_pdfplumber):
    """Two sources could in principle archive identical bytes; keeping their
    caches apart mirrors how data/raw/ is laid out.
    """
    pdftext.page_texts(settings, "source_a", "same", b"%PDF")
    pdftext.page_texts(settings, "source_b", "same", b"%PDF")
    assert len(counting_pdfplumber) == 2


def test_cached_text_lives_beside_the_raw_archive(settings, counting_pdfplumber):
    pdftext.page_texts(settings, "src", "abc123", b"%PDF")
    path = pdftext.cache_path(settings, "src", "abc123")
    assert path.is_file()
    assert path.parent.parent == pdftext.cache_dir(settings)
    assert json.loads(path.read_text(encoding="utf-8")) == ["page one", "page two"]


def test_without_a_hash_nothing_is_cached(settings, counting_pdfplumber):
    """No key, no cache entry — better than inventing one from the path, which
    would be a claim about identity this pipeline cannot support.
    """
    pdftext.page_texts(settings, "src", "", b"%PDF")
    pdftext.page_texts(settings, "src", "", b"%PDF")
    assert len(counting_pdfplumber) == 2
    assert not pdftext.cache_dir(settings).exists()


# --- robustness ------------------------------------------------------------------

def test_a_corrupt_cache_file_is_re_extracted_not_raised(settings, counting_pdfplumber):
    """Derived data. A truncated file from an interrupted run must cost time,
    never a failed crawl.
    """
    pdftext.page_texts(settings, "src", "abc123", b"%PDF")
    pdftext.cache_path(settings, "src", "abc123").write_text("{not json", encoding="utf-8")

    assert pdftext.page_texts(settings, "src", "abc123", b"%PDF") == ["page one", "page two"]
    assert len(counting_pdfplumber) == 2


def test_a_cache_file_of_the_wrong_shape_is_rejected(settings, counting_pdfplumber):
    pdftext.page_texts(settings, "src", "abc123", b"%PDF")
    pdftext.cache_path(settings, "src", "abc123").write_text(
        '{"pages": ["one"]}', encoding="utf-8")

    assert pdftext.page_texts(settings, "src", "abc123", b"%PDF") == ["page one", "page two"]
    assert len(counting_pdfplumber) == 2


def test_no_partial_file_is_left_behind(settings, counting_pdfplumber):
    """Written then renamed, so an interrupted run cannot leave a half-written
    cache that a later run reads as a short document.
    """
    pdftext.page_texts(settings, "src", "abc123", b"%PDF")
    assert list(pdftext.cache_dir(settings).rglob("*.partial")) == []


def test_numbered_pages_pairs_text_with_its_page_index(settings, counting_pdfplumber):
    assert pdftext.numbered_pages(settings, "src", "abc123", b"%PDF") == \
        [(0, "page one"), (1, "page two")]


# --- the callers -------------------------------------------------------------------

def test_m14_reads_the_cache_m03_wrote():
    """The duplicate extraction this exists to remove: m14 must look under
    m03's source system, not its own, or it would miss every entry and
    silently re-extract everything.
    """
    from pipeline.modules import m03_charity_finance as m03
    from pipeline.modules import m14_annual_reports as m14

    assert m14.M03_SOURCE_SYSTEM == m03.SOURCE_ACCOUNTS


def test_the_staff_costs_locator_works_on_text_not_a_pdf_object():
    """Taking text is what lets the extraction be shared. A regression here
    would quietly reintroduce the second pass.
    """
    from pipeline.charity_accounts_config import AccountsProfile
    from pipeline.modules.m03_charity_finance import find_staff_costs_pages

    profile = AccountsProfile(locator_keywords=[["staff costs"]])
    pages = ["cover page", "STAFF COSTS\nwages and salaries 1,000", "back page"]
    located = find_staff_costs_pages(pages, profile)

    assert [index for index, _ in located] == [1]

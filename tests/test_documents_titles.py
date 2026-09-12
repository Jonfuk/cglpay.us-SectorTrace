"""Deterministic display-title derivation (BETA-062).

The point of `titles.derive` is the precedence and what it refuses to call a
title: a hash-like filename, a bare reference number, or a generic filler
word all fall through rather than become the name a reader sees.
"""
from __future__ import annotations

from pipeline.documents import titles


def test_the_source_label_wins_when_it_is_a_real_name():
    display, basis = titles.derive(
        source_title="Kent drug and alcohol strategy 2024",
        pdf_title="Microsoft Word - final.docx",
        headings=["Contents"], filename="a3f91c2b.pdf")
    assert (display, basis) == ("Kent drug and alcohol strategy 2024", "source_label")


def test_pdf_metadata_is_next_when_the_source_label_is_missing_or_noise():
    display, basis = titles.derive(
        source_title="document",  # generic filler — not identity
        pdf_title="Joint Strategic Needs Assessment: Substance Misuse",
        headings=["1"], filename="download.pdf")
    assert basis == "pdf_metadata"
    assert display == "Joint Strategic Needs Assessment: Substance Misuse"


def test_the_first_usable_heading_is_next():
    display, basis = titles.derive(
        source_title=None, pdf_title=None,
        headings=["  ", "Page 1", "Cabinet Report — Treatment Recommissioning"],
        filename="6f2c9a1b4e8d.pdf")
    assert (display, basis) == (
        "Cabinet Report — Treatment Recommissioning", "heading")


def test_a_de_slugified_filename_is_the_last_resort():
    display, basis = titles.derive(
        source_title="", pdf_title="", headings=[],
        filename="Kent-JSNA-substance-misuse-2024.pdf")
    # Separators become spaces; casing is left as the source had it.
    assert (display, basis) == ("Kent JSNA substance misuse 2024", "filename")


def test_a_hash_like_filename_yields_unknown_not_a_title():
    assert titles.derive(filename="a3f91c2b8e4d5f6071829304a5b6c7d8.pdf") == (
        None, "unknown")
    assert titles.derive(filename="7b1e2c3d-4f5a-6b7c-8d9e.bin")[1] == "unknown"


def test_bare_numbers_and_reference_codes_are_not_identity():
    assert titles.derive(source_title="2024-04-01", filename="x")[1] == "unknown"
    assert titles.derive(source_title="TA1", filename="x")[1] == "unknown"
    assert titles.derive(source_title="v2.3", filename="x")[1] == "unknown"


def test_whitespace_quotes_and_length_are_normalised():
    display, _ = titles.derive(source_title='  "  Spaced  Title  "  ')
    assert display == "Spaced Title"
    long_display, _ = titles.derive(source_title="A" * 500)
    assert len(long_display) <= 201 and long_display.endswith("…")


def test_rank_of_orders_the_bases_and_sinks_the_unknown():
    assert titles.rank_of("source_label") < titles.rank_of("heading")
    assert titles.rank_of("heading") < titles.rank_of("filename")
    assert titles.rank_of("not-a-basis") == len(titles.TITLE_BASES)

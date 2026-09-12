"""Conservative URL canonicalisation (BETA-057).

The point is what it refuses to do. It normalises the case-insensitive parts
and strips tracking noise, and it does *not* resolve `..`, add/remove `www`,
collapse `/index.html`, or follow a redirect — every one of those is a place
"probably the same" becomes a wrong merge.
"""
from __future__ import annotations

from pipeline.url_canon import canonical


def test_the_fragment_is_dropped():
    assert canonical("https://x.gov.uk/a/b#section-3") == "https://x.gov.uk/a/b"


def test_tracking_parameters_are_dropped_but_real_ones_kept():
    got = canonical("https://x.gov.uk/doc?id=42&utm_source=news&gclid=abc&page=2")
    assert got == "https://x.gov.uk/doc?id=42&page=2"


def test_the_query_is_sorted_so_order_does_not_matter():
    a = canonical("https://x.gov.uk/d?b=2&a=1")
    b = canonical("https://x.gov.uk/d?a=1&b=2")
    assert a == b == "https://x.gov.uk/d?a=1&b=2"


def test_scheme_and_host_are_lowercased_and_one_trailing_slash_stripped():
    assert canonical("HTTPS://X.Gov.UK/Path/") == "https://x.gov.uk/Path"
    # Path case is preserved — only the trailing slash goes.
    assert canonical("https://x.gov.uk/Path/More/") == "https://x.gov.uk/Path/More"


def test_a_default_port_is_dropped_but_a_real_one_is_kept():
    assert canonical("https://x.gov.uk:443/a") == "https://x.gov.uk/a"
    assert canonical("http://x.gov.uk:8080/a") == "http://x.gov.uk:8080/a"


def test_it_does_not_resolve_dot_dot_or_touch_www_or_index_html():
    assert canonical("https://x.gov.uk/a/../b") == "https://x.gov.uk/a/../b"
    assert canonical("https://www.x.gov.uk/a") != canonical("https://x.gov.uk/a")
    assert canonical("https://x.gov.uk/dir/index.html") != canonical("https://x.gov.uk/dir")


def test_a_non_http_value_is_returned_stripped_not_transformed():
    assert canonical("  not a url  ") == "not a url"
    assert canonical("ftp://x/y") == "ftp://x/y"

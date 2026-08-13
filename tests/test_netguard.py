"""Where a fetch is allowed to land.

The operator UI takes a URL from whoever can reach it and fetches it, with no
authentication and a default bind on every interface. These tests are the
difference between that being a URL checker and it being a port scanner with a
nice front end.

Every one injects a resolver. Nothing here touches DNS.
"""
from __future__ import annotations

import socket

import pytest

from pipeline.netguard import BlockedAddress, addresses_for, check_url


def resolving_to(*addresses):
    """A resolver that answers with these addresses whatever it is asked."""
    def resolver(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                  (address, port)) for address in addresses]
    return resolver


PUBLIC = resolving_to("93.184.216.34")


# --- the families that must be refused -----------------------------------------


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "https://[::1]/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://169.254.169.254/",          # cloud metadata, the classic target
    "http://0.0.0.0/",
    "http://[fd00::1]/",                # unique local
    "http://[fe80::1]/",                # link local
])
def test_an_address_literal_in_private_space_is_refused(url):
    with pytest.raises(BlockedAddress):
        check_url(url, resolver=PUBLIC)


def test_a_literal_does_not_need_a_resolver_at_all():
    """The common attempt is a literal, and refusing it must not depend on DNS
    being reachable."""
    def explode(*args, **kwargs):
        raise AssertionError("a literal must not be resolved")

    with pytest.raises(BlockedAddress):
        check_url("http://127.0.0.1/", resolver=explode)


@pytest.mark.parametrize("host", [
    "localhost",
    "internal.corp",
    "127.0.0.1.nip.io",
    "totally-innocent.example",
    # Dotted shorthand. `ipaddress` will not parse this, so it takes the
    # resolution path like any name -- which is the right outcome by a route
    # worth knowing about. What the OS does with it varies: Linux expands it
    # to 127.0.0.1, Windows refuses to resolve it at all. Refused either way,
    # so the guard does not depend on which.
    "127.1",
])
def test_a_name_is_judged_by_what_it_resolves_to(host):
    """A blocklist of names refuses `localhost` and misses every other way of
    saying the same thing. What matters is where the packet would go."""
    with pytest.raises(BlockedAddress, match="loopback"):
        check_url(f"http://{host}/", resolver=resolving_to("127.0.0.1"))


def test_a_name_resolving_to_both_public_and_private_is_refused():
    """Which of the two gets connected to is not this code's decision."""
    with pytest.raises(BlockedAddress):
        check_url("http://split.example/",
                   resolver=resolving_to("93.184.216.34", "10.0.0.1"))


def test_the_refusal_says_which_kind_of_address_it_was():
    with pytest.raises(BlockedAddress, match="private"):
        check_url("http://x.example/", resolver=resolving_to("10.0.0.1"))
    with pytest.raises(BlockedAddress, match="link-local"):
        check_url("http://x.example/", resolver=resolving_to("169.254.169.254"))


def test_a_name_that_does_not_resolve_is_refused_not_fetched():
    def fails(*args, **kwargs):
        raise socket.gaierror("no such host")

    with pytest.raises(BlockedAddress, match="does not resolve"):
        check_url("http://nowhere.example/", resolver=fails)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.org/x",
    "gopher://example.org/",
])
def test_only_http_and_https_are_fetchable(url):
    with pytest.raises(BlockedAddress):
        check_url(url, resolver=PUBLIC)


def test_a_url_with_no_host_is_refused():
    with pytest.raises(BlockedAddress, match="no host"):
        check_url("http:///just-a-path", resolver=PUBLIC)


# --- and what must still work --------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://www.kent.gov.uk/",
    "https://democracy.eastsussex.gov.uk/ieSearchResults2.aspx?q=drugs",
    "http://committees.scilly.gov.uk/",          # http, and a real one
    "https://www.whatdotheyknow.com/feed/search/x",
    "https://example.org:8443/on-an-odd-port",
])
def test_a_council_website_still_resolves(url):
    """Over-refusing breaks a working feature. These are shapes the pipeline
    actually fetches, including one on http and one on a non-default port."""
    check_url(url, resolver=PUBLIC)


def test_a_public_address_literal_is_fine():
    check_url("http://93.184.216.34/", resolver=PUBLIC)


def test_addresses_for_returns_every_answer():
    found = addresses_for("x.example", 443,
                           resolving_to("93.184.216.34", "93.184.216.35"))

    assert [str(a) for a in found] == ["93.184.216.34", "93.184.216.35"]


# --- through the client, which is where redirects live -------------------------


def test_the_guard_applies_to_a_redirect_hop(settings, httpx_mock):
    """The case a single up-front check misses.

    httpx follows redirects itself, so a public URL that 302s into private
    space is one request the caller made and a second it did not. The second
    is the one worth stopping.
    """
    from pipeline.http import PipelineHTTPClient
    from pipeline.netguard import BlockedAddress

    httpx_mock.add_response(url="https://council.example/robots.txt", text="")
    httpx_mock.add_response(url="https://council.example/doc",
                             status_code=302,
                             headers={"Location": "http://10.0.0.5/secret"})

    def resolver(host, port, *args, **kwargs):
        address = "10.0.0.5" if host == "10.0.0.5" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                  (address, port))]

    with PipelineHTTPClient("test", settings=settings, guard_destination=True,
                             resolver=resolver) as client:
        with pytest.raises(BlockedAddress):
            client.get("https://council.example/doc")


def test_an_unguarded_client_is_the_default(settings, httpx_mock):
    """Modules fetch addresses they found on published pages, not addresses a
    person typed, and turning this on for them would make every offline test in
    the suite do a real lookup for a host that does not exist."""
    from pipeline.http import PipelineHTTPClient

    httpx_mock.add_response(url="http://10.0.0.5/robots.txt", text="")
    httpx_mock.add_response(url="http://10.0.0.5/x", text="fine")

    with PipelineHTTPClient("test", settings=settings) as client:
        assert client.get("http://10.0.0.5/x").ok


# --- the two routes that take a URL from a person ------------------------------


def _private(host, port, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
              ("192.168.1.1", port))]


def test_check_url_refuses_the_operators_own_network(settings, conn):
    """The finding this phase exists for: without the guard this answers
    'yes it responded, and here is what it looked like'."""
    from pipeline.web import resolve

    result = resolve.check_url("http://router.internal/", settings, conn,
                                resolver=_private)

    assert result["ok"] is False
    assert result["status"] is None, "nothing was fetched"
    assert "192.168.1.1" in result["error"]
    assert "public web" in result["error"]


# The working path is covered by tests/test_web_resolve.py, which drives the
# real council-URL flow end to end. Those tests now run with the guard active
# -- conftest resolves every name to a public address -- so "a council still
# resolves" is asserted there rather than duplicated here against a mock of
# the committee-system probing this module does not own.


def test_promotion_refuses_a_candidate_pointing_inward(settings, conn):
    """A candidate is a link copied off a council's page, so anyone who can
    publish there chooses this URL."""
    from pipeline import promote

    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES "
        "('E10000016', 'Kent', 'CTY', '2013-04-01', '2024', '2024', 'u', "
        "'2026-08-01T00:00:00Z', 200, 'ons', 'abc')")
    conn.execute(
        "INSERT INTO cdp_document_candidates (authority_ons_code, candidate_url, "
        "title, document_type_guess, confidence, discovered_at, discovery_method, "
        "verified, rejected, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016', 'http://192.168.1.1/admin', 'Strategy', "
        "'strategy', 0.9, '2026-08-01T00:00:00Z', 'link', 0, 0, 'u', "
        "'2026-08-01T00:00:00Z', 200, 'm09', 'h')")
    conn.commit()

    with pytest.raises(promote.PromotionError, match="192.168.1.1"):
        promote.promote(conn, "cdp_document", "http://192.168.1.1/admin",
                         promoted_by="Jon", fields={"document_type": "strategy"},
                         settings=settings, resolver=_private)

    assert conn.execute("SELECT COUNT(*) FROM cdp_documents").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM evidence_promotions").fetchone()[0] == 0

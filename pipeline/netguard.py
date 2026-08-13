"""Where a fetch is allowed to land.

`/api/resolve/check-url` and the promote route both take a URL from whoever is
using the operator UI and go and fetch it. There is no authentication here by
design and the server binds every interface by default, so without this
anyone who can reach the UI can ask the pipeline to fetch
`http://192.168.1.1/` and be told whether it answered, what it looked like,
and whether it responds to a ModernGov signature path. That is a port scanner
with a nice front end, running from inside the operator's network.

The check is on the **resolved address**, not on the hostname. A blocklist of
names refuses `localhost` and misses `127.0.0.1`, `2130706433`,
`127.0.0.1.nip.io`, and any name whose owner points it at an internal address.
What matters is where the packet would go.

Two honest limits, neither of which makes this not worth having:

  * **It resolves, then httpx resolves again to connect.** A name that answers
    differently between those two lookups (DNS rebinding) is not caught. Doing
    better means pinning the connection to the address that was checked, which
    is a custom transport; if this ever guards something more valuable than a
    LAN, that is the next step.

  * **It is not a firewall.** It stops this pipeline being *used* to reach
    private space. It does nothing about what the machine itself can reach.

The resolver is injected so that this is testable without DNS. The whole test
suite runs offline and hermetically, and a guard that made 1,300 tests do
real lookups would be its own problem.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

log = structlog.get_logger()

# Indirection so tests can substitute a resolver without touching the socket
# module itself. Patching `socket.getaddrinfo` is patching it for everything
# in the process -- including httpx connecting to the test server on
# 127.0.0.1, which then resolves somewhere else and times out.
DEFAULT_RESOLVER = socket.getaddrinfo


class BlockedAddress(Exception):
    """A URL that resolves somewhere this pipeline will not fetch from."""


def _describe(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Why this address is refused, in the words a person would use."""
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link-local"
    if address.is_private:
        return "private"
    if address.is_multicast:
        return "multicast"
    if address.is_reserved:
        return "reserved"
    if address.is_unspecified:
        return "unspecified"
    return "not a global address"


def addresses_for(host: str, port: int, resolver=None) -> list:
    """Every address this host resolves to, as ipaddress objects.

    An IP literal resolves to itself without a lookup, which matters: the
    common attempt is a literal, and it should not depend on a resolver being
    reachable.
    """
    try:
        return [ipaddress.ip_address(host.strip("[]"))]
    except ValueError:
        pass

    resolver = resolver or DEFAULT_RESOLVER
    try:
        infos = resolver(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise BlockedAddress(f"{host} does not resolve ({exc}).") from exc

    found = []
    for info in infos:
        sockaddr = info[4]
        try:
            found.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:  # pragma: no cover - a resolver returning nonsense
            continue
    if not found:
        raise BlockedAddress(f"{host} resolves to no usable address.")
    return found


def check_url(url: str, resolver=None) -> None:
    """Raise `BlockedAddress` unless every address this URL resolves to is
    public.

    Every address, not the first: a name that resolves to both a public and a
    private address is refused, because which one gets connected to is not
    this code's decision.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedAddress(
            f"{parsed.scheme or 'that'}: URLs are not fetchable here — use http or https.")
    if not parsed.hostname:
        raise BlockedAddress(f"{url!r} has no host to check.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    for address in addresses_for(parsed.hostname, port, resolver):
        if not address.is_global:
            reason = _describe(address)
            log.warning("http.blocked_address", url=url, host=parsed.hostname,
                         address=str(address), reason=reason)
            raise BlockedAddress(
                f"{parsed.hostname} resolves to {address} ({reason}). This "
                "pipeline fetches published documents from the public web; it "
                "is not a way to reach the network it is running on.")


def guard_hook(resolver=None):
    """An httpx request event hook that applies `check_url` to every request.

    A hook rather than one check before the call, because httpx follows
    redirects itself: a public URL that 302s to `http://10.0.0.1/` is one
    request the caller made and a second it did not, and the second is the one
    worth stopping. Each redirect hop is a request through the same client, so
    each one passes through here.
    """
    def hook(request) -> None:
        check_url(str(request.url), resolver)

    return hook

"""Authority-name normalisation and lookup, shared by every module that
receives a bare council name from its source instead of a GSS/ONS code
(Find a Tender / Contracts Finder buyer names in Module 1, CQC's
`localAuthority` field in Module 5).

Previously duplicated independently in `m01_procurement` and `m05_cqc`,
which disagreed on which council-name suffixes to strip and, between them,
mishandled every English authority whose ONS name takes the "<name>, City
of" / "<name>, County of" form -- Bristol, Herefordshire and Kingston upon
Hull all failed to normalise to their plain form, confirmed by running both
prior implementations directly. See
`docs/mysociety-identifier-mappings-feasibility.md` S5 for the full
comparison. One implementation now, with both suffixes covered.
"""
from __future__ import annotations

import re

_COUNCIL_SUFFIX_RE = re.compile(
    r"\b(metropolitan borough council|metropolitan district council|"
    r"county council|city council|borough council|district council|"
    r"unitary authority|royal borough of|london borough of|city of|"
    r"county of|council)\b",
    re.IGNORECASE,
)


def normalise_authority_name(name: str | None) -> str:
    text = (name or "").lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = _COUNCIL_SUFFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_authority_lookup(conn) -> dict[str, str]:
    """{normalised_name: ons_code}, across every authority row this pipeline
    knows -- current and retired, so a notice or record referencing an
    abolished council still joins.
    """
    lookup: dict[str, str] = {}
    for row in conn.execute("SELECT ons_code, name FROM authorities ORDER BY ons_code"):
        lookup.setdefault(normalise_authority_name(row["name"]), row["ons_code"])
    return lookup

"""Deterministic, operator-only role triage for Open Jobs observations.

The classifier is a finding aid, not a relevance score.  A match creates a
human review item and never promotes an advert, identifies an employer, or
claims that a vacancy belongs to the substance-misuse sector.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.modules.m16_nhs_jobs import ROLE_KEYWORDS

# Keep the shared NHS Jobs vocabulary as the first part of this list so the
# same role language is used across the two source-specific collectors.  The
# extra phrases are deliberately narrow; broad words such as "care" and
# "support" produce an unreviewable queue of unrelated jobs.
POSITIVE_TERMS: tuple[str, ...] = tuple(dict.fromkeys(
    (*ROLE_KEYWORDS,
     "substance use", "addiction worker", "addictions worker", "addiction",
     "opioid", "opiate", "detox", "needle exchange", "harm reduction",
     "drug treatment", "alcohol treatment", "treatment recovery"),
))

# These phrases are common false positives for the word "recovery".  They
# remain visible in the triage result so an operator can audit why a row was
# excluded from the candidate count.
NEGATIVE_TERMS: tuple[str, ...] = (
    "disaster recovery", "data recovery", "debt recovery", "vehicle recovery",
    "mortgage recovery", "recovery of", "recovery technician",
)

# Location is a separate tri-state finding aid.  A country or region not in
# either list remains unresolved; an unrecognised value is never treated as
# proof that an advert is outside England.
ENGLAND_TERMS: tuple[str, ...] = (
    "england", "london", "birmingham", "leeds", "sheffield", "liverpool",
    "bristol", "newcastle", "nottingham", "leicester", "coventry", "sunderland",
    "hull", "york", "manchester", "north east", "north west", "yorkshire",
    "east midlands", "west midlands", "east of england", "south east",
    "south west", "tyne and wear", "greater manchester", "merseyside",
    "lancashire", "cheshire", "cumbria", "county durham", "durham",
    "northumberland", "west yorkshire", "south yorkshire", "north yorkshire",
    "east riding", "lincolnshire", "nottinghamshire", "derbyshire",
    "leicestershire", "northamptonshire", "staffordshire", "warwickshire",
    "worcestershire", "shropshire", "herefordshire", "gloucestershire",
    "bristol", "somerset", "dorset", "devon", "cornwall", "wiltshire",
    "hampshire", "surrey", "east sussex", "west sussex", "kent", "essex",
    "suffolk", "norfolk", "cambridgeshire", "hertfordshire", "bedfordshire",
    "buckinghamshire", "berkshire", "oxfordshire", "rutland",
    # Common place-only values returned by the Open Jobs feeds.  A place name
    # is useful evidence when it is paired with a UK region in the source;
    # non-England markers are checked first for ambiguous names such as York.
    "gateshead", "royal tunbridge wells", "tunbridge wells", "leatherhead",
    "preston", "barnet", "bromley", "reading", "exeter", "brighton",
    "portsmouth", "southampton", "milton keynes", "luton", "basildon",
    "colchester", "ipswich", "peterborough", "cambridge", "oxford", "swindon",
    "bath", "plymouth", "torquay", "gloucester", "worcester", "derby",
    "lincoln", "doncaster", "wakefield", "bradford", "huddersfield", "harrogate",
    "blackpool", "bolton", "stockport", "wigan", "salford", "oldham", "rochdale",
    "burnley", "blackburn", "birkenhead", "st helens", "warrington", "crewe",
    "macclesfield", "carlisle", "middlesbrough", "darlington", "hartlepool",
    "newcastle upon tyne", "scarborough", "grimsby", "chester", "shrewsbury",
    "telford", "wolverhampton", "warwick", "northampton", "bedford", "watford",
    "st albans", "chelmsford", "southend", "maidstone", "canterbury", "ashford",
    "guildford", "woking", "redhill", "crawley", "worthing", "eastbourne", "hastings",
    "bournemouth", "poole", "salisbury", "taunton", "truro", "newquay", "barnstaple",
)

NON_ENGLAND_TERMS: tuple[str, ...] = (
    "scotland", "wales", "northern ireland", "republic of ireland", "ireland",
    "united states", "usa", "us", "canada", "india", "philippines", "australia",
    "new zealand", "south africa", "singapore", "malaysia", "indonesia", "china",
    "japan", "united arab emirates", "dubai", "saudi arabia", "ontario", "alberta",
    "british columbia", "new south wales", "victoria", "queensland", "western australia",
    "south australia", "tasmania", "australian capital territory", "northern territory",
    # State/province names catch feeds which omit the country (for example
    # ``Spokane, Washington``).  Codes are handled separately below.
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas",
    "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming",
)

# A few feeds use postal abbreviations with no country name (``Athens, GA``).
# Restrict this to comma/line boundaries so ordinary words cannot be mistaken
# for a location marker.
_US_STATE_CODE = re.compile(
    r"(?:^|[,;/]\s*)(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)(?:\s*[,;/]|$)",
    re.IGNORECASE,
)


def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


_POSITIVE = tuple((term, _pattern(term)) for term in POSITIVE_TERMS)
_NEGATIVE = tuple((term, _pattern(term)) for term in NEGATIVE_TERMS)
_ENGLAND = tuple((term, _pattern(term)) for term in ENGLAND_TERMS)
_NON_ENGLAND = tuple((term, _pattern(term)) for term in NON_ENGLAND_TERMS)


@dataclass(frozen=True)
class TriageResult:
    """The explainable result for one current advert observation."""

    decision: str
    matched_terms: tuple[str, ...]
    excluded_terms: tuple[str, ...]
    matched_fields: tuple[str, ...]
    location_state: str

    @property
    def candidate(self) -> bool:
        return self.decision == "candidate"

    def payload(self) -> dict[str, object]:
        return {
            "triage_version": "role_v1",
            "decision": self.decision,
            "matched_terms": list(self.matched_terms),
            "excluded_terms": list(self.excluded_terms),
            "matched_fields": list(self.matched_fields),
            "location_state": self.location_state,
        }


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    return str(value)


def classify(*, title: str | None, company: str | None, location: str | None,
             content: object = None, departments: object = None) -> TriageResult:
    """Classify an advert as a review candidate or an excluded finding aid.

    Matching is case-insensitive and preserves the field in which a term was
    found.  Location is recorded for audit but does not decide England scope;
    that remains a human decision because aggregator geography can be partial
    or ambiguous.
    """
    fields = {
        "title": _text(title),
        "company": _text(company),
        "location": _text(location),
        "content": _text(content),
        "departments": _text(departments),
    }
    location_text = fields["location"]
    if (_US_STATE_CODE.search(location_text)
            or any(pattern.search(location_text) for _, pattern in _NON_ENGLAND)):
        location_state = "non_england"
    elif any(pattern.search(location_text) for _, pattern in _ENGLAND):
        location_state = "england"
    else:
        location_state = "unresolved"
    matched_terms: list[str] = []
    matched_fields: list[str] = []
    for term, pattern in _POSITIVE:
        field_hits = [name for name, value in fields.items() if pattern.search(value)]
        if field_hits:
            matched_terms.append(term)
            matched_fields.extend(field_hits)
    excluded_terms = [term for term, pattern in _NEGATIVE
                      if any(pattern.search(value) for value in fields.values())]
    if not matched_terms and excluded_terms:
        decision = "excluded"
    elif not matched_terms:
        decision = "no_match"
    elif excluded_terms:
        decision = "excluded"
    else:
        decision = "candidate"
    return TriageResult(
        decision=decision,
        matched_terms=tuple(matched_terms),
        excluded_terms=tuple(excluded_terms),
        matched_fields=tuple(dict.fromkeys(matched_fields)),
        location_state=location_state,
    )

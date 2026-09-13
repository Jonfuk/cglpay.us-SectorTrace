# Open Referral UK service directories — feasibility (JON-7)

**Status: research only. No code, migration or module changed.** Written
against commit `55fde50` with a clean tree, as the bounded research
deliverable for JON-7 ("Explore Open Referral UK service directories"),
whose readiness label (Not scheduled / Post-V1) requires a named human
decision before anything in §8 is built. This document assesses ORUK feeds
and comparable council directories for services, locations, eligibility,
service type and geographic coverage; generates no provider candidates
itself (that is implementation); and sets out feasibility, source/access
terms, provenance requirements, an integration approach and draft acceptance
criteria — not an implementation, per the ticket's own acceptance criteria.

The ticket's own module-audit note asks that current source claims and
repository state be verified rather than assumed. Every factual claim below
about the standard, its governance and its live feeds was checked against a
primary source while writing this document: the standard's own GitHub
profile, its own published feed directory, and live queries against three
of the ten feeds that directory currently lists — not a third-party summary
of any of them. Two things that only surfaced by querying live feeds rather
than reading about them: the standard's own taxonomy mechanism is present
in the schema but returned zero populated terms on the one feed checked for
it, and two feed-level query parameters that look like they should filter
results (`search=`, `organization_id=`) are silently ignored by the
implementation tested — both are recorded in §5, not asserted from the
specification alone.

## 1. What already exists (read before proposing anything new)

| Module | Covers | Role |
|---|---|---|
| `m05_cqc` | CQC syndication API, walked provider-by-provider for the 32 tracked providers (`SUPPLIER_NAME_VARIANTS`); locations, ratings, registered-manager contacts | Authoritative CQC evidence — `cqc_locations`, `cqc_providers` |
| `m26_cqc_directory` | Cross-checks `m05_cqc`'s output against CQC's own weekly bulk care-directory CSV and monthly ratings ODS | Completeness/currency check on the same authoritative evidence, never a second source of truth |
| `m23_sector_universe` | Reconciles `providers`, `companies` (m04), `charity_financials` (m03), `cqc_providers` (m05), `contracts` (m01) and `review_queue` leads into one universe, `provider_key` set only through a verified identifier | Provider discovery infrastructure this ticket's ask plugs into |

**This ticket does not touch any of the three.** `docs/CAVEATS.md`'s Module 5
entry ("this is not a service map… most community drug and alcohol provision
is not CQC-registered") and Module 23's entry ("the universe is a capture,
never a census") both already describe exactly the gap ORUK could help
close — a name for organisations and locations CQC registration does not
reach because they are not a regulated activity — and both already state the
discipline any new source into this universe must keep: `provider_key` is
set only through a verified identifier, never a name alone, and CQC
registration stays the authoritative regulated-activity evidence regardless
of what any directory says. Nothing here proposes to relax either rule.

## 2. What Open Referral UK actually is

Open Referral UK (ORUK) is the UK application profile of the international
**Human Services Data Specification (HSDS)**, currently at v3.0, maintained
by the (US) Open Referral initiative. ORUK is HSDS 3.0 constrained and
extended for an English local-government context: a smaller set of
recommended/required fields, and a UK-specific taxonomy vocabulary, defined
in the `OpenReferralUK/uk-profile` GitHub repository (confirmed by reading
the repository directly — `profile/`, `schema/`, `docs/`, `examples/`
directories, built on the HSDS example-profile template, itself built on
`PorismDominicSkinner/open_referral_uk_profile`). It was endorsed as a UK
government data standard by the Central Digital and Data Office's Data
Standards Authority in 2022, and its stewardship changed hands very recently
— confirmed on the Open Referral community forum, not a secondary summary of
it: MHCLG began transferring the standard to **iStandUK** (an organisation
hosted by Tameside Metropolitan Borough Council) in November 2025, with the
handover of "the key OpenReferralUK GitHub repositories, including the
validator, the UK directory of feeds and the UK website" completed
**1 April 2026** — five months before this document was written. iStandUK's
own stated near-term plan is "strengthening the technical stability of the
newly transitioned standard" before broader outreach, not expansion —
worth carrying forward as a live-governance-in-flux caveat, not a stable
platform to build against without expecting further change.

**Licensing is guidance, not a standard-wide grant.** ORUK's own developer
guidance states data "should" be published under the Open Government
Licence or an equivalent open licence, and lists what publishers should
exclude (internal-only services, archived records, sensitive locations such
as refuges, personal staff contact details) — but this is a recommendation
to publishers, not a licence this pipeline or anyone else automatically
receives by querying a feed. **There is no single ORUK licence**: each
publisher's feed carries whatever terms that publisher chose, the same
"varies by authority" shape `pipeline/licences.py`'s `authority_varies`
entry already exists to describe. This is unlike `docs/CAVEATS.md`'s other
aggregator sources (data.gov.uk, mySociety) which at least publish one
stated licence for the aggregation layer itself — ORUK's own website (CC
BY-SA 4.0) says nothing about the licence terms of the human-services data
served through it, and none of the three feeds queried for this document
stated a licence anywhere in the API responses themselves. **A licence
would need to be confirmed per council feed before any row from it is
stored**, not assumed OGL because ORUK's guidance recommends OGL.

## 3. Verified live today — the feed directory and what querying it actually shows

**The verified feed directory (`openreferraluk.org/community/directory`)
lists exactly ten feeds today**, checked live 2026-09-12, not from a cached
list:

| Publisher (as listed) | Host | Coverage described |
|---|---|---|
| Bristol Council | `bristol.openplace.directory` | Bristol & South Gloucestershire, general services |
| Buckinghamshire Council | `api.familyinfo.buckinghamshire.gov.uk` | Family information services |
| Care Quality Commission | `api.porism.com` | National — "transformed from CQC locations data" |
| Community Action Network | `dorset.localplacedirectory.org.uk` | Dorset, voluntary/community and statutory provision |
| Cumbria Council | `openreferral.localgovdrupal.org` | Cumbria, general directory |
| Hull City Council | `lgaapi.connecttosupport.org` | Hull, general services |
| North Lincolnshire Council | `northlincs.openplace.directory` | General services |
| Open Sessions | `opensessions.io` | London/national, sport and leisure |
| Pennine Lancashire ICP | `penninelancs.openplace.directory` | General services |
| Shropshire Council | `shropshire.openplace.directory` | Community directory & family information |

None of the ten is described, in the directory's own listing, as covering
substance misuse, drug or alcohol services specifically — this is a
generalist "find local services" standard, not a sector directory, exactly
as the ticket's own framing ("use a general service-directories design
rather than tying the module permanently to ORUK") anticipates. Four of the
ten (`bristol.openplace.directory`, `northlincs.openplace.directory`,
`penninelancs.openplace.directory`, `shropshire.openplace.directory`) share
one hosting pattern — `openplace.directory` — strongly suggesting one
commercial vendor operates several of these councils' feeds; `api.porism.com`
(the CQC feed) is a second, separately named product from what reads as the
same vendor family (`PorismDominicSkinner` is also the origin of the UK
profile's own base schema, per §2). This is not asserted as fact beyond what
the hostnames and repository attribution show, but it means "ten independent
implementations" is not quite the right mental model — several may share one
underlying platform's quirks, good and bad.

**Querying live feeds surfaced real, load-bearing gaps the specification
alone does not show:**

- **The CQC feed is a strictly worse copy of what `m05_cqc` already
  collects, confirmed by querying it.** `api.porism.com`'s `/services` and
  `/organizations` endpoints return only `id`, `name`, `status` and a
  minimal nested organisation reference — no address, postcode, Companies
  House number, charity number, regulated activities, rating or any other
  field `m05_cqc` already stores from CQC's own API. This is exactly the
  case the ticket names ("retaining authoritative CQC API/bulk registration
  evidence") — this feed must never be read as a second or alternative
  source for anything CQC-related; it would add nothing `m05_cqc`/`m26_cqc_directory`
  do not already hold, in a strictly poorer shape.
- **The taxonomy mechanism exists in the schema and returned nothing on the
  one feed checked.** `bristol.openplace.directory`'s `/taxonomies`
  endpoint (a live query, not a documentation read) returned `total_items:
  0`. The standard's eligibility/service-type classification machinery is
  real in the specification but this implementation has not populated it —
  a consumer cannot filter or classify by taxonomy against this feed today,
  whatever the specification promises.
- **Query parameters that look like filters are silently ignored.** A
  `search=drug` parameter against `dorset.localplacedirectory.org.uk`'s
  2,223-service directory returned the identical first page as an
  unfiltered request; an `organization_id=` parameter against
  `bristol.openplace.directory`'s 874-service directory likewise returned
  the full unfiltered set (`total_items` unchanged at 874). **A consumer
  must page through an entire council's directory and match locally** —
  the same discipline `m05_cqc`'s exact-name matching already applies to
  CQC's provider index, not a new integration pattern, but confirmed here
  as a requirement rather than an optimisation choice.
- **List responses are minimal; only the detail endpoint is rich.**
  `/services` list entries carry little beyond `id` and `name`; the full
  record — description, `service_areas`, contacts, target-audience tags,
  assurance metadata — is only on `/services/{id}`. A full pull of a
  council's directory is one list-and-paginate pass plus one detail fetch
  per service, not one bulk request — Dorset's 2,223 services would be
  2,223 detail fetches on top of 223 list pages, a materially larger
  request count per council than any single-file source this pipeline
  currently reads (compare `m29`'s one file for all 296 authorities).

## 4. Coverage — a concrete positive result, not a generalisation from it

Two of the tracked comparators — `bristol_drugs_project` and
`developing_health_independence` — are exact organisation-name matches in
`bristol.openplace.directory`'s live organisation list, confirmed by
fetching the organisation record directly rather than trusting a search
result (the org-name search having already been shown not to filter, §3):

```json
{
  "id": "44c163ee-d6c5-47d2-8e17-345a47ba5361",
  "name": "Bristol Drugs Project",
  "description": "Bristol-based charity here to help you with alcohol and
    drug problems… As part of Bristol ROADS (Recovery Orientated Alcohol
    and Drugs Service), they provide support to help adults reduce the
    harm drugs and alcohol can cause…",
  "uri": "http://www.bdp.org.uk"
}
```

A linked service record (`1625 Independent People`, a different Bristol
organisation, fetched to see the full detail shape rather than the sparse
list shape) shows what the standard actually carries once populated:

```json
{
  "service_areas": [
    {"name": "Bristol", "uri": "http://www.example.com"},
    {"name": "South Gloucestershire", "uri": "http://www.example.com"}
  ],
  "pc_targetAudience": [
    {"audienceType": "Homeless", "id": "80424"},
    {"audienceType": "Care leavers", "id": "80425"}
  ],
  "pc_metadata": {"assured_by": "oliviaplenty@thecareforum.org.uk",
                  "date_assured": "2025-09-02"},
  "maximum_age": -1, "minimum_age": -1
}
```

Three things worth carrying forward from this one record, none of them
visible from reading the specification alone:

- **`service_areas` is free-text named areas, not administrative
  geography.** "Bristol" and "South Gloucestershire" are strings, not ONS
  codes; the placeholder `"uri": "http://www.example.com"` on *both* entries
  shows this field is templated boilerplate the publisher never overrode,
  not a real per-area link — geographic coverage from ORUK would need the
  same name-to-`ons_code` resolution discipline `m05_cqc`'s
  `_build_authority_lookup` and `m27`'s `NDTMS_AREA_ALIASES` already apply
  elsewhere in this codebase, not a new problem.
- **The eligibility field the ticket asks about is not HSDS's own
  `eligibility` string field here — it is a vendor-specific
  `pc_targetAudience` extension** (`pc_` reading as this vendor's own
  prefix, consistent with the CQC feed's minimalism and the shared
  `openplace.directory` hosting noted in §3). A generic ORUK reader that
  only understood the base HSDS/ORUK schema would miss this entirely;
  reading it means reading this vendor's specific shape, undermining "one
  general reader for any ORUK feed" as a design goal — see §8.
- **There is a real human curation step behind at least this feed.**
  `pc_metadata.assured_by`/`date_assured` names a person and a date — this
  is Bristol's directory being maintained by **The Care Forum** (the
  assurer's email domain), a Bristol-based infrastructure charity, not
  Bristol Council's own staff, despite the verified-feed-directory's
  listing naming "Bristol Council" as the publisher. That distinction
  (who the feed directory credits vs. who the metadata shows actually
  curates it) is exactly the kind of thing this project's provenance
  discipline exists to keep straight, and it only surfaced by reading a
  live record rather than the directory listing.

**This is one authority, two matched providers, confirmed by direct query —
not evidence that ORUK broadly covers the sector.** Of the ten listed feeds,
only Bristol's was checked for tracked-provider content (chosen because two
tracked comparators are named "Bristol"-adjacent in `keywords.py`); the
other nine were not searched for tracked-provider names before writing this
document, and none of the ten covers an authority large enough, or is
confirmed to include drug/alcohol service content at all, to support a
claim of meaningful England-wide coverage. Ten feeds against 347 authorities
is a sparse, patchwork rollout, consistent with "50 councils on the path to
ORUK adoption" (MHCLG's own January 2025 figure) meaning on the path to
publishing a *verified* feed, not already there.

## 5. Data quality and what not to conclude from any of this

- **Absence from a directory is not absence of a service**, the same
  reading `docs/CAVEATS.md`'s Module 5 entry already gives CQC registration.
  A directory the size of Dorset's (2,223 services) not surfacing a
  substance misuse service in a ten-row sample says nothing about the other
  2,213 rows; this document did not exhaustively page any feed to check.
- **A directory's inclusion of an organisation is not confirmation the
  organisation is currently operating the described service** — the same
  discipline every candidate table in this pipeline already applies
  (`foi_request_candidates`, `unmatched_buyer_name`, `possible_group_company`):
  a name match is a lead for a person, never itself evidence.
- **Vendor-specific fields (`pc_targetAudience`, `pc_metadata`) are not
  portable across the ten feeds** without checking each one — a general
  service-directories reader (the ticket's own stated design goal) cannot
  assume every ORUK-labelled feed exposes eligibility the same way this one
  vendor's implementation does, and this document checked exactly one.
- **"Assured" is this publisher's own quality process, not this pipeline's
  verification.** `pc_metadata.date_assured` says a named person at The
  Care Forum reviewed the record on a date; it is not a claim this project
  can independently check, and does not substitute for the human review
  this project's own promotion path (`pipeline/promote.py`) requires before
  anything reaches evidence.
- **No feed queried stated a licence in its API responses.** §2's point
  stands concretely here: nothing fetched during this research carried a
  machine-readable licence field to record in `pipeline/licences.py`,
  meaning a real integration would need to find and record each target
  council's stated terms by hand, the same way `authority_varies` already
  requires for council documents.

## 6. Access and politeness

- **No authentication was required or offered** on any of the three feeds
  queried; all three answered plain unauthenticated GET requests.
- **No documented or observed rate limit.** Nothing in the ORUK developer
  documentation states one, and no `429` or `Retry-After` was seen across
  the handful of requests made while writing this document — too small a
  sample to conclude a limit does not exist, only that none was hit.
- **`robots.txt` was checked for the one host it could be fetched from**:
  `openplace.directory` returns a blanket `Disallow:` (nothing), permissive.
  `api.porism.com/robots.txt` returned `404` (no file, not a block) — the
  project's existing `PipelineHTTPClient` politeness discipline (robots.txt
  respected where present, per-host rate limiting, conditional requests,
  `CONTACT_EMAIL` in the User-Agent) applies unchanged to any of these
  hosts; nothing here needs a new access mechanism.
- **The real politeness cost is request count, not permission.** §3's
  finding that list/detail is a two-tier fetch with no working server-side
  filter means a full pull of even one mid-sized council (Dorset, 2,223
  services) is on the order of 2,400+ requests. Spread over per-host rate
  limiting and run infrequently (this data does not change fast), that is
  workable, but it is a materially heavier fetch pattern than any existing
  module's single-file or single-paginated-index sources, and multiplying
  it across even the ten currently-listed feeds is a design constraint for
  whoever scopes an implementation, not a detail.

## 7. Fit against the ticket's own ask

| Ticket asks about | HSDS/ORUK native field | Confirmed present in practice (Bristol sample) |
|---|---|---|
| Services | `service` object (name, description, status) | Yes — populated, free-text description |
| Locations | `location`/`service_at_location` objects | **Not observed** — no structured location/address/postcode/coordinates in the one detail record read; address text sat inside free-text `description` |
| Eligibility | `eligibility` (free text) | **Not the field used** — this vendor's `pc_targetAudience` tag list stood in for it |
| Service type | `taxonomies`/`taxonomy_terms` | **Empty** — zero populated terms on the one feed's taxonomy endpoint |
| Geographic coverage | `service_areas` | Present, but free-text area names with a templated placeholder URI, not administrative codes |

Three of the ticket's five named fields are either absent, vendor-specific
rather than standard, or present but not administratively resolvable in the
one real feed inspected closely. This is a fair reading of ORUK's *own*
schema capability against one live implementation of it — not a verdict on
the specification, which does define richer structures (`location`,
`taxonomies`, `eligibility`) than this particular publisher populated.
Whether the other nine feeds populate these fields more fully is unverified;
each would need the same live-query check this document gave Bristol before
any coverage claim about it is made.

## 8. Integration approach (recommended, not built)

Consistent with the ticket's instruction to use "a general service-directories
design rather than tying the module permanently to ORUK":

1. **A generic HSDS/ORUK reader, not a per-council parser** — one client
   that walks any feed's `/organizations` and `/services` (paginating fully,
   since §3 showed filters cannot be relied on), keyed by the base
   HSDS/ORUK field set only (name, description, `service_areas`, `status`).
   Vendor extensions like `pc_targetAudience` are a second, explicitly
   optional read per known vendor shape — never assumed present — so a feed
   from a different implementation degrades to "no eligibility data" rather
   than failing.
2. **Organisation-name matching reuses `m05_cqc.match_provider_name`'s
   exact-normalised-name discipline exactly**, not a new matcher: an exact
   hit is a candidate for `m23_sector_universe`/`provider_identifiers`
   review, a substring hit goes to `review_queue` exactly as CQC substring
   hits already do. **No row from this source may ever set `provider_key`
   directly** — the same rule `docs/CAVEATS.md`'s Module 23 entry already
   states for every other input to the universe.
3. **New candidate tables, not new evidence tables** — a `service_directory_candidates`
   (or similarly named) table holding what was fetched, its source feed and
   its provenance, feeding the existing human-review path
   (`pipeline/promote.py`) the same way `foi_request_candidates` does.
   Nothing here is promoted to evidence, a location, or a service-at-location
   fact without a person confirming it, per settled decision 4.
4. **Never combined with, and never overriding, CQC evidence.** §3's finding
   that the CQC-transform feed is strictly poorer than `m05_cqc`'s own data
   means a service directory module must not write to `cqc_locations` or
   `cqc_providers`, and any location or organisation match against an
   already-CQC-tracked provider is additive lead generation (e.g. a
   non-CQC-regulated service at an address CQC does not list), never a
   correction to CQC's own registration record.
5. **A per-feed licence and per-feed field-shape check is part of onboarding
   each council, not a one-time integration decision** — §2 and §5 both
   found no blanket licence or guaranteed field shape across feeds; a real
   implementation should record, per feed added, its stated licence (or the
   absence of one, flagged the way `authority_varies` already flags
   council documents) and which optional fields it actually populates,
   confirmed live rather than assumed from the specification.
6. **A candidate module number and migration number are not reserved here**
   — the next free values at time of writing are `m36`/`0116`, but JON-40's
   own feasibility document (`docs/rough-sleeping-data-framework.md`) makes
   the identical provisional claim on the same numbers for an unrelated
   source; whichever of the two tickets is implemented first takes `m36`,
   and the other moves to the next free number at that time.
7. **Geographic and service-area resolution needs the same alias/lookup
   discipline already used elsewhere** — `m05_cqc._build_authority_lookup`
   and `m27`'s `NDTMS_AREA_ALIASES` are the existing precedents for turning
   a source's free-text area name into an `ons_code`; `service_areas`'
   free-text names (§4) are the same class of problem, not a new one.

## 9. Draft acceptance criteria (for a future implementation ticket, not this one)

| Case | Expected result | Check |
|---|---|---|
| A feed's organisation name exactly matches a tracked provider variant | Written as a candidate with `match_basis = 'exact'`, queued for `m23`/`review_queue`, never auto-sets `provider_key` | New fixture-backed test, mirroring `test_m05_cqc.py`'s exact-match coverage |
| A feed's organisation name is a substring-only match | Written to `review_queue`, never accepted automatically | New test, mirroring `m05_cqc`'s substring-candidate behaviour |
| A feed's `/taxonomies` (or equivalent) returns zero terms | Module records the fact and proceeds without service-type classification, does not fail the run | New test against an empty-taxonomy fixture |
| A `service_areas` entry's name does not resolve to a known `ons_code` | Logged to `review_queue` (e.g. `service_directory_unmatched_area`), not silently dropped or guessed | New test, mirroring `cqc_locations`' `unmatched_cqc_local_authority` pattern |
| A feed states no licence anywhere in its API responses | Recorded as licence-unknown for that feed (not defaulted to OGL), surfaced for a human to resolve before any row leaves candidate status | New test asserting no implicit OGL default |
| A feed's list endpoint ignores a filter parameter this module tries | Falls back to full pagination rather than trusting a filtered count, matching §3's confirmed behaviour | New test against a fixture that ignores query params, asserting the full set is still read |
| CQC-sourced feed data (e.g. the `api.porism.com` transform) | Never written to `cqc_locations`/`cqc_providers`; if read at all, kept in its own candidate rows only | New test asserting no write path exists from this module into CQC's own tables |

## 10. Recommended next decisions (none taken here)

1. **Which feeds, if any, are worth onboarding first** — Bristol is the one
   feed this document confirmed carries genuine substance misuse content
   against two already-tracked comparators; the other nine listed feeds are
   unverified for sector-relevant content and would each need the same
   live-query check before being prioritised.
2. **Whether a vendor-specific field reader (e.g. this document's
   `pc_targetAudience` finding) is worth building for the `openplace.directory`
   family specifically**, given four of the ten current feeds share that
   hosting pattern, versus keeping strictly to the base HSDS/ORUK schema and
   accepting no eligibility data from any feed until the standard's own
   fields are populated more broadly.
3. **Whether the request-count cost of full pagination (§6) is acceptable
   for a routine recurring run**, or whether this becomes an occasional/
   manual re-run source rather than something scheduled alongside the
   pipeline's other modules.
4. **Whether "provider discovery" here should extend to authorities beyond
   where a tracked provider already operates** — the ticket names both
   "provider discovery" and "service-at-location reconciliation" for
   already-known providers; broadening to genuinely new organisations is a
   bigger, unscoped decision this document does not make.
5. **Confirm each feed's actual licence before storing anything from it** —
   no blanket answer exists (§2, §5); this is a per-feed research task for
   whoever picks up implementation, not something this document can settle
   in general.

Every item above is a candidate for a named human decision, not an
implementation queue — consistent with this issue's Not-scheduled/Post-V1
readiness label.

## Sources

* This repository: `pipeline/modules/m05_cqc.py`, `pipeline/modules/m26_cqc_directory.py`,
  `pipeline/modules/m23_sector_universe.py`, `pipeline/keywords.py`,
  `pipeline/providers.py`, `pipeline/licences.py`, `pipeline/netguard.py`,
  `pipeline/promote.py`, `docs/CAVEATS.md` (read 2026-09-12).
* `https://alphagov.github.io/data-standards-authority/standards/openreferraluk/`
  (fetched 2026-09-12) — endorsement status and licence statement.
* `https://openreferraluk.org/`, `/developers/overview`, `/developers/data-sharing`,
  `/community/directory` (all fetched 2026-09-12) — the live feed directory,
  API endpoint list, and publisher data-sharing guidance.
* `https://github.com/OpenReferralUK/uk-profile` (fetched 2026-09-12) — the UK
  application profile repository itself.
* `https://forum.openreferral.org/t/oruk-launches-under-the-stewardship-of-istanduk/799`
  (fetched 2026-09-12) — primary announcement of the November 2025 – April
  2026 MHCLG-to-iStandUK stewardship transition, used in preference to
  third-party summaries of it.
* `https://www.localdigital.gov.uk/open-referral-uk-the-journey-so-far/` and
  `https://mhclgdigital.blog.gov.uk/2024/03/06/driving-adoption-of-open-referral-uk-to-deliver-millions-in-annual-savings-for-councils`
  (fetched 2026-09-12) — MHCLG's own adoption-programme figures (50 councils
  "on the path" as of January 2025); no specific savings figure was found
  and none is repeated here as a number.
* Live queries against three of the ten listed feeds, 2026-09-12:
  `https://api.porism.com/ServiceDirectoryServiceCQC` (`/services`,
  `/organizations`), `https://dorset.localplacedirectory.org.uk/aggregator`
  (`/services`, attempted `/taxonomies`), `https://bristol.openplace.directory/o/OpenReferralService/v3`
  (`/services`, `/organizations`, `/taxonomies`, and individual
  `/services/{id}` and `/organizations` records for Bristol Drugs Project
  and 1625 Independent People) — plus `robots.txt` on `openplace.directory`
  and `api.porism.com`. The other seven listed feeds (Buckinghamshire,
  Cumbria, Hull, North Lincolnshire, Open Sessions, Pennine Lancashire,
  Shropshire) were not queried for this document.

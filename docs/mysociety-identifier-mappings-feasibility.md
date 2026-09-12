# mySociety / local-authority identifier mappings — feasibility (JON-32)

**Status: feasibility only. No code, schema or module changed.** Written
against commit `55fde50` with a clean tree, as the bounded research
deliverable for JON-32 ("Integrate mySociety local-authority identifier
mappings"), labelled `Identity` / `Post-V1` / `Not scheduled`. This document
verifies what already exists, checks the named external sources live rather
than from memory, and sets out gaps and an integration approach — not an
implementation, per the ticket's own acceptance criteria (feasibility,
access terms, provenance, integration approach, acceptance criteria, before
any build).

The ticket names two different problems and it matters not to conflate them:

1. **External identifiers *on* the authority entity** — does a WDTK body
   have a stable ID, does GOV.UK publish a council slug, does MapIt add
   anything `authorities` doesn't already have.
2. **How evidence *without* a code gets matched to an authority at all** —
   several modules receive a bare council name from their source (CQC, Find
   a Tender) and must resolve it to `ons_code` themselves, because nothing
   published one. This is the "independent module-specific name matching"
   line in the ticket, and it is a real, separate, more concrete problem
   than (1).

## Verdict up front

Most of what the ticket describes as missing is already built, and the part
that is genuinely missing is not the part the ticket's module-audit note
names.

- **Current/former councils and dated reorganisation history already
  exist**, built and tested, in `m00_geography` — `authorities.active_from`/
  `active_to` and the `authority_successors` table (§1). This is the
  headline item in the ticket's outcome list ("preserve
  reorganisation/effective-date history") and it needs no further work.
- **GOV.UK slugs, as a live concept for local authorities, do not appear to
  exist.** Checked live, not assumed (§3): local councils are not GOV.UK
  "organisations" (`/api/organisations/<slug>` 404s for one), and the GDS
  register that once assigned English local authorities a stable
  `local-authority-eng` identifier no longer resolves at all. This is not a
  gap this pipeline can close by building something; there may be nothing
  current to integrate.
- **MapIt is a commercial SocietyWorks product now**, not the free
  service the ticket's phrasing implies. Checked live (§3): the UK instance
  is £23–340/month with a 50-call/day key-less sandbox, and its only
  relevant capability — resolving other code schemes against GSS — is
  something ONS already gives this pipeline directly and more
  authoritatively. Recommend not pursuing this without an explicit paid or
  charity-rate decision, because the marginal value against what
  `authorities` already carries is low (§4).
- **WhatDoTheyKnow identifiers are partially collected already**, but
  siloed to Module 15's own table (`authority_foi_profiles.wdtk_body_slug`),
  not centralised, and mySociety's own numeric body ID (`Internal ID` in
  their CSV) is not captured at all (§2, §4).
- **The real, verified, buildable finding is problem (2) above**: two
  modules (`m01_procurement`, `m05_cqc`) each maintain their own
  `_normalise_authority_name`, and they disagree in a way that is a
  live, demonstrated defect, not a hypothetical one — see §5. This is
  the concrete case for centralising something, and it is a smaller, cheaper
  fix than a new identifier schema.

## 1. What already exists (read before proposing anything new)

| Piece | State | Where |
|---|---|---|
| `authorities` — GSS/ONS code as the verified natural key for every current and former English upper-tier authority + non-metropolitan district | Built, tested | `pipeline/modules/m00_geography.py`, `authorities` table (migration `0002`) |
| Retired-code tracking (`active_from`/`active_to`, `first_seen_vintage`/`last_seen_vintage`) | Built, tested | `m00_geography.py::run`, `authorities` |
| Local government reorganisation edges, resolved by measured geometric overlap, never guessed from names | Built, tested | `m00_geography.py::_resolve_successors`, `authority_successors` table |
| Unresolved reorganisation gaps surfaced, not silently dropped | Built | `review_queue` item type `unresolved_successor` |
| mySociety authority register → GSS join, WDTK body slug/URL, home page, publication scheme, disclosure log URL | Built, tested | `pipeline/modules/m15_foi.py::parse_authorities_csv`, `authority_foi_profiles` table (migration `0019`) |
| GSS-code extraction from mySociety's own tag string (`gss:`, `statistical_geography:`, `lad##cd_code:`) | Built, tested | `m15_foi.py::extract_gss_code` |
| First authoritative authority website URL source (used as a fallback by Modules 9 and 10) | Built | `pipeline/authority_websites.py` docstring; `AuthorityWebsite.source == "foi_profile"` |
| Per-provider external identifier model, with verified/unverified status and provenance-free config seeding | Built, tested — the closest existing precedent for what "centralise external identifiers" could mean for authorities | `providers.py`, `provider_identifiers` table (migration `0005`) |
| CKAN organisation-slug matching for data.gov.uk, done live by name every run, not persisted | Built | `m19_data_gov_uk.py::_normalise_org_name`, `_search` (org pass) |
| Authority-name → `ons_code` matching, duplicated across two modules | Built, **diverges between the two copies** | `m01_procurement.py::_normalise_authority_name`/`_build_authority_lookup`; `m05_cqc.py::_normalise_authority_name`/`_build_authority_lookup` (§5) |
| Authority-name matching reused correctly (no third copy) | Built | `m23_sector_universe.py` imports `_build_authority_lookup`/`_match_buyer` from `m01_procurement` rather than redefining them |
| Fingertips/PHE area codes joined directly as ONS codes, no separate scheme to reconcile | Built, no gap found | `m12_fingertips.py::_known_ons_codes` |

There is no separate "old identifier module" to compare against — `m00` is
already the geography spine the ticket asks to extend, and it already does
most of what the outcome list names.

## 2. What mySociety's authority CSV actually contains, versus what is stored

Confirmed against the fixture header used in `tests/test_m15_foi.py` (not
re-derived from memory): the CSV's columns are `Internal ID, Name, Short
name, URL name, Tags, Home page, Publication scheme, Disclosure log`.
`parse_authorities_csv` (`m15_foi.py:136`) currently keeps `Name`, `URL name`
(as `wdtk_body_slug`), `Home page`, `Publication scheme` and `Disclosure
log`, plus the GSS code extracted from `Tags`. **`Internal ID` — mySociety's
own numeric body ID, used by their `/api/v2/body/<id>` endpoint — is read by
nobody and stored nowhere.** This is a one-line, low-risk addition if a
future ticket ever needs to call the numbered API rather than construct a
slug URL; nothing today does, so this document flags it rather than
recommending it be added now.

`Short name` is also discarded; nothing found in this repository needs it.

## 3. Source and access terms (verified 2026-09-12)

Verified live against the actual pages, in the same spirit as
`docs/m15-alaveteli-feed-feasibility.md`'s discipline of checking source code
and live responses rather than a secondary description, because the ticket
itself flags identifier claims as needing verification.

**GOV.UK.**

- `https://www.gov.uk/api/organisations/kent-county-council` returns HTTP
  404. GOV.UK's organisations API is a registry of central government
  departments and agencies; English local councils are not members of it,
  and there is no equivalent per-council content-API record with a stable
  slug found in this research.
- The old GDS Registers service (`registers.service.gov.uk`), which once
  ran a `local-authority-eng` register assigning English local authorities a
  short code, no longer resolves at all — `getaddrinfo ENOTFOUND
  www.registers.service.gov.uk` on a live fetch 2026-09-12. A GitHub search
  of the `alphagov` organisation for a `local-authority-eng`-named
  repository returned no matches. This is consistent with GDS's own
  well-documented retirement of the Registers programme; nothing here
  suggests an archived copy exists at a URL this research found.
- **Conclusion: whatever the ticket's "GOV.UK slugs" line was referring to
  does not appear to have a live, current equivalent.** The one GOV.UK
  identifier this pipeline already touches — data.gov.uk/CKAN organisation
  names (`m19_data_gov_uk.py`) — is matched live by normalised name every
  run and never stored; see §4 on why persisting it would not currently pay
  for itself.

**MapIt** (`mapit.mysociety.org`, operated by SocietyWorks Ltd, a mySociety
trading subsidiary), checked live 2026-09-12 against its own marketing,
docs and pricing pages:

- **It is a commercial product, not a free API.** Pricing: a key-less
  "Sandbox" tier capped at 50 calls/day; "Village" at £23/month (10,000
  calls/month, free for registered charities); "Town" at £113/month; and
  "Metropolis" at £340/month (unlimited, half-price for charities). All
  tiers are additionally rate-limited to "an average of 1 call per second."
  This pipeline is a trade union pay-campaign project, not itself a
  registered charity, so which tier (if any) it could use for free is a
  named human decision, not a default — see §7.
- **What it actually does**: point-to-boundary lookups (postcode, lat/lon,
  OS grid reference → administrative area) and an area registry keyed by an
  internal MapIt area ID, with a `/code/<type>/<code>` endpoint that
  resolves GSS IDs (among other schemes) to that internal ID.
- **Nothing in this pipeline does a postcode-to-authority lookup today** —
  checked, no module references "postcode" in that way. MapIt's core
  function is therefore not something anything here currently needs.
- **Its only relevant feature for this ticket — resolving other codes
  against GSS — is something ONS's own Open Geography Portal already gives
  this pipeline first-hand** (`m00_geography.py` fetches GSS codes directly
  from the source ONS itself publishes, not a mySociety mirror of it).
  Routing through a paid, rate-limited, third-party mirror to get an
  identifier this pipeline already has authoritatively would be a net loss
  of provenance quality, not a gain.
- A separate free instance, `global.mapit.mysociety.org`, exists but is
  scoped to OpenStreetMap-derived boundaries under CC-BY-SA-2.0/ODbL, is
  also restricted to charities/unpaid non-profit workers (50,000 calls/year)
  for commercial use beyond that, and is not the UK-specific service the
  ticket's "MapIt" line means.
- No robots.txt or crawling question arises here — access is entirely
  gated by the API-key/pricing model above, not by politeness rules.

**WhatDoTheyKnow.** No new research needed — `docs/mysociety-access-request.md`
already covers licensing (CC BY-SA for mySociety's own data, generally OGL
v3.0 for authority responses) and the live compliance question (the
`/feed/search/` robots.txt exception, tracked separately in JON-89, most
recently deferred to 2026-10-12 per `docs/m15-alaveteli-feed-feasibility.md`).
Nothing in this document changes that position or depends on its outcome:
the authority CSV (`/body/all-authorities.csv`) this ticket cares about is
the one WDTK route that returns 200 with no robots.txt conflict and is
already collected.

## 4. Gaps against the ticket's ask, and what closing each would (or would not) need

**Current/former councils, dated reorganisation history — no gap.** Already
built exactly as described (§1). Nothing to do.

**GSS/ONS codes — no gap.** Already the authoritative natural key, sourced
directly from ONS, never inferred (§1). Nothing to do.

**GOV.UK slugs — not buildable against anything live found (§3).** If a
later ticket identifies a specific GOV.UK-published identifier this
research missed, that would need to be named explicitly and re-verified
before treating it as real; this document did not find one.

**WhatDoTheyKnow body identifiers — a real but small gap.** `wdtk_body_slug`
already exists but only in `authority_foi_profiles`, scoped to Module 15;
`Internal ID` (mySociety's numeric body ID) is discarded entirely (§2).
Closing this fully would mean either (a) a generic `authority_identifiers`
table alongside `authorities` — note this cannot simply copy
`provider_identifiers`'s shape, because that table is deliberately
provenance-free (config-seeded, per its own migration comment), whereas
WDTK data is fetched evidence with a real `source_url`/`retrieved_at`/
`payload_sha256` that must not be dropped — or (b) leaving it where it is,
since nothing outside Module 15 currently needs `wdtk_body_slug`, and no
module needs the numeric ID at all today. Recommend (b) until a second
consumer actually needs it: building a general identifiers table for a
single producer and zero consumers is exactly the premature abstraction
`CLAUDE.md`'s house style asks not to build.

**MapIt IDs — not worth pursuing as currently priced (§3).** No further
engineering gap to close; the open question is a cost/access decision, not
a technical one.

**"Other council IDs" — none identified as in-scope today.** Two other
schemes exist in UK local-government data generally — DfE/Ofsted's 3-digit
numeric LA code (children's-services data) and NHS ODS codes — but nothing
in this pipeline currently ingests a source keyed by either: Fingertips
(`m12`) already returns ONS/GSS codes directly (verified against
`m12_fingertips.py::_known_ons_codes`), and no module here touches
children's-services data. Flagged for awareness, not recommended for
speculative schema work.

**Independent module-specific name matching — the real, verified gap
(§5).** This is where the actual, demonstrable problem is, and it is
cheaper to fix than any of the identifier-schema questions above.

## 5. The verified defect: two authority-name normalisers, both wrong on comma-suffix names

`m01_procurement.py` and `m05_cqc.py` each define their own
`_normalise_authority_name` and `_build_authority_lookup(conn)`, independently,
to resolve a bare council name (from Find a Tender / OCDS buyer names, and
from CQC's `localAuthority` field) against `authorities.ons_code`. A third
module, `m23_sector_universe.py`, does the right thing and imports m01's
versions rather than writing a third copy — proof this pattern is already
recognised as reusable in one place, just not applied consistently.

The two independent copies disagree, and both are wrong against real ONS
authority names, confirmed by running both functions directly (not
inferred) against the three English authorities whose ONS name uses a
comma-suffix form (`authorities.name`, cross-checked against
`pipeline/authority_websites.py`'s `AuthorityWebsite.name` entries for the
same three):

| Input | `m01_procurement._normalise_authority_name` | `m05_cqc._normalise_authority_name` |
|---|---|---|
| `"Bristol, City of"` | `"bristol"` (correct) | `"bristol city of"` (**wrong** — leaves `"city of"` in) |
| `"Herefordshire, County of"` | `"herefordshire county of"` (**wrong** — `"county of"` isn't in its strip list either) | `"herefordshire county of"` (**wrong**, same reason) |
| `"Kingston upon Hull, City of"` | `"kingston upon hull"` (correct) | `"kingston upon hull city of"` (**wrong**) |

Against the plain forms a source is likely to actually send (`"Bristol"`,
`"Herefordshire"`, `"Kingston upon Hull"`), both functions normalise to the
bare name — so **all three authorities fail to join** whenever CQC's
`localAuthority` field (or an FTS buyer name) uses the plain form and the
lookup key was built from `authorities.name`'s comma-suffix form. This is
not a silent wrong join — `m05_cqc.py::_store_location` already falls back
to `NULL` plus a `review_queue` item (`unmatched_cqc_local_authority`) when
the lookup misses, which is the correct discipline per `docs/CAVEATS.md`'s
first rule. The cost is not incorrectness; it is avoidable review-queue
noise, recurring on every run, for three specific, known, nameable
authorities, caused by two independently-maintained regexes that neither
covers a case the other partially does.

This is the concrete version of the ticket's "rather than independent
module-specific name matching" line, and it is a small, well-scoped fix: one
shared function, one test fixture covering exactly these three names, used
by both call sites.

## 6. Provenance requirements

No new provenance model is needed for anything recommended here. `m00`'s
`authorities` and `authority_successors` already carry
`source_url`/`retrieved_at`/`http_status`/`source_system`/`payload_sha256`
for every row, sourced directly from ONS. `authority_foi_profiles` does the
same for the mySociety CSV fields it already stores. A consolidated
`normalise_authority_name()` (§7) carries no provenance of its own — it is
matching logic over already-provenanced data, the same category as
`m19_data_gov_uk.py::_normalise_org_name`, not a new evidence source.

## 7. Integration approach (recommended, not built)

1. **Consolidate authority-name normalisation into one shared function**,
   e.g. `pipeline/authority_names.py::normalise_authority_name()` and
   `build_authority_lookup(conn)`, fixing the comma-suffix gap found in §5
   (strip `"city of"` **and** `"county of"` as trailing suffixes, not just
   the mid-string forms each copy currently handles inconsistently) once,
   tested once. `m01_procurement.py` and `m05_cqc.py` both switch to import
   it; `m23_sector_universe.py`'s existing import of m01's version moves to
   the new shared module instead of m01. This is the one item from this
   document worth a bounded implementation ticket on its own — it is a
   pure refactor plus a bug fix, touches no schema, and removes a proven
   defect.
2. **Do not build a generic `authority_identifiers` table now.** §4
   concluded there is exactly one producer (`wdtk_body_slug` in Module 15)
   and zero consumers outside it; revisit only if a second module needs an
   authority-scoped external identifier `authority_foi_profiles` doesn't
   already carry.
3. **Do not pursue MapIt** without an explicit decision from Jon on whether
   the charity-rate "Village" tier is available to this project and whether
   the £23–340/month cost is worth an identifier scheme ONS already
   provides more authoritatively for free (§3–§4).
4. **Do not build against a "GOV.UK slug"** until a specific, currently-live
   GOV.UK-published identifier is named — this research did not find one
   (§3).
5. **Optional, very small**: capture mySociety's `Internal ID` alongside
   the existing `wdtk_body_slug`/`wdtk_body_url` columns in
   `authority_foi_profiles`, at essentially zero cost the next time that
   table's parser is touched for another reason — not worth a ticket of its
   own.

## 8. Draft acceptance criteria (for a future implementation ticket covering item 1 only)

| Case | Expected result | Check |
|---|---|---|
| `"Bristol, City of"`, `"Herefordshire, County of"`, `"Kingston upon Hull, City of"` normalised by the shared function | All three reduce to the same key as their plain form (`"bristol"`, `"herefordshire"`, `"kingston upon hull"`) | New fixture test, the three names from §5 |
| CQC `localAuthority: "Bristol"` (or `"Herefordshire"`, `"Kingston upon Hull"`) against a lookup built from `authorities.name` | Resolves to the correct `ons_code`, no `unmatched_cqc_local_authority` review item | Updated `test_m05_cqc.py` fixture case |
| Every existing passing case in `test_m01_procurement.py` and `test_m05_cqc.py` for buyer/authority matching | Unchanged behaviour — the shared function is a superset fix, not a behaviour change for names that already matched | Existing test suites, re-run unmodified |
| `m23_sector_universe.py` | Still imports one authority-lookup implementation, now from the shared module, not from `m01_procurement` | Import-path assertion or a straightforward code read at review |

## 9. Open questions requiring a human decision

1. **Whether item 1 (§7) is worth its own bounded ticket now**, given it is
   a small, well-understood fix with a demonstrated defect behind it, versus
   staying `Post-V1`/`Not scheduled` like the rest of this ticket's scope.
2. **Whether mySociety's `Internal ID` (§2, §7.5) is worth capturing** now,
   speculatively, or only when a real second consumer appears.
3. **Whether MapIt's charity-rate tier is something Jon wants to pursue**
   at all, given §3–§4's conclusion that its only relevant capability
   duplicates what ONS already provides for free and more authoritatively.
4. **Whether any GOV.UK-published local-authority identifier this research
   missed should be named explicitly** for re-verification, rather than
   treating §3's negative result as final.

## Sources

* This repository: `pipeline/modules/m00_geography.py`,
  `pipeline/modules/m15_foi.py`, `pipeline/modules/m01_procurement.py`,
  `pipeline/modules/m05_cqc.py`, `pipeline/modules/m23_sector_universe.py`,
  `pipeline/modules/m19_data_gov_uk.py`, `pipeline/modules/m12_fingertips.py`,
  `pipeline/authority_websites.py`, `pipeline/providers.py`,
  `pipeline/migrations/postgres/0002_geography.sql`,
  `pipeline/migrations/postgres/0005_providers.sql`,
  `pipeline/migrations/postgres/0019_foi.sql`, `docs/CAVEATS.md`,
  `docs/SOURCES.md`, `docs/mysociety-access-request.md`,
  `docs/m15-alaveteli-feed-feasibility.md`, `tests/test_m15_foi.py` (read
  2026-09-12); the two normalisation functions in §5 were executed directly
  against the three named authority names via `uv run python`, not inferred
  from reading the regexes.
* `https://mapit.mysociety.org/`, `/docs/`, `/pricing/` (fetched
  2026-09-12) — the primary source for MapIt's current commercial terms.
* `https://global.mapit.mysociety.org/` (fetched 2026-09-12) — the separate
  free/OSM-derived instance and its licensing.
* `https://www.gov.uk/api/organisations/kent-county-council` (fetched
  2026-09-12) — returned 404, the basis for §3's GOV.UK-organisations
  finding.
* `https://www.registers.service.gov.uk/registers/local-authority-eng`
  (fetch attempted 2026-09-12) — DNS resolution failure, the basis for §3's
  finding that the GDS local-authority register no longer exists live.
* GitHub search of the `alphagov` organisation for `local-authority-eng`
  (2026-09-12) — no matching repository found.

# Kingfisher / OCDS procurement lifecycle architecture — feasibility (JON-28)

**Status: feasibility and integration design complete. No production code, schema,
collector enablement or evidence promotion is authorised by this document.**
Written 2026-09-13 against beta commit 5fece46ae1d63fef596e5e35f49fb2384f8198d3. This is the bounded
research deliverable for JON-28: verify current capabilities, coverage,
licensing and provenance before implementation.

## Verdict up front

Open Contracting Partnership (OCP) Data Registry and the OpenTender UK
publication are technically useful to SectorTrace, but only as a separately
attributed mirror/cross-check layer.

**Recommend:** a Post-V1, operator-controlled historical gap and reconciliation
import using the OCP Data Registry's OpenTender UK bulk packages.

**Do not recommend:** replacing Find a Tender or Contracts Finder, treating
OpenTender as a primary source, merging mirror observations into the canonical
contracts rows merely because fields look similar, or calculating a headline
contract total from the result.

The highest-value use is the period before SectorTrace's direct procurement
coverage: OpenTender claims UK coverage from January 2006, while the current
m01_procurement design begins its direct channels later. That claim is useful
as a lead for a measured backfill, not as proof that every UK procurement event
is present.

## 1. What the two Kingfisher components do

Kingfisher is a family of OCP tools, not one replacement database.

| Component | Verified capability | SectorTrace relevance |
|---|---|---|
| Kingfisher Collect | Scrapy-based spiders download OCDS data, write each source file to disk as a release or record package, and can send it to Kingfisher Process | A mature source-collection pattern; do not import its crawler runtime into V1 |
| Kingfisher Process | Accepts OCDS through a web API or local load, stores data in PostgreSQL collections, runs optional schema checks and pre-processing, and can compile releases | A useful architectural comparison for immutable source collections and derived views |
| OCP Data Registry | Catalogues datasets, documents source/coverage/quality information, and provides bulk JSON, Excel and CSV downloads; it currently advertises more than 100 publishers | The practical access point for an isolated mirror observation import |
| OpenTender UK | A transformed publication combining TED data with national procurement portals, including Contracts Finder | A derivative view that must remain distinct from the underlying UK publisher channels |

Sources: [Kingfisher Collect documentation](https://kingfisher-collect.readthedocs.io/en/latest/), [Kingfisher Process documentation](https://kingfisher-process.readthedocs.io/en/v1/), [Kingfisher Process source](https://github.com/open-contracting/kingfisher-process), [OCP Data Registry](https://data.open-contracting.org/).

## 2. OCDS lifecycle semantics and the important loss in OpenTender

OCDS separates a contracting process from the publications that update it:

- A release is a point-in-time update and contains an OCID.
- Releases are immutable and form a change history.
- A record indexes the releases for one contracting process.
- A compiled release contains the latest value of each field.
- A versioned release retains field-level change history.

Kingfisher Process models these concepts with source collections, collection
files/items, raw data and package data, release/record/compiled-release tables,
and schema-check results. A collection also records source ID, run timestamp,
sample status, transform lineage and processing state. Duplicate package data
can be de-duplicated by content hash while collection lineage remains available.

The OpenTender UK registry page explicitly says its downloadable rows represent
compiled releases: one latest-value snapshot per contracting process. It is
therefore not equivalent to importing the original release stream, records or
full change history. A mirror row can be used to identify a possible missing or
conflicting observation; it cannot silently become a historical lifecycle
release in SectorTrace.

SectorTrace should preserve this distinction:

1. Direct Find a Tender and Contracts Finder bytes remain the primary evidence.
2. OpenTender observations remain mirror observations with their own source,
   OCID prefix, retrieval metadata and licence.
3. A candidate match between the two layers is a review finding, not an
   automatic merge.
4. A compiled mirror value is never used to manufacture an award, contract,
   payment, amendment or implementation event absent from the primary source.

References: [OCDS releases and records](https://standard.open-contracting.org/latest/en/primer/releases_and_records/),
[Kingfisher Process database structure](https://kingfisher-process.readthedocs.io/en/v1/database-structure.html).

## 3. OpenTender UK coverage and completeness finding

The current OCP Data Registry entry for **United Kingdom: OpenTender** reports:

| Property | Registry claim |
|---|---|
| Date range | January 2006 – January 2025 |
| Update frequency | Every six months |
| Last retrieved | 27 June 2026 |
| Formats | JSON, Excel and CSV |
| OCID prefix | ocds-70d2nz |
| JSON all-time package | 386 MB compressed JSONL |
| CSV all-time package | 545 MB compressed archive |
| Licence shown | CC BY-NC-SA 4.0 |
| Sources described | TED plus national procurement portals, with Contracts Finder supplementing lower-value coverage |

The range claim is real as a registry metadata claim, but it does not mean
complete England-wide procurement coverage:

- OpenTender's TED component is threshold-bound.
- The Contracts Finder supplement has its own publication and field limits.
- The current page reports no planning records, contracts, contract items,
  transactions, milestones or amendments for this publication.
- It reports 660,914 tenders, 663,937 awards and 2,217,711 documents, but
  these are counts of compiled-release objects, not a count of all notices or
  all stages.
- The registry page says no data-quality summary has yet been prepared for
  this publication.
- The period ends January 2025 despite the page being retrieved in June 2026,
  so it is not an ongoing replacement for the direct live channels.

This means the correct SectorTrace assertion is:

> The Registry advertises an OpenTender UK dataset spanning January 2006 to
> January 2025. Actual completeness, continuity and field availability must be
> measured from the downloaded package and its manifest; the date range alone
> is not evidence of complete procurement coverage.

The UK history to 2006 is consequently a credible backfill lead and a verified
published claim, not a completeness guarantee.

Source: [United Kingdom: OpenTender — OCP Data Registry](https://data.open-contracting.org/en/publication/92).

## 4. Comparison with the current m01 procurement collector

The beta m01_procurement module currently keeps its direct channels separate:

- Find a Tender is the direct source for the FTS OCDS release package. The
  module uses its live API and retains the API response provenance.
- Contracts Finder is collected through its live API for the relevant window.
- Contracts Finder's own historical CSV archive is a separate channel and is
  not conflated with the live API.
- The optional Kaggle re-host is already treated as a cross-check only and
  writes sightings/review findings rather than primary contracts evidence.
- Channel sightings preserve source_system, notice ID, OCID, buyer/title/CPV
  summary, values, dates, source URL, retrieval time and payload hash.

That architecture is already the right foundation. OpenTender should be added
as another explicitly named mirror channel, not as a fourth writer into the
canonical contracts table.

| Question | Direct channels | OpenTender Registry |
|---|---|---|
| Authority | Original UK publisher systems | Transformed OCP/OpenTender publication |
| Lifecycle | Release/package history where published | Compiled/latest-value snapshot |
| Coverage | Current source-specific windows and thresholds | Advertised Jan 2006–Jan 2025, subject to source limits |
| OCID namespace | FTS/Contracts Finder prefixes | ocds-70d2nz |
| Licence | OGL v3.0 for the current FTS/Contracts Finder Registry entries | CC BY-NC-SA 4.0 shown for OpenTender UK |
| Best use | Primary evidence | Gap discovery, reconciliation and historical lead generation |
| Promotion | Eligible subject to existing source rules | Blocked until mirror licensing/provenance review is satisfied |

The Registry's separate entries are also informative: the current FTS entry
reports real-time coverage from January 2021 and OGL v3.0, while its Contracts
Finder entry reports real-time coverage from November 2016 and OGL v3.0. Those
publisher entries should remain authoritative for their respective channels.
Sources: [FTS Registry entry](https://data.open-contracting.org/en/publication/41),
[Contracts Finder Registry entry](https://data.open-contracting.org/en/publication/128).

## 5. Reconciliation design

Matching must be conservative because an OCID is not enough when separate
publishers or transformations use different namespaces. The Registry's own
FTS quality notes warn that some tenders and awards from the same process are
published under different OCIDs.

Use the following matching order:

1. Exact source-system plus native notice ID: retain as the direct identity.
2. Exact OCID: retain the source-specific observation; do not overwrite the
   other source's row.
3. Candidate comparison on buyer/authority, normalized title, publication date
   within a documented tolerance, CPV set and value/currency.
4. Only a high-confidence candidate may produce a review suggestion.
5. Ambiguous, conflicting or one-sided candidates remain separate and enter
   review; they are not deduplicated automatically.

A reconciliation report should distinguish at least:

- direct match;
- mirror-only observation;
- direct-only observation;
- candidate match needing review;
- same-process candidate with conflicting OCIDs;
- field disagreement;
- malformed or incomplete mirror row;
- licence or provenance blocked.

The report may identify coverage gaps and source disagreement. It must not infer
that a direct-only row is absent from the world, nor that a mirror-only row is
true merely because OpenTender contains it.

## 6. Licence, access and provenance disposition

The OpenTender UK entry displays CC BY-NC-SA 4.0. This is materially different
from the OGL v3.0 shown for the direct FTS and Contracts Finder publications.

Before any public export or database promotion, SectorTrace needs a human
licensing decision covering:

- non-commercial use by the campaign and public portal;
- attribution and link-back wording;
- ShareAlike obligations for any adapted or combined dataset;
- whether storing a transformed observation in the warehouse is permitted;
- whether the public portal, downloadable exports and repository are each
  compatible with those terms;
- rights in the underlying TED and Contracts Finder material as transformed by
  OpenTender.

Until that decision is recorded, the safe disposition is an operator-only
mirror/cross-check observation or an offline feasibility fixture. It must not
silently inherit the direct channels' OGL disposition.

Every retrieved package would need a separate provenance manifest containing:

- Registry publication URL and OpenTender source URL;
- exact download URL and retrieval timestamp;
- HTTP status, content type and byte count;
- SHA-256 of the compressed bytes;
- package format and parser version;
- advertised date range, source OCID prefix and licence text;
- extraction run ID and any transformation/normalisation performed;
- whether the observation is primary, mirror, candidate or review-only;
- the licensing decision and public-export disposition.

Keep raw bytes and derived rows separate. A changed registry package must create a
new retrieval identity and reconciliation run, never rewrite an earlier
observation.

## 7. Recommended implementation boundary

### Phase A — offline preparation

Create a small, licence-cleared fixture from the Registry package or an
approved sample. Verify:

- one JSONL line is a compiled release;
- the OCID prefix is retained;
- empty and malformed rows are classified explicitly;
- values, dates, parties, documents and extensions map without guessing;
- package metadata and hashes are captured.

No live-source request belongs in the test suite.

### Phase B — operator-only cross-check

Reuse the existing procurement channel-sighting pattern if its columns are
sufficient. If not, add a separate mirror-observation table rather than
overloading contracts. Run a bounded, explicit source command that:

- downloads a selected annual or all-time package;
- archives the exact bytes;
- records a collection attempt and parser version;
- computes yearly/authority/CPV presence summaries;
- generates review candidates for gaps and disagreements;
- cannot write public contracts rows or promote evidence.

### Phase C — human decision

Review the first report for sample coverage, false matches, source gaps and
licensing. Only after approval should a future issue define whether any narrow
historical backfill is permitted. Direct primary rows remain unchanged.

### Explicitly out of scope

- replacing FTS or Contracts Finder;
- importing Kingfisher Process or running a second PostgreSQL warehouse;
- reconstructing release histories from compiled OpenTender rows;
- merging on title/value alone;
- automatic promotion or deletion;
- headline totals or arithmetic across notices, awards, contracts and payments;
- changing current V1 source contracts or live collection cadence.

## 8. Future implementation acceptance criteria

A follow-up implementation issue should not be accepted unless all of these are
true:

- OpenTender observations have a distinct source-system identity, OCID prefix,
  provenance manifest and licence disposition.
- Direct FTS/Contracts Finder records are never overwritten, merged or
  re-attributed to OpenTender.
- The claimed January 2006–January 2025 range is checked from downloaded
  package contents, per-year counts and a retained manifest.
- The report distinguishes source coverage from completeness and calls out the
  current January 2025 freshness boundary.
- Reconciliation uses documented candidate fields and routes ambiguous matches
  to human review.
- Different OCIDs for a likely process remain visible and separately
  attributable.
- Fixtures cover mirror-only, direct-only, exact match, different-OCID,
  conflicting-value, malformed, missing-field and duplicate cases.
- Invalid/partial downloads cannot appear as successful empty coverage.
- Public exports and portal responses exclude mirror data while its licence or
  promotion disposition is unresolved.
- No calculation combines headline contract values across evidence layers.
- Collection is polite, bounded and opt-in; CI and tests do not contact live
  Registry, OpenTender, FTS or Contracts Finder endpoints.

## Decision

JON-28 is complete as a feasibility deliverable.

**Decision:** pursue a Post-V1 OpenTender/OCP Registry historical gap and
reconciliation capability, subject to a recorded licensing decision and an
offline fixture-first implementation. Keep direct Find a Tender and Contracts
Finder as primary evidence; keep mirror observations separate; preserve
release/record semantics; and do not publish headline contract totals.

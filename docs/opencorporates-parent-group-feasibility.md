# OpenCorporates parent and group discovery — feasibility (JON-31)

**Status: research only.** No code, migration or module changed. Written
against commit `55fde50` with a clean tree, as the bounded assignment for
JON-31 ("Explore OpenCorporates parent and group discovery"), whose readiness
label (Not scheduled / Post-V1) requires a named human decision before any
implementation. This document is that decision material: feasibility, access
terms, provenance, integration approach and acceptance criteria, per the
ticket's own ask — not an implementation.

JON-31 also carries a module-audit note asking this pass to verify a specific
claim against current source terms and repository state: *"m04/m23:
OpenCorporates international/group reconciliation with field-level provenance
where available. Companies House remains authoritative; streaming discovery
belongs to a separate transport task."* §1–§2 verify the OpenCorporates side
of that claim against the vendor's own current terms and documentation; §0
verifies the repository side against the code as it stands today. The claim
holds, with one correction: OpenCorporates' provenance is coarser than
"field-level" in the sense this pipeline uses that phrase, and §3 says why
that matters before anyone builds against it.

## 0. What already exists (read before proposing anything new)

| Component | Covers | Key caveat already in `docs/CAVEATS.md` |
|---|---|---|
| `m04_companies` (`pipeline/modules/m04_companies.py`) | Companies House: company profile, officers, filings, insolvency, PSC (People with Significant Control), disqualified-director sweep — for UK-registered entities only, seeded from `provider_identifiers` or an exact-name search | `match_basis = 'name_only_unconfirmed'` is not identity; PSC rows are ownership edges, never provider links, on a name |
| `company_psc` / `restricted_company_psc` (migration `0038`) | PSC entries per company, including **corporate** PSCs carrying `identification_company_number` and `identification_country_registered` as published by Companies House | "whether it belongs to a provider's group is the entity graph's question (F1)" — i.e. explicitly deferred, not answered |
| `m23_sector_universe` (`pipeline/modules/m23_sector_universe.py`) | Reconciles providers, companies, charities, CQC providers, contract awardees and unmatched buyers into one population, by verified identifier only — fetches nothing itself | "provider_key is set only through an identifier that a source published... never through a name" |
| `review_queue` items `unconfirmed_name_match`, `possible_group_company` | Companies House name-search misses, captured as unresolved leads, not accepted matches | m23 captures these systematically; capture is not resolution |

Two things follow directly from reading the code rather than the ticket's own
paraphrase of it:

1. **Companies House is already the sole entity-identity source in this
   pipeline, and nothing here proposes changing that for UK entities.**
   `m04` fetches company profile, PSC, filings, insolvency and officers
   directly from the register with per-row `source_url` / `retrieved_at` /
   `payload_sha256` provenance (settled decision #1). Re-fetching the same UK
   facts through OpenCorporates, which itself sources UK data *from*
   Companies House, would add a second, less-provenanced copy of data this
   pipeline already holds first-hand. **Companies House remaining
   authoritative for UK entities is correct and is not a decision this
   document reopens.**

2. **`company_psc` already stores the one fact that makes "group discovery"
   concrete: a corporate PSC's own company number and country of
   registration, as Companies House itself asserts them.** Where that
   country is not the UK — the ownership-chain case a substance-misuse
   provider's private-equity or holding-company structure would actually
   produce — Companies House has no page to fetch for that entity at all: it
   is a foreign register's record, referenced by number, never resolved.
   Nothing in the current pipeline attempts to resolve it. That is the
   genuine, scoped gap this document assesses, not a general-purpose company
   lookup.

## 1. What OpenCorporates actually is, and its licence

OpenCorporates is a UK-based company (originally a CIC) operating a database
of 300+ jurisdictions' official company-register filings — not a register in
its own right, but an aggregator over other jurisdictions' registers,
comparable in role to what Fingertips is to NHS/ONS/DfE source statistics
(`docs/ohid-ndtms-contextual-indicators.md` §1) rather than to Companies
House.

**Licence.** The database is published under the **Open Database Licence
(ODbL)**: OpenCorporates "do not claim any rights over the information"
itself, only over their compiled database. Any reuse must carry attribution
— a hyperlink reading "from OpenCorporates" to the homepage or the specific
record page, sized no smaller than 70% of the largest font used for the
information it accompanies — and, critically, **share-alike**: "if you
combine the information with your own data, the resultant information must
be published under the Attribution Share-Alike ODbL," unless a paid
non-share-alike licence is bought instead.
Source: [OpenCorporates terms of use](https://opencorporates.com/terms-of-use-2/).

**API access and cost.** There is no free general-purpose API tier. Published
annual plans (checked at time of writing; verify before committing budget) run
Essentials £2,250/yr (500 calls/month, 200/day), Starter £6,600/yr
(2,500/month), Basic £12,000/yr (5,000/month), with bespoke Enterprise pricing
above that. Source:
[opencorporates.com/pricing](https://opencorporates.com/pricing/). Separately,
OpenCorporates states it offers **free at-scale API access to investigative
journalists, NGOs, universities and anti-corruption research groups** with "a
project or initiative to improve the use, quality and understanding of
legal-entity data," by direct application — not a self-serve tier, and
eligibility for a trade-union pay-campaign evidence project (as opposed to an
anti-corruption one) is **not established by anything read in this pass**; it
would need an actual application to know. Source: [OpenCorporates enterprise
API terms of
service](https://opencorporates.com/legal-information/enterprise-api-terms-of-service/).
Both figures come from the vendor's own current pages, not third-party
resellers, but pricing pages change — re-check before any purchase decision.

**Endpoints relevant here.** The standard company endpoint
(`/companies/:jurisdiction_code/:company_number`) natively carries
`controlling_entity`, `ultimate_controlling_company`,
`ultimate_beneficial_owners` and `home_company` fields — populated only where
the underlying national register itself publishes that fact, which is the
same "NULL means not published, not absent" discipline this pipeline already
applies (settled decision #1) and is worth confirming rather than assuming
once real access exists. A separate bulk product, the **Relationships File**,
pre-compiles ownership/subsidiary/branch/share-parcel links across
jurisdictions from official filings, meant to be paired with the API rather
than substituting for it; its own pricing and exact jurisdiction coverage
were not published anywhere this pass could reach and would need a direct
enquiry. Sources: [OpenCorporates API
reference](https://api.opencorporates.com/documentation/API-Reference),
[OpenCorporates blog: API + Relationships
File](https://blog.opencorporates.com/2025/10/28/opencorporates-api-plus-relationships-file/).

## 2. Coverage assessment against this project's actual gap

The ticket's own brief asks about "international company/entity
reconciliation and parent/group discovery" in general. Read against §0, the
only piece of that which is not already served by an existing, working
module is: **resolving the identity of a corporate PSC that Companies House
names but does not itself hold a register page for** — i.e. a foreign parent
or intermediate holding company in a tracked provider's ownership chain.

| Candidate use | Already covered? | Disposition |
|---|---|---|
| UK company profile, officers, filings, insolvency, disqualifications | Yes — `m04`, direct from Companies House, first-hand provenance | **No case for OpenCorporates here.** Would duplicate, with worse provenance, data this pipeline already holds. |
| UK PSC ownership edges | Yes — `m04`/`company_psc`, direct from Companies House | Same as above. |
| Sector universe / entity reconciliation across providers, companies, charities, CQC, contracts | Yes — `m23`, a query over what other modules already collected, fetches nothing | OpenCorporates adds nothing here; `m23`'s job is reconciling this pipeline's own sources, not discovering new ones. |
| **Identity of a foreign corporate PSC** (`company_psc.identification_country_registered` ≠ GB, with a foreign `identification_company_number`) | **No.** Companies House asserts the identifier and stops there; nothing resolves what that entity is, whether it is still active, or what it in turn is owned by. | **Genuine, concrete gap.** This is the one thing OpenCorporates' non-UK register coverage could answer that this pipeline cannot answer today. |
| Multi-hop "who ultimately owns the group" tracing beyond one PSC hop | Not attempted anywhere in the current pipeline | **Gap, but a licensing and scope question before a technical one** — see §3. `ultimate_controlling_company` on the API's own company object would answer a single hop; anything requiring the Relationships File is a separate purchase not evaluated in this pass. |
| General-purpose "search any company anywhere" lookup, unrelated to a PSC this pipeline has already found | Out of scope | **Decline.** This pipeline tracks a fixed set of ~13 providers and their contract counterparties, not company research at large; adding a general lookup tool has no named consumer. |

## 3. Why the module-audit claim needs the one correction, before anyone builds against it

The audit line says OpenCorporates would bring "field-level provenance where
available." Read against what §1 actually found in the API reference: the
standard company object carries **one `source` block per company**
(publisher, URL, `retrieved_at`, terms) plus a `data`/`statements` model the
documentation itself flags mid-migration ("the 'data' type is being
deprecated in favour of statements... improved provenance" — not yet
delivered as documented fact). There is **no documented per-field source URL
or retrieval timestamp** distinguishing, say, which filing a registered
address came from versus which filing the current officer list came from —
the granularity this pipeline's own `_provenance()` helper in `m04_companies`
provides for every row it writes (settled decision #1, and every existing
module in `docs/SOURCES.md`).

That does not disqualify OpenCorporates from the one gap named in §2 —
a foreign PSC's *company-level* identity (name, status, registered address,
its own further parent if published) needs exactly one company-level
provenance record, which OpenCorporates' standard object does supply, and
storing that single `source` block against the row is consistent with how
`companies.source_url` / `retrieved_at` / `payload_sha256` already work for
Companies House rows in this pipeline. It does mean the claim should read
"company-level provenance," not "field-level" — the audit note is close but
overstates the granularity, and this correction is exactly the kind of
"verify current source claims" check the ticket asked for.

## 4. Integration approach for the one confirmed gap

If a human decides the foreign-PSC-identity gap is worth closing:

1. **Licence decision first, before any code.** Either (a) apply for
   OpenCorporates' discretionary free "Permitted User" access, which requires
   publishing any resulting derived data under **Attribution Share-Alike
   ODbL** — meaning anything in the public portal that traces back to an
   OpenCorporates lookup would need its own ODbL attribution and would place
   this pipeline's own combined dataset under share-alike terms for that
   slice, a real constraint on `public_export.py` output that needs a named
   decision, not a default — or (b) buy the lowest paid tier (£2,250/yr at
   time of writing) for a **non-share-alike** licence, which avoids that
   obligation but still requires the "from OpenCorporates" attribution on
   anything displayed. Neither option is free of licensing consequences;
   this document takes neither decision.
2. **Scope the fetch to PSC-triggered lookups only, never a general search.**
   A new, narrow function — analogous to `m04`'s `_fetch_company` — takes a
   `company_psc` row where `identification_country_registered` is not `GB`
   and `identification_company_number` is set, and fetches exactly that one
   OpenCorporates company record. This bounds request volume to the number
   of distinct foreign corporate PSCs this pipeline has already found via
   Companies House — plausibly single or low double digits for 13 tracked
   providers — comfortably inside even the cheapest paid tier's 200/day
   limit, and gives a natural, auditable trigger rather than an open-ended
   crawl.
3. **New table, not an extension of `companies`.** `companies` is keyed on an
   8-character Companies House number (`normalise_company_number`) and is
   populated only from the UK register; a foreign entity does not have one.
   A `foreign_entities` (or similarly named) table keyed on
   `(jurisdiction_code, company_number)` as OpenCorporates itself keys
   entities, carrying `source_system = 'opencorporates'` and the same
   `source_url` / `retrieved_at` / `payload_sha256` shape every other module
   uses, keeps this additive rather than overloading a column whose meaning
   is currently "Companies House only."
4. **Link by identifier only, never by name — same discipline as `m04`.**
   `company_psc.identification_company_number` is the join key; nothing
   about a foreign entity's name is ever used to assert it is part of a
   provider's group, for the same reason `match_basis = 'name_only_unconfirmed'`
   exists today.
5. **`docs/licences.py` and `docs/SOURCES.md` need a new row on the same day**
   the module lands — `tests/test_licences.py` already enforces this for
   every registered module, and the ODbL share-alike/attribution question
   from step 1 is exactly the kind of "not a plain open licence" case that
   table's existing pattern (Modules 6, 9–10, 14–16) is built to carry.
6. **New `review_queue` item type**, e.g. `foreign_entity_lookup_failed`, for
   the case OpenCorporates does not have the jurisdiction, or the fetch
   fails — following the existing `company_profile_unavailable` pattern
   rather than silently dropping the PSC row's identity question.

No migration to any existing table, no change to `m04`'s or `m23`'s current
behaviour, no new evidence layer beyond one additive table under the same
provenance shape everything else already uses.

## 5. Recommended next decisions (none taken here)

1. **Decide the licence route** (§4.1) before writing any code — this is the
   one decision with real, ongoing consequences for what the public portal
   may show, and it is a legal/policy call, not an engineering one.
2. **If proceeding, apply for OpenCorporates' discretionary free access first**
   and see what terms are actually offered to this specific project, rather
   than assuming either the "Permitted User" or the cheapest paid tier
   in advance — the eligibility question in §1 is unresolved by this pass.
3. **Inspect how many foreign corporate PSCs the pipeline has already found**
   via a read-only query over the existing `company_psc` table (a live-data
   check, not a build, in the same spirit as the NDTMS/Fingertips mapping
   question `docs/ohid-ndtms-contextual-indicators.md` §5 leaves open) —
   this tells whether the gap is worth closing at all before any licence is
   bought.
4. **Decline** a general-purpose OpenCorporates company-search integration,
   and decline re-fetching UK entities through OpenCorporates — both would
   add cost and a weaker-provenance duplicate of data this pipeline already
   holds first-hand from Companies House.
5. **Decline, for this pass, the Relationships File and any multi-hop
   "ultimate owner" tracing beyond one PSC hop** — its pricing, coverage and
   exact sourcing discipline were not reachable in this research pass and
   would need their own scoping once the single-hop case (§4) has a track
   record.

Every item above is a candidate for a named human decision, not an
implementation queue — consistent with this issue's Not-scheduled/Post-V1
readiness label.

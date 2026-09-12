# 360Giving / GrantNav grants evidence feasibility (JON-6)

**Status: feasibility only. No code, migration or module changed.** Written
against commit `55fde50` with a clean tree. JON-6 is labelled `Post-V1` /
`Not scheduled`, and its own outcome asks for feasibility, source/access
terms, provenance requirements, an integration approach and draft acceptance
criteria before implementation — not an implementation. The ticket's earlier
numeric ranking is superseded by a module audit that renamed this a distinct
module, proposed `m36_360giving` (numbering to be confirmed at build time,
not reserved here) supporting `m03_charity_finance` and `m23_sector_universe`.

Every factual claim below was checked live on 2026-09-12 against
`api.threesixtygiving.org`, `registry.threesixtygiving.org` and
`grantnav.threesixtygiving.org` themselves — including their `robots.txt` —
not against a summary of any of them. One useful negative result from that
discipline: a widely-repeated description of "the GrantNav bulk API" names
`https://grantnav.threesixtygiving.org/api/grants.json` as the way to fetch
the whole dataset. That endpoint returns a live **404** today (§3) — it is
gone, superseded by a genuinely different, newer HTTP API on a different
host, and any integration plan built on the old description would fail
before writing its first row.

## 1. What already exists (read before proposing anything new)

There is no grants module in this pipeline today. The relevant existing
machinery is the identifier-based reconciliation discipline this ticket asks
to reuse, not extend:

| Piece | What it gives a grants module | Where |
|---|---|---|
| `provider_identifiers` (`scheme = 'charity_number'` / `'company_number'`) | The exact lookup table a grants module needs: a tracked provider's own charity and company numbers, asserted once and shared across modules | `pipeline/providers.py` |
| `m03_charity_finance._seed_charity_numbers` / `m04_companies._seed_company_numbers` | The precedent for "look up a source's own record by a provider's already-known identifier" — a grants module does the same lookup against a different source, not a new matching algorithm | `pipeline/modules/m03_charity_finance.py`, `pipeline/modules/m04_companies.py` |
| `m23_sector_universe`'s `match_basis` discipline | The rule this ticket's "recipient reconciliation" ultimately has to obey: `provider_key` is set only through a verified identifier a source published, never through a name, and an unconfirmed link is a review item, not a fact | `pipeline/modules/m23_sector_universe.py` |
| `m01_procurement`'s GB-PPON-keyed awardees | The closest existing precedent for attributing money to an organisation by a published identifier rather than free-text name matching | `pipeline/modules/m01_procurement.py` |
| `EVIDENCE_LAYERS["finance"]` (`m03`, `m11_public_health_grant`, `m13_la_budgets`) | The evidence layer a grants module almost certainly belongs to — money received/made by name, kept in its own table, never combined across sources | `pipeline/web/datasets.py` |

**This ticket does not touch `m01`, `m03`, `m04`, `m11` or `m23`.** Nothing
here changes what they collect; a grants module would read
`provider_identifiers` the same way `m03`/`m04` already do, not alter it.

## 2. What 360Giving, the Registry, GrantNav and the API actually are — four different things

The ticket names "360Giving / GrantNav" as one thing. Live inspection shows
four, easy to conflate and worth keeping apart:

1. **The 360Giving Data Standard** — a schema for publishing grants data
   (funder, recipient, amount, currency, dates, purpose, classifications) and
   an organisation-identifier scheme (`GB-CHC-<charity number>`,
   `GB-COH-<company number>`, `GB-SC-`/`GB-NIC-` for Scottish/NI charities,
   `GB-GOR-` for government departments, and an internal `360G-<publisher>-`
   prefix for organisations with no official register entry). This is a
   specification, not something to fetch.
2. **The Data Registry** (`registry.threesixtygiving.org`) — a catalogue of
   individual funders' own published data files. **This is discovery
   metadata, not data**, in exactly `m19_data_gov_uk`'s sense: its JSON feed
   (`https://registry.threesixtygiving.org/data.json`, fetched live) lists
   **883 datasets from 296 publishers**, each entry a `downloadURL` pointing
   to a file hosted on the *publisher's own* infrastructure — not
   360Giving's — in whatever format that publisher chose.
3. **GrantNav** (`grantnav.threesixtygiving.org`) — a search/visualisation
   front end over an aggregated copy of every validated Registry dataset,
   currently described by 360Giving's own downloading guide as holding "over
   1 million grants." Its documented bulk-download endpoints are dead (§3);
   its search UI is the wrong route regardless (§3).
4. **The 360Giving API** (`api.threesixtygiving.org`) — a REST/JSON API
   announced in 2024, separate from GrantNav's older, now-retired bulk
   endpoints. This is the one live, working, machine-friendly route into the
   aggregated data (§3), and the one an integration should use.

## 3. Verified live today

**GrantNav's documented bulk-download endpoints are gone.**
`https://grantnav.threesixtygiving.org/api/grants.json`,
`.../api/grants.csv` and `.../api/1.0/grants.json` all return HTTP 404 as of
2026-09-12. The current, documented way to get "the whole dataset" is a
no-filter download from GrantNav's own `/search` page.

**GrantNav's `/search` is exactly what `robots.txt` disallows, and it also
503s to a plain fetch.** `grantnav.threesixtygiving.org/robots.txt` disallows
`/search`, `/recipients` and `/funders` for every user agent (`User-agent:
*` shares the same rule block as the named bots, not a separate one) — so
this pipeline's own robots-respecting client (settled decision 5) could not
fetch the bulk-download link even if the endpoint still worked. Confirmed
independently: a plain GET of `/search` returned HTTP 503 twice, from two
different fetchers, on the same day. GrantNav's HTML front end is not a
route this pipeline should use, on both grounds at once.

**The 360Giving API is live, unblocked and requires no key.**
`api.threesixtygiving.org/robots.txt` itself 404s (no file, so no
directives — everything is fetchable under the standard's own terms, §6).
Confirmed live:

```
GET https://api.threesixtygiving.org/api/v1/org/?limit=3
→ {"count": 454270, "next": "...&offset=3", "previous": null, "results": [...]}

GET https://api.threesixtygiving.org/api/v1/org/GB-CHC-1079327/
→ {"name": "Change Grow Live", "recipient": {"aggregate": {"grants": 21,
   "earliest_grant_date": "2006-11-15", "latest_grant_date": "2023-11-24",
   "currencies": {"GBP": {"total": 2706858.0, ...}}}}, "funder": null,
   "linked_orgs": [{"org_id": "GB-COH-03861209"}]}
```

That last call is a real, spot-checked answer to the ticket's own question:
**Change Grow Live — one of this pipeline's tracked providers — appears in
360Giving data as a grant recipient**, 21 grants totalling £2,706,858 across
2006–2023, and never as a funder (`funder: null`). Only one provider was
spot-checked; whether the other 12 appear was not tested here.

Four endpoints exist, all `GET`, all paginated with `limit`/`offset` and a
`next`/`previous`/`count` envelope, none accepting a date, amount or
"since" filter of any kind:

| Endpoint | Returns |
|---|---|
| `/api/v1/org/` | Every organisation (funder or recipient) known across all published grants — 454,270 today |
| `/api/v1/org/<org_id>/` | One organisation's summary: aggregate grants made/received, date range, currency totals, `linked_orgs` |
| `/api/v1/org/<org_id>/grants_made/` | Every grant that organisation funded |
| `/api/v1/org/<org_id>/grants_received/` | Every grant that organisation received |

**No date, amount or incremental-fetch parameter exists on any endpoint** —
confirmed against the live endpoints list, not assumed from the absence of
documentation for one. `dateModified` appears on some individual grant
records and not others (see the two example payloads in §5) — it is a
publisher-supplied field, not a guaranteed one, and cannot be relied on as a
universal checkpoint column.

## 4. Coverage

- **883 datasets, 296 publishers**, per the Registry's own JSON feed, dated
  from the earliest dataset registration on 2018-08-03 to one modified
  2026-09-11 — the day before this document. This is a floor on publisher
  count, not the number of UK grantmakers: publication is voluntary, and a
  funder that has never registered with 360Giving is invisible here, the
  same "capture, not a census" caveat `m23_sector_universe` already carries
  for its own universe.
- **454,270 distinct organisations** (funders and recipients combined) are
  known to the live API today, across "over 1 million grants" by GrantNav's
  own stated dataset size.
- **Licensing is overwhelmingly open**, counted directly from all 883
  Registry entries: 702 Creative Commons Attribution 4.0 (CC BY), 123 Open
  Government Licence v3.0, 36 CC BY-SA 4.0 (share-alike), 22 CC0/Public
  Domain. No dataset in the current Registry carries a non-commercial or
  no-derivatives term. The API's own per-grant `data_license` field (§5)
  repeats this at row level, which is more useful for `pipeline/licences.py`
  than a single module-wide licence string: this source needs the
  `"varies by publisher"` pattern already used for Modules 9, 10, 24 and 28,
  not a single OGL-style entry.
- **File formats behind the Registry are heterogeneous**: of the 883
  `downloadURL`s, 649 are `.xlsx`, 153 have no file extension (dynamic
  export endpoints), 33 `.json`, 23 `.csv`, 11 `.ods`, and a handful of
  `.aspx`/`.ashx` query endpoints. This pipeline already has readers for two
  of those (`pipeline/xlsx.py`'s hand-rolled reader, used by `m24`/`m30`/
  `m31`; `odfpy` for ODS), which matters only if the Registry route (raw
  per-publisher files) is ever chosen over the API route — see §7.

## 5. Data fields, and what the API's own answers correct about a "typical" 360Giving summary

Two real grant records for the same recipient (Change Grow Live), fetched
live from `grants_received`, worth reading side by side because they
disagree on shape in ways a schema has to tolerate rather than assume away:

```json
{
  "grant_id": "360G-BarnwoodTrust-GF103354",
  "data": {
    "awardDate": "2023-03-22",
    "dateModified": "2024-02-07T00:00:00Z",
    "amountAwarded": 1500, "currency": "GBP",
    "fundingOrganization": [{"id": "GB-CHC-1162855", "name": "Barnwood Trust"}],
    "recipientOrganization": [{"id": "GB-CHC-1079327", "name": "Change Grow Live",
                                "postalCode": "Change Grow Live", "charityNumber": "1079327"}]
  },
  "data_license": {"name": "Creative Commons Public Domain Dedication 1.0 Universal"}
}
```

```json
{
  "grant_id": "360G-cabinetoffice-G2-GA-202106432507-20-21",
  "data": {
    "awardDate": "2020-05-29T00:00:00+00:00",
    "amountAwarded": 923, "currency": "GBP",
    "fundingOrganization": [{"id": "GB-GOR-D5", "name": "Department for Digital, Culture, Media & Sport"}],
    "recipientOrganization": [{"id": "GB-COH-03861209", "name": "CHANGE GROW LIVE",
                                "postalCode": "BN11YR", "charityNumber": "1079327",
                                "companyNumber": "03861209"}]
  },
  "data_license": {"name": "Open Government Licence 3.0 (United Kingdom)"}
}
```

Four concrete findings from this pair, not from the standard's documentation:

1. **`awardDate` is inconsistently formatted across publishers** — a bare
   `"2023-03-22"` in one record, a full `"2020-05-29T00:00:00+00:00"`
   timestamp in another, for the same recipient. A parser needs to accept
   both, the same tolerant-date discipline already used elsewhere in this
   pipeline rather than a single strptime format.
2. **The same real organisation is filed under two different identifier
   schemes in different grants** — `GB-CHC-1079327` in one row,
   `GB-COH-03861209` in another, with `charityNumber`/`companyNumber` both
   present as plain fields alongside whichever `id` the publisher chose.
   **Reconciliation therefore has to check both `provider_identifiers`
   schemes against both the `id` prefix and the explicit `charityNumber`/
   `companyNumber` fields** — matching on `id` alone would miss the second
   grant.
3. **Publisher data quality is exactly as unverified as any other
   self-published source this pipeline already stores as-is**: one live
   record's `postalCode` field literally contains the string `"Change Grow
   Live"` — a publisher data-entry error, not a parsing fault. The right
   answer, consistent with every other module's discipline, is to store it
   verbatim and never repair it, not to detect and "fix" what looks wrong.
4. **`data_license` is a per-*grant* field, not merely a per-dataset one** —
   the CC0 grant and the OGL grant above are two different licences on two
   rows about the same recipient, confirming §4's licence table needs
   recording per row, the same granularity Module 1's Kaggle channel
   sightings and Module 24's council files already require.

**`linked_orgs`** (seen on Change Grow Live's own organisation summary,
linking `GB-CHC-1079327` to `GB-COH-03861209`) is 360Giving's own,
publisher-derived cross-scheme association. It is a lead, not a
corroborated identity, by the same discipline `m04`'s `match_basis` and
`m23`'s `name_only_unconfirmed` already apply to every other externally
asserted link in this pipeline — useful for widening a reconciliation
search, never sufficient on its own to set `provider_key`.

## 6. Access terms and provenance requirements

- **No API key or account is technically required** — verified by the calls
  in §3 succeeding with a plain `Accept: application/json` header and no
  credentials.
- **A documented, non-enforced expectation exists to register and to accept
  Terms and Conditions / a Code of Conduct** before using the API, primarily
  so 360Giving can notify registered users of take-down requests. This is an
  operational step for a person, the same shape as
  `docs/mysociety-access-request.md`'s access-request discipline for Module
  15 — not something to skip because the API happens to work without it.
- **Publishers can and do withdraw datasets.** The Registry and GrantNav
  both describe data as removed on request. A grants module therefore needs
  the same "what happens when the source takes something back" answer
  Module 15 already has for `robots_exceptions` — this document does not
  choose one (§9).
- **The only published numeric rate limit found is the older GrantNav API's
  "2 requests per user per second," returning HTTP 429 over that.** The
  current `api.threesixtygiving.org` documentation states only that "rate
  limiting is in place to ensure stability" with no number given. Treat 2
  req/s as the working assumption until a live 429 says otherwise, which
  this pipeline's shared HTTP client's per-host default already satisfies
  without a per-host override.
- **Provenance**: every grant record already carries the fields this
  pipeline's `_provenance()` convention needs — a stable `grant_id`, the
  publisher's own `dataSource` URL, a `data_license`, and (inconsistently) a
  `dateModified`. The fetch itself (an HTTPS GET with no auth) archives
  under `data/raw/` exactly as every other module's fetch does; no new
  provenance mechanism is needed, only the usual `source_url` (the API call
  actually made, including `org_id` and offset), `retrieved_at` and
  `payload_sha256`.

## 7. Integration approach (recommended, not built)

1. **Use the `api.threesixtygiving.org` REST API, not GrantNav's HTML
   front end or its dead bulk endpoints.** This closes both problems in §3
   at once: the disallowed/503ing `/search` path and the retired
   `/api/grants.json`.
2. **Scope collection to the tracked providers, not the whole corpus.**
   Rather than walking all 454,270 known organisations, look up each
   tracked provider's own `charity_number`/`company_number` from
   `provider_identifiers` (already asserted, already used by `m03`/`m04`)
   and call `/org/GB-CHC-<n>/grants_received/` **and**
   `/org/GB-COH-<n>/grants_received/` for each — §5 showed the same real
   organisation filed under either scheme depending on the grant, so a
   provider with both identifiers needs both calls, deduplicated on
   `grant_id`. This is a bounded, provider-scoped fetch (13 providers × up
   to 2 org-id calls each), not a corpus-wide crawl.
3. **`grants_made` is included for completeness, not because it was found to
   matter.** The one provider spot-checked (Change Grow Live) has
   `funder: null`. Worth keeping in the design so a provider that does run a
   small grants programme is not silently missed, but not worth building
   before evidence one exists.
4. **No incremental fetch exists server-side, so re-running is a bounded
   re-pull, not a real "since" query.** Because collection is scoped to ~13
   providers' own grants (§7.2), a full re-fetch of each provider's
   `grants_received`/`grants_made` on every run is cheap enough that
   `supports_since=False` with an honest `since_note` (the same declared-gap
   pattern `m15_foi` already uses) is a reasonable first answer, upsetting
   nothing structurally. Comparing each grant's `dateModified` against what
   is already stored (where the field is present at all) would let a run
   report "N grants changed" without needing a source-side filter — an
   enhancement, not a blocker.
5. **New module and new table(s), evidence layer `finance`.** A single
   `three_sixty_giving_grants` table (one row per `grant_id` per matched
   provider, with a `direction` column — `received`/`made` — rather than two
   near-identical tables) mirrors `m27`'s generic-indicator precedent over
   `m29`'s one-table-per-source precedent; either is defensible, and this is
   a named open decision (§9), not a default. Whichever shape is chosen, the
   natural key needs `grant_id` (already globally unique per publisher
   prefix) plus `provider_key` plus `direction`.
6. **Recipient reconciliation is a lookup, not new matching logic.** Query
   `provider_identifiers` for each tracked provider's charity/company
   numbers (exactly the `_seed_charity_numbers`/`_seed_company_numbers`
   pattern in `m03`/`m04`), call the two org-id endpoints in §7.2, and set
   `provider_key` only from that identifier match — never from
   `recipientOrganization.name` text, and never purely from `linked_orgs`
   (§5) without the identifier it names also resolving to the same
   provider through `provider_identifiers`.
7. **Per-row licence, not a single module licence string.** Record
   `data_license` verbatim per grant and add a `"varies_by_publisher"` entry
   to `pipeline/licences.py` on the day this module is built, satisfying
   `tests/test_licences.py`'s existing per-module requirement.
8. **The Data Registry's raw per-publisher files (§4) are a fallback, not
   the primary route** — useful only if a specific field the API's
   flattened response drops (the API "does not contain all the original
   fields," per 360Giving's own documentation) is needed for one provider's
   grants, fetched individually rather than as a corpus-wide alternative to
   the API.

## 8. Draft acceptance criteria (for a future implementation ticket, not this one)

| Case | Expected result | Check |
|---|---|---|
| Tracked provider has both a `charity_number` and `company_number` in `provider_identifiers` | Both `/org/<id>/grants_received/` calls are made; results deduplicated on `grant_id` | Fixture with the same `grant_id` returned under both identifier lookups |
| Tracked provider has neither identifier on file | Module records a review item rather than skipping the provider silently | New review-queue reason, name TBD at build time |
| A grant's `recipientOrganization` carries a `charityNumber`/`companyNumber` that does not match `id`'s own scheme | Both fields are checked against `provider_identifiers`, not just `id` | Fixture built from the real Change Grow Live COH-scheme grant in §5 |
| `dateModified` present vs absent on a grant | Stored as `NULL` when absent, never defaulted to `awardDate` or the fetch time | Fixture pair, one with and one without the field |
| `data_license` differs between two grants for the same recipient | Both are stored verbatim per row; no single module-wide licence is asserted | Fixture pair using two different real licences from §5 |
| Pagination beyond one page | Every page is fetched via `next` until null, not just the first `limit` | Fixture with `count` greater than one page |
| A previously stored grant no longer appears in a re-fetch | Treated as "not returned this run," not deleted — mirrors this pipeline's general discipline of not inferring cessation from absence (`docs/CAVEATS.md`'s CDP-documents entry states this rule explicitly for a comparable case) | New test; exact handling is one of §9's open decisions |

## 9. Recommended next decisions (none taken here)

1. **Table shape** — one `three_sixty_giving_grants` table with a
   `direction` column, or two separate tables — before any migration is
   written (§7.5).
2. **What happens to a grant that disappears from a re-fetch** — a
   publisher genuinely withdrew it (take-down), or it simply fell outside
   whatever window the source returns — needs a named answer before storage
   semantics are fixed, the same class of decision JON-40's revision
   question raised for RSDF.
3. **Whether `grants_made` is worth collecting at all in the first pass**,
   given the one provider checked here made none — or whether to defer it
   until a provider is found to run a grants programme.
4. **Registering with 360Giving's API notification list** is a human,
   pre-implementation step (§6), not a code change, and should happen before
   any production collection starts rather than being treated as optional.
5. **The `docs/CAVEATS.md` entry this module will need** should state, in
   its own words, the ticket's own instruction verbatim: 360Giving grant
   income is never summed with `m01` contract value, `m11` public health
   grant allocations, or any other finance-layer figure, and a provider's
   count of grants received is a floor over voluntarily published data, not
   a picture of its total grant income.

## Sources

* This repository: `pipeline/providers.py`, `pipeline/modules/m03_charity_finance.py`,
  `pipeline/modules/m04_companies.py`, `pipeline/modules/m23_sector_universe.py`,
  `pipeline/modules/m01_procurement.py`, `pipeline/modules/m30_statutory_homelessness.py`,
  `pipeline/xlsx.py`, `pipeline/web/datasets.py`, `pipeline/licences.py`,
  `docs/SOURCES.md`, `docs/CAVEATS.md` (read 2026-09-12).
* `https://api.threesixtygiving.org/api/v1/org/`,
  `.../org/GB-CHC-1079327/`, `.../org/GB-CHC-1079327/grants_received/`,
  `.../org/GB-CHC-1000147/grants_made/` and `https://api.threesixtygiving.org/robots.txt`
  — fetched live 2026-09-12, the primary source for §3, §5 and §6.
* `https://registry.threesixtygiving.org/data.json` — fetched live
  2026-09-12 and counted directly (883 datasets, 296 publishers, licence
  distribution, file-extension breakdown) for §4.
* `https://grantnav.threesixtygiving.org/robots.txt`,
  `.../api/grants.json`, `.../api/grants.csv`, `.../api/1.0/grants.json`,
  `.../search` — fetched live 2026-09-12; the 404s and the disallow/503 on
  `/search` are the basis for §3's correction of the commonly repeated bulk
  API description.
* `https://www.360giving.org/explore/technical/api/`,
  `.../api-docs/`, `.../api-docs/use/`, `.../api-docs/endpoints/`,
  `.../explore/technical/grantnav-data/`, `.../explore/user-guide/downloading/`,
  `.../explore/before-you-start/how-to-access/`,
  `.../2024/06/11/360giving-api/` — fetched 2026-09-12, for API history,
  documented rate limits and the take-down/registration policy in §6.
* `https://standard.threesixtygiving.org/en/latest/technical/identifiers/` —
  fetched 2026-09-12, for the organisation-identifier prefix table in §2.

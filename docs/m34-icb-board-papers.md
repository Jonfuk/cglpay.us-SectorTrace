# Module 34 — Integrated Care Board governance documents

**Status:** built — migration `0081`, `pipeline/icb_boards.py`,
`pipeline/modules/m34_icb_board_papers.py`, `tests/test_m34_icb_board_papers.py`.
This document is now the design record; what shipped matches it, with the
notes below.

**As built:**

- **§11 Q1 was taken: the directory drives the seed.** `_collect_directory`
  fetches the NHS England "integrated care in your area" page into
  `integrated_care_boards` with provenance, and `pipeline/icb_boards.py`
  carries hand-verified `board_url` overrides — seeded with the one the module
  was built from (Nottingham and Nottinghamshire). An ICB with no override
  falls back to its directory link's origin with `MEETING_PATHS` probed
  against it; with neither it is an `icb_board_url_unknown` review item. The
  hand-verify-all-42 option was not taken because 42 sites cannot be verified
  offline without fabricating provenance.
- **§11 Q2 was taken: governance section, not the whole publications
  library.** `MEETING_PATHS` covers the Board and the standing committees;
  a `/publications` sweep is left as a future widening.
- **§11 Q3 (first-run size check) is still open** — it needs a live run, which
  the offline suite cannot do. The integration smoke spec
  (`tests/test_integration_smoke.py`, `m34_icb_board_papers`, `--limit 3`)
  and the module docstring both flag the first real run for a person to
  watch.
- Table natural key is `integrated_care_boards.name` / `icb_name`, not the ODS
  code: the directory does not reliably publish a code next to each ICB.
  `ods_code` is recorded from `icb_boards.ODS_CODES` when present (empty for
  now — a code is provenance, not a guess).
- Review-item types shipped: `icb_directory_unavailable`,
  `icb_directory_robots_disallowed`, `icb_board_url_unknown`,
  `icb_collection_failed`, `icb_paper_robots_disallowed`,
  `icb_doc_unavailable`, `icb_doc_ceiling_reached`, `icb_no_documents_found`.

---

## Original proposal

An ICB is a statutory NHS body that plans and funds most NHS services in its
area. There are **42** of them (they replaced 211 CCGs in July 2022). Each
publishes its Board and committee papers on its own website — Nottingham and
Nottinghamshire's Board, the example that prompted this, sits under
`https://notts.icb.nhs.uk/about-us/our-icb-board/`.

**Scope (per the "capture all documents" instruction): every document in an
ICB's meetings/governance area — the Board and all standing committees, with
agendas, reports, minutes and enclosures — captured in full regardless of
subject. See §2a.**

## 1. Why this is worth collecting — and the limit that shapes it

Drug and alcohol treatment in England is **commissioned by local authorities**
out of the public health grant, not by the NHS. So an ICB is *not* a
commissioner of the services this campaign is about, and this module must not
be read as if it were. What ICB board papers do carry, in passing, is:

- dual-diagnosis / mental-health commissioning that overlaps the treatment
  population, and inpatient detox where it is NHS-commissioned;
- Combating Drugs Partnership updates and joint board reports;
- named provider contracts, TUPE, and pay/workforce pressure, where a
  provider also holds an NHS contract or the ICB co-funds a service;
- shared-care prescribing arrangements with primary care.

**The founding caveat:** a mention in a 300-page board pack is *context*, never
a figure. This module extracts no spend, no headcount, and nothing that
requires knowing which LA an ICB "covers". It is a finding aid over a document
corpus — the same role Module 28 plays for SAR reports. See
[docs/CAVEATS.md](CAVEATS.md) §"ICB board papers (Module 34)", added with the
migration.

## 2. Why a new module, not more of m10

Module 10 searches **council** committee systems (ModernGov / CMIS) for papers
whose *title* matched a term. Neither assumption transfers:

- ICBs do not run ModernGov or CMIS. Each has a bespoke CMS page listing
  meetings, with the papers attached as PDFs (very often one omnibus "Board
  papers — 25 September 2025" bundle of 100–400 pages, plus separate
  enclosures).
- **Title matching does not work on an omnibus pack.** The bundle's link text
  is a date, not a subject. The substance-misuse content is on page 214 of the
  PDF. So discovery cannot filter on link text the way m09/m10 do — it has to
  take the whole pack and filter on the *extracted text* afterwards.

The closest existing analogue is **Module 32** (`m32_sab_site_reviews`): crawl
each of N bodies' own sites over a bounded path list plus one hop, same-host
only, then read every document found on a confirmed index page and let a
downstream gate decide evidence vs. review. m34 is m32's shape applied to a
different corpus, and reuses m28's PDF/DOCX readers, concern-term indexer and
provider-mention matcher unchanged.

## 2a. Scope: capture every governance document, not just the sector-relevant ones

**Decision (supersedes §11 Q2):** the module captures **every document
published under an ICB's meetings/governance area** — the Board *and* every
standing committee (Finance & Performance, Quality & Safety, Audit,
Remuneration, People, and any others), including agendas, minutes, headline
reports and every attached enclosure. It does **not** subject-filter what it
stores. Every captured document is archived to `data/raw/`, has its text
extracted, and is indexed for subject terms and provider mentions.

Two reasons to take the whole corpus rather than only the packs that look
relevant:

- The relevant content is unpredictably placed. A drug-treatment provider's
  staffing problem surfaces in a Quality Committee exception report as often
  as in the Board pack, and a "capture the pack, skip the committees" rule
  would miss it by construction.
- Whether a document is relevant is a *judgement* (§1), and this pipeline
  makes judgements with a person, not a keyword. Storing everything and
  letting the subject index **rank the review worklist** keeps that judgement
  where it belongs. `subject_hits = 0` means "not surfaced for review now",
  never "discarded" — the archived bytes and full text are still there when a
  later question needs them.

The one boundary still drawn: **meetings/governance documents, not the entire
site publication library** (strategies, JSNAs, easy-read leaflets, job packs,
newsletters). Widening to `/publications` wholesale is a separate decision —
§11 Q2, rewritten.

## 3. The 42-body spine

42 is small enough to **hand-verify once**, which is the m09 lesson (invented
hostnames "quietly find nothing while appearing to have searched"). Two parts:

1. **`pipeline/icb_boards.py`** — a static, hand-verified registry, one entry
   per ICB: `{ods_code, name, region, board_url}`, where `board_url` is the
   confirmed board-papers landing page (the `notts.icb.nhs.uk/about-us/our-icb-board/`
   equivalent), checked by request against the exact path this module will
   join to. Mirrors `pipeline/authority_websites.py`. `ods_code` is the ICB's
   3-character NHS ODS code (e.g. Nottingham and Nottinghamshire), `NULL`
   until confirmed against the NHS England ODS list.

2. **A directory fetch**, run at the top of the module, to notice drift: NHS
   England's "integrated care in your area" page lists all 42 with links.
   Parsed into `integrated_care_boards` (reference table, provenance
   attached). A name in the directory with no entry in `icb_boards.py`, or a
   registry `board_url` that no longer resolves, becomes a review item
   (`icb_board_url_unknown` / `icb_board_url_stale`) — the same "a link is a
   claim, verify it" discipline m10 applies. The directory never overrides the
   hand-verified `board_url`; it only flags divergence.

The nhs.uk "find your local ICB" page the request pointed at is a postcode
lookup widget; the NHS England area page is the cleaner directory source and
is what §11 Q1 asks about.

## 4. Schema — migration `0081_icb_board_papers.sql` (both dialects)

```sql
-- Reference: the 42 ICBs, seeded from the NHS England directory, provenance
-- attached. The hand-verified board_url lives in pipeline/icb_boards.py, not
-- here, for the same reason authority websites do: it is code-reviewed.
CREATE TABLE IF NOT EXISTS integrated_care_boards (
    ods_code        TEXT PRIMARY KEY,     -- NHS ODS 3-char code; the natural key
    name            TEXT NOT NULL,
    region          TEXT,                 -- NHS England region, as the directory states it
    directory_url   TEXT,                 -- the ICB's page on the NHS England directory
    board_url       TEXT,                 -- confirmed meetings/governance entry page (from icb_boards.py)
    source_url      TEXT NOT NULL,
    retrieved_at    TEXT NOT NULL,
    http_status     INTEGER NOT NULL,
    source_system   TEXT NOT NULL,
    payload_sha256  TEXT NOT NULL
);

-- Candidate documents. DISCOVERY, NOT EXTRACTION — nothing here is evidence.
-- One row per document URL. verified/rejected are set by a person; a re-run
-- refreshes discovery metadata and the indexed term counts but never a
-- decision column (db.DECISION_COLUMNS via preserve=).
CREATE TABLE IF NOT EXISTS icb_board_paper_candidates (
    icb_ods_code        TEXT NOT NULL,
    document_url         TEXT NOT NULL,
    meeting_title        TEXT,            -- link text / nearest heading, e.g. "Board meeting"
    committee_name       TEXT,            -- the committee, where URL/heading names one; NULL for the Board itself
    meeting_date         TEXT,            -- ISO, parsed from link text/heading; NULL if unparseable (+ parse_failures row)
    document_kind        TEXT,            -- 'board_pack' | 'committee_pack' | 'agenda' | 'minutes' | 'report' | 'enclosure' | 'unknown'
    from_index_page      INTEGER NOT NULL DEFAULT 0,  -- found on a confirmed meetings/governance index
    has_body_text        INTEGER NOT NULL DEFAULT 0,
    subject_hits         INTEGER NOT NULL DEFAULT 0,   -- total substance-misuse term occurrences in the text
    provider_mentions    INTEGER NOT NULL DEFAULT 0,   -- distinct providers named in the text
    verified             INTEGER NOT NULL DEFAULT 0,
    verified_at          TEXT,
    rejected             INTEGER NOT NULL DEFAULT 0,
    discovered_at        TEXT NOT NULL,
    discovery_method     TEXT,            -- 'path_crawl:/…' | 'subpage_hop'
    source_url           TEXT NOT NULL,
    retrieved_at         TEXT NOT NULL,
    http_status          INTEGER NOT NULL,
    source_system        TEXT NOT NULL,
    payload_sha256       TEXT NOT NULL,
    PRIMARY KEY (icb_ods_code, document_url),
    FOREIGN KEY (icb_ods_code) REFERENCES integrated_care_boards (ods_code)
);
CREATE INDEX IF NOT EXISTS idx_icb_candidates_verified
    ON icb_board_paper_candidates (verified, icb_ods_code);
CREATE INDEX IF NOT EXISTS idx_icb_candidates_subject
    ON icb_board_paper_candidates (subject_hits);

-- Only verified candidates are promoted here, with archived copy + full text.
CREATE TABLE IF NOT EXISTS icb_board_papers (
    icb_ods_code    TEXT NOT NULL,
    document_url     TEXT NOT NULL,
    meeting_title    TEXT,
    committee_name   TEXT,
    meeting_date     TEXT,
    document_kind    TEXT NOT NULL,       -- confirmed, not guessed
    archived_path    TEXT,
    full_text        TEXT,
    source_url       TEXT NOT NULL,
    retrieved_at     TEXT NOT NULL,
    http_status      INTEGER NOT NULL,
    source_system    TEXT NOT NULL,
    payload_sha256   TEXT NOT NULL,
    PRIMARY KEY (icb_ods_code, document_url),
    FOREIGN KEY (icb_ods_code) REFERENCES integrated_care_boards (ods_code)
);

-- Term-frequency finding aid over the full text (same term list and role as
-- sar_concern_terms / pfd_reports). Not an excerpt: an ICB pack has no shared
-- template, so no "where the relevant bit starts" pattern would be trustworthy.
CREATE TABLE IF NOT EXISTS icb_paper_subject_terms (
    document_url  TEXT NOT NULL,
    term          TEXT NOT NULL,
    occurrences   INTEGER NOT NULL,
    PRIMARY KEY (document_url, term)
);

CREATE TABLE IF NOT EXISTS icb_paper_provider_mentions (
    document_url  TEXT NOT NULL,
    provider_key  TEXT NOT NULL,
    matched_name  TEXT NOT NULL,
    PRIMARY KEY (document_url, provider_key)
);

-- One row per ICB per run, rewritten each time, so "which ICBs yield nothing"
-- is a query not an inference — the role sab_site_crawls / council_spend_files play.
CREATE TABLE IF NOT EXISTS icb_site_crawls (
    icb_ods_code    TEXT PRIMARY KEY,
    board_url        TEXT NOT NULL,
    pages_fetched    INTEGER NOT NULL,
    docs_found        INTEGER NOT NULL,   -- every governance document captured this run
    docs_with_subject INTEGER NOT NULL,  -- of those, how many mention the sector (worklist size)
    ceiling_reached  INTEGER NOT NULL DEFAULT 0,  -- 1 if MAX_DOCS_PER_ICB truncated the crawl
    status            TEXT NOT NULL,      -- 'ok' | 'no_documents_found' | 'unreachable' | 'robots_disallowed'
    last_crawled      TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    retrieved_at      TEXT NOT NULL,
    http_status       INTEGER NOT NULL,
    source_system     TEXT NOT NULL,
    payload_sha256    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_icb_site_crawls_status ON icb_site_crawls (status);

-- RESTRICTED: governance documents name officers ("presented by <name>,
-- Director of Commissioning") and committee reports reference patient-safety
-- incidents more often than the Board pack does. The
-- matched-text window around a subject-term hit goes here, never to the
-- exportable candidate table — kept out of every export by guard_columns()
-- and the reveal gate, not by this module remembering to redact.
CREATE TABLE IF NOT EXISTS restricted_icb_paper_snippets (
    document_url   TEXT NOT NULL,
    term           TEXT NOT NULL,
    snippet_text   TEXT NOT NULL,
    source_url     TEXT NOT NULL,
    retrieved_at   TEXT NOT NULL,
    http_status    INTEGER NOT NULL,
    source_system  TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (document_url, term)
);
```

## 5. Discovery algorithm (`crawl_icb(unit, client)` on a pool thread)

Concurrency across the 42 ICBs is free and safe: 42 distinct hosts, and the
per-host rate limit is process-wide (`pipeline.http.HOST_CLOCK`). Fetch only —
the worker returns a findings object and the main thread writes it, exactly as
m32's `BoardCrawl` / m10's `AuthorityFindings` do.

Per ICB:

1. Start at the hand-verified `board_url`. Also try a bounded `MEETING_PATHS`
   set relative to the ICB's origin — the Board *and* the standing committees,
   since §2a takes all of them — e.g. `/about-us/our-icb-board`,
   `/about-us/governance/board-meetings`, `/about-us/board-meetings-and-papers`,
   `/get-involved/board-meetings`, `/who-we-are/our-board`,
   `/about-us/corporate-governance`, `/about-us/committees`,
   `/about-us/our-committees`, `/publications/governance`,
   `/publications/board-papers`, `/publications/committee-papers`. A 404 is
   expected and unremarkable (m09/m32). The final list is fixed once during
   the §11 Q3 dry run against the real sites.
2. **One hop** (m32's `MAX_SUBPAGES_PER_SAB` pattern, but widened): a same-host
   link whose text carries a governance word — `board`, `committee`,
   `governance`, `meeting`, `agenda`, `papers`, `minutes` — but points at a
   page, not a document, is followed once. ICB sites routinely keep a
   per-committee, year-by-year archive one or two clicks below the landing
   page; `MAX_SUBPAGES_PER_ICB` is raised accordingly (≈ 25) because there are
   many committees, not one board.
3. On any page reached from step 1 or 2, collect **every** same-host link to a
   `.pdf` / `.docx` / `.odt`. Do **not** require subject vocabulary in the link
   text — §2a. Classify `document_kind` from link text / URL (`board_pack`,
   `committee_pack`, `agenda`, `minutes`, `enclosure`, `report`, else
   `unknown`) and, where the URL or heading names the committee, record it in
   `committee_name`; parse a `meeting_date` from the link text or nearest
   heading, `NULL` + `parse_failures` if it will not parse.
4. Bound it as a **safety ceiling, not a target**: `MAX_PAGES_PER_ICB`
   (≈ `len(MEETING_PATHS) + MAX_SUBPAGES_PER_ICB`), and `MAX_DOCS_PER_ICB`
   ≈ 400 — an ICB with ~6 committees × ~8 meetings/year × ~10 documents over a
   multi-year back-catalogue reaches a few hundred on the *first* run, then
   `--since` holds routine runs to a meeting or two (§8). Hitting the ceiling
   is logged as `icb_doc_ceiling_reached` so it is visible rather than a silent
   truncation (roadmap W-06's lesson).

## 6. Subject indexing — ranks the worklist, never gates capture

Every captured document is read and indexed (§2a). The subject index decides
only what a reviewer sees first, not what is stored. For each candidate
document:

- Read it with `m28._read_pdf` / `m28._read_docx` (PDF text, OCR fallback for
  scans behind `OCR_ENABLED`, stdlib DOCX parser — no new dependency). `.doc`
  and `.odt` are recorded and left as a `parse_failures` row, as in m28.
- `subject_hits` = `m28.index_concern_terms(text)` **plus** a substance-misuse
  pass using `keywords.SUBSTANCE_MISUSE_KEYWORDS`. Store per-term counts in
  `icb_paper_subject_terms`.
- `provider_mentions` = `m28.find_provider_mentions(text)` (whole-token match
  against `SUPPLIER_NAME_VARIANTS`, with the same `cgl` / `via` / `inclusion`
  unsafe-variant guard). Store in `icb_paper_provider_mentions`.
- For every subject-term hit, store a windowed snippet (± ~300 chars) in
  `restricted_icb_paper_snippets`.

Every document is written to `icb_board_paper_candidates` with its archived
bytes and extracted text, whatever its `subject_hits`. A row with
`subject_hits = 0` and `provider_mentions = 0` is simply not surfaced in the
review worklist — `docs/verification/icb_board_papers.md`, grouped by NHS
region like m09's, listing rows where the text touches the sector, ranked by
hit count and newest meeting first. The rest stay captured and queryable; a
later campaign question ("did any ICB discuss the recommissioning?") runs
against the full text, not just the pre-filtered slice.

## 7. The promotion gate

Nothing auto-promotes. `icb_board_paper_candidates` → `icb_board_papers` is the
same human step as m09/m10/m32: a reviewer opens the document, confirms the
mention is real and relevant, and promotes via the admin UI / documented SQL,
which records who and when in `review_decisions`. Database triggers
(`migrations/0030`) already enforce "no evidence without a person"; this
module adds no path around them.

Rationale for keeping even a clearly-relevant document behind the gate: the
value of an ICB paper here is contested by construction (§1). A person deciding
"yes, this Quality Committee report is about the drug-treatment provider's
staffing" is exactly the judgement the project refuses to automate.

"Capture all documents" (§2a) does not weaken this. The whole corpus is
*collected* — archived, text-extracted, indexed, queryable — but "collected"
and "evidence" are different states, and the gap between them is the person.
The archived pile is a research aid; `icb_board_papers` is the citable set.

## 8. Provenance, dedupe, `--since`

- Every row carries `source_url`, `retrieved_at`, `http_status`,
  `source_system` (`"icb_websites_governance"`), `payload_sha256`; bytes
  archived under `data/raw/` by the shared client.
- **Dedupe / skip:** an `_already_processed(conn, url)` check in m28's shape —
  a row with `has_body_text = 1` is settled; a row with `has_body_text = 0`
  whose extension is still unreadable is settled; anything else is retried
  (so a document that failed to parse gets another go when the reader
  improves).
- **`--since` is supported here**, unlike m28/m32, because ICB governance
  documents *do* carry a reliable meeting date in the link text.
  `module_meta.supports_since = True`; `ctx.is_before_since(meeting_date)`
  skips old documents on routine runs. This matters more now that scope is all
  committees: a board pack is 5–20 MB, an ICB back-catalogue across ~6
  committees over several years is **hundreds of documents and low GBs** on
  the first run, and re-fetching them nightly is real crawl time and real
  `data/raw/` growth (roadmap P-02). The full listing is still walked every
  run to notice additions; only the *fetch* of an already-old, already-seen
  document is skipped. First run is the expensive one — expect it to take a
  while and land a lot; steady state is a handful of new documents a week.

## 9. robots.txt

NHS `*.icb.nhs.uk` sites vary. A disallow on a governance path or the asset
directory is recorded as `icb_paper_robots_disallowed` and the ICB is left
countable, exactly as m32 does. If a batch of ICBs block the asset directory
their PDFs sit in (m32 hit seven such SAB hosts), add them to
`Settings.robots_exceptions` as a named batch with the same justification the
council batches carry — not silently.

## 10. Wiring

| | |
|---|---|
| Module | `pipeline/modules/m34_icb_board_papers.py`, `@register_module("m34_icb_board_papers", supports_since=True, since_note="governance documents carry a meeting date; an already-seen old document is not re-fetched")` |
| Registry spine | `pipeline/icb_boards.py` (hand-verified, code-reviewed) |
| Depends on | nothing hard. `region` on `integrated_care_boards` comes from the directory, so no m00 dependency. |
| Reuses | `m28._read_pdf`, `m28._read_docx`, `m28.index_concern_terms`, `m28.find_provider_mentions`, `m28.document_extension`; `parallel.fetch_in_parallel` / `worker_count`; `providers.seed_providers` |
| CAVEATS | new `### ICB board papers (Module 34)` section — leads with §1 here: not a commissioner of these services, mentions are context not figures, no attribution of ICB→LA, no arithmetic |
| SOURCES.md | new row + Module 34 block. Licence: **OGL v3.0** (NHS ICB board papers), stated per-document-checkable like the council rows |
| `pipeline/licences.py` | one entry, `m34_icb_board_papers` → OGL v3.0, so exports carry the `# licence:` line (roadmap W-10) |
| Portal | admin-only. No `/api/v1/*` route, no `public_queries.py` edit, no `static/public/**` edit — `tests/test_portal_isolation.py` stays green. Surfacing on the portal is a later, separate decision. |

## 11. Open questions — answer before building

1. **Directory source for the 42-body seed.** NHS England's "integrated care
   in your area" page (recommended — one page, all 42, stable), the nhs.uk
   postcode-lookup page the request pointed at (it is a widget, not a list),
   or skip the directory fetch entirely and let `icb_boards.py` be the sole
   source of truth (simplest; loses automatic drift detection)?

2. **Does "all documents" stop at the governance section, or take the whole
   site?** §2a draws the line at meetings/governance — Board and all
   committees, every agenda / report / minute / enclosure. The alternative is
   to also sweep the ICB's general `/publications` library (strategies, JSNAs,
   annual reports, board-assurance frameworks). That roughly doubles the
   corpus and much of it is not meeting material. Recommendation: governance
   section for the first build; add a `PUBLICATION_PATHS` sweep as a second
   pass if the governance corpus proves worth maintaining. Say if you want the
   whole library from the start.

3. **First-run size check.** Before the full 42-ICB run, crawl 3–4 ICBs
   (Nottingham and Nottinghamshire, plus two on different CMS platforms) and
   record: pages reached, documents found, total MB, how many mention the
   sector, how many name a provider, and whether `MAX_DOCS_PER_ICB` was hit.
   This sets the real path list (§5.1), the ceiling, and whether the module is
   a priority or a background nice-to-have — and the number goes in the
   roadmap either way.

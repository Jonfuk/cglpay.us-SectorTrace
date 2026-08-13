# Review queue: making 4,762 decisions tractable

Proposal, 2026-08-13. Nothing here is built. Every number below was measured
against the real warehouse; every URL pattern was probed through the pipeline's
own `check-url` endpoint, so robots and rate limits applied.

## 1. What the queue actually contains

4,762 pending items, and three types are 89% of them:

| Items | Type | What the reviewer must decide |
|------:|------|-------------------------------|
| 2,667 | `m01 unmatched_buyer_name` | Is this contract buyer one of our 347 English authorities? |
| 1,067 | `m08 pfd_concerns_in_pdf_only` | — (see §5: this is not a decision) |
| 493 | `m04 possible_group_company` | Is this company part of the provider group? |
| 102 | `m15 foi_response_text_not_retrievable` | — (see §5) |
| 97 | `m10 committee_url_unknown` | Where does this council publish committee papers? |
| 336 | 28 other types | various |

**Every raw value is distinct.** The dedupe ratio is exactly 1.0 for every
type above 20 items, so there is no "decide once, apply to 50 copies" shortcut
hiding in here. The leverage has to come from somewhere else.

## 2. The biggest lever: most of the largest category is not a judgement call

The 2,667 unmatched buyer names are buyers on Find a Tender that did not match
an English local authority. Sampling shows why — most of them are not English
local authorities and never could be:

| Count | Cluster | Verdict |
|------:|---------|---------|
| 1,378 | NHS bodies (trusts, ICBs, health boards) | reject |
| 235 | universities, colleges, schools, academies | reject |
| 194 | housing associations, Ltd/PLC/CIC | reject |
| 182 | **looks like a council** | **real work** |
| 169 | police, fire, crime commissioners | reject |
| 81 | central government departments and agencies | reject |
| 159 | Scotland / Wales / Northern Ireland | reject |
| 508 | none of the above | mixed; needs eyes |

Roughly **2,000 of 2,667 are near-certain rejects** reachable in about eight
sweeps, and the genuine judgement collapses to the ~182 council-shaped names
plus whatever the 508 contains.

**The machinery for this already exists.** "Reject all matching" acts on the
current filter, so searching `Integrated Care Board` and rejecting all matches
already works today. What is missing is *knowing the clusters are there*.

> **Suggestion 1 — a cluster panel above the queue.** For the current filter,
> show the most common distinguishing tokens with counts, each a one-click
> filter: `NHS (1,378)`, `Council (182)`, `University (235)`… Clicking sets the
> search box; the existing match bar then offers "Reject all 1,378 matching".
> Server-side this is one `GROUP BY` over a token list; no new write path.
>
> Keep the counts honest: they describe the filter, not the queue, and the
> existing decide-matching confirmation (which re-counts inside the
> transaction) stays exactly as it is.

## 3. Direct links: stop making the reviewer leave the page

This is the request that prompted the proposal, and the queue is worse than it
needs to be here — several items already carry a usable URL, but it is inside
a JSON blob rendered as a `<pre>`.

Probed through `/api/check-url`:

| Item type | Link available | Derived from | Probe |
|---|---|---|---|
| `pfd_concerns_in_pdf_only` | judiciary.uk report page | `context.report_url` — **already absolute** | **200** |
| `unmatched_tribunal_respondent` | gov.uk decision page | `https://www.gov.uk` + `context.link` | **200** |
| `possible_group_company` | Companies House page | `…company-information.service.gov.uk/company/{number}` from `raw_value` | **200** |
| `foi_response_text_not_retrievable` | WhatDoTheyKnow body page | `context.wdtk_body_url` — already absolute | 403 to bots; fine in a browser |
| `unmatched_buyer_name` | Find a Tender notice | `…/Notice/{notice_id}` | 403 to bots; **pattern unverified — check by hand once** |

The tribunal case is exactly the problem described: the pipeline stores
`/employment-tribunal-decisions/mr-d-lee-v-…` and fetches it against
`https://www.gov.uk/api/content`, so the **API** path is what a reviewer sees
and the human page — one string concatenation away — is what they need.

> **Suggestion 2 — render context as fields, not JSON.** Replace the `<pre>`
> with a small table: one row per key, values as text, and known keys
> upgraded:
> - anything that is already an `http(s)` URL becomes a link (the existing
>   `maybeLink` rule — a database value never decides what a click does);
> - `link` on a tribunal item becomes `https://www.gov.uk{link}`;
> - `raw_value` on a company item becomes a Companies House link;
> - `notice_id` becomes a Find a Tender notice link;
> - `provider_key`, `ons_code`, `case_number` become internal jumps to the
>   relevant table, reusing the Phase 5 jump-link machinery;
> - `note` is prose and renders as prose, not as a quoted JSON string.
>
> A per-type link builder in one small module, so adding a type is one entry
> and the rules are reviewable in one place. Raw JSON stays available behind a
> toggle — it is the ground truth and hiding it entirely would be worse.

## 4. Bring the answer to the reviewer

Beyond links, a lot of what a reviewer would go and look up is already in the
warehouse or one join away.

> **Suggestion 3 — an evidence panel per item.** Server-side enrichment, one
> function per item type, returned by `/api/review/{id}`:
>
> - **`unmatched_buyer_name`**: the contract this came from —
>   title, value, publication date, buyer name as printed. The join
>   (`contracts.notice_id = context.notice_id`) works today. Note it is
>   one-to-many: 2,667 items join to 4,205 contract rows, so show the count and
>   the most recent, not a silent "the" contract.
> - **`possible_group_company`**: the provider's *known* variants and
>   identifiers, next to the candidate name, so "is this the same entity?" is a
>   comparison rather than a memory test. We hold nothing about the candidate
>   company itself — 0 of 400 sampled have a `companies` row — which is
>   precisely why the Companies House link matters.
> - **`committee_url_unknown`**: the authority's name, region, and any URL
>   already recorded for it. The resolve form with live `check-url` already
>   exists for these; it just needs the authority's identity beside it.
> - **`unmatched_ndtms_area` / `unmatched_nhs_jobs_employer`**: the nearest
>   candidates from `authorities` / `providers`.

> **Suggestion 4 — candidate matches, scored, never pre-selected.** For the
> ~182 council-shaped buyer names, strip `City/County/Borough/District/Council`
> and fuzzy-match against `authorities.name`. It works well:
> `The Royal Borough of Kensington & Chelsea` → *Kensington and Chelsea*;
> `Borough of Telford & Wrekin` → *Telford and Wrekin*.
>
> **It also fails dangerously.** `South Ayrshire Council` → *South Derbyshire*
> and `North Ayrshire Council` → *North Yorkshire*, both confidently and both
> wrong — Ayrshire is Scottish and has no English match at all. So: detect
> nation first and suppress suggestions for non-English names; always show the
> score; never pre-tick anything; and label it "candidates", not "match". A
> suggestion that is right 90% of the time and silently wrong 10% of the time
> is worse than none in an evidence base whose whole claim is that its figures
> can be checked.

## 5. A structural observation: the queue mixes decisions with notifications

`pfd_concerns_in_pdf_only` (1,067) says *"matters of concern are in a PDF not
linked in the REST content"*. `foi_response_text_not_retrievable` (102) says
*"needs /request/<slug>.json, which answers automated clients with a
Cloudflare 403"*.

Neither is a judgement a human can make. Approving one asserts nothing;
rejecting one discards nothing. They are the pipeline telling its operator
that a source shape defeated it — closer to `parse_failures` than to
`review_queue` — and together they are **25% of the queue**, permanently
pending, diluting the count that the Overview tab leads with.

They differ in one important way, though, and it decides what to do about
each. The FOI one is a wall: WhatDoTheyKnow answers automated clients with a
Cloudflare 403, and no amount of parsing gets past that. The PFD one is not a
wall — the report exists, it is public, and it is a PDF the pipeline has
simply not gone and read. So one gets hidden and one gets fixed.

> **Suggestion 5 — separate the not-decidable.** The cheapest honest version is
> a UI-only grouping: mark those item types as informational, default the queue
> filter to exclude them, and show them under their own heading with a count.
> No schema change, no decisions recorded that mean nothing.

> **Suggestion 6 — fetch the PDF in m08.** *(Built, 2026-08-13.)*
>
> **Measured correction to the estimate below.** The PDF text layer alone does
> not retire 1,067 items. Sampling twelve against the live source found
> **seven whose PDF is a scan with no text layer** — paper, mostly 2014 to
> 2018. Five of twelve yielded their concerns from the text layer, so that
> route is worth **around 445 of 1,067**.
>
> **OCR covers the rest** (`uv sync --extra ocr`, `OCR_ENABLED=true`), which on
> the sample would take the total to substantially all of them. It is off by
> default: about nine seconds a page puts the backlog at several hours of CPU,
> and that is a choice rather than a side effect of installing a package.
> Reports it still cannot read keep a `reason` saying why.
>
> It is not a download. The PDF link is not in the REST content, so the module
> has to fetch each report's HTML page and find the PDF href there, then fetch
> the PDF: roughly **2,134 requests at 2s/host, so about 70 minutes of
> crawling** on top of the current run. `pdfplumber` and `pipeline/pdftext.py`
> already exist, and the extraction that follows is the module's own — the
> existing `_MATTERS_RE` and `_SENT_TO_HEADER_RE` apply unchanged to PDF text.
>
> What makes this a careful change rather than a mechanical one is that m08 is
> the module with the strictest personal-data handling in the pipeline, and PDF
> text arrives with none of the protections the REST content had:
>
> - full body text goes to `restricted_pfd_report_text`, never to a public
>   column and never to an export;
> - `redact_name()` must run on the extracted matters of concern before they
>   reach the public column — the deceased is named in roughly one report in
>   twenty, and in the body text far more often than in the header;
> - **and it had to be strengthened to do it.** `redact_name` removed the full
>   name and the surname, which was enough for the structured REST stub and is
>   not enough for coroner prose. The first real PDF read said *"As a result
>   Kay was not referred to a senior medical practitioner"* — the forename,
>   into a public column. 1,056 of the 1,059 affected reports have a forename
>   that would have survived. It now removes every part of the name longer
>   than two characters, at the cost of over-redacting the 18 deceased called
>   Mark, Rose, May, June or Joy. That is the right way round to fail here;
> - the deceased's name comes from the report header, so a PDF whose header
>   does not parse gives nothing to redact *with*. That case must record a
>   parse failure and store nothing public, rather than storing unredacted
>   text on the assumption there was no name in it;
> - `robots.txt` for the PDF path is checked by the HTTP client already, and a
>   refusal is recorded as blocked rather than overridden.
>
> **The 1,067 existing items will not clear themselves.** They stay pending
> until someone decides them — `record_review_item` deduplicates, so a re-run
> neither adds nor removes. Once the extraction lands they are stale, and the
> honest close is a single bulk rejection with a note naming the change that
> superseded them. The queue keeps the record; it just stops asking.

## 6. Flow, once the content is right

Smaller, but they compound over hundreds of items:

- **Prefetch the next page.** At 50 per page a reviewer hits a wait every 50
  decisions; the next page can be in memory before it is asked for.
- **Session progress.** "37 decided this session, 2,630 left in this filter" —
  a queue this size needs to show that it is moving.
- **`?` opens the keyboard map.** The shortcuts exist and are documented in a
  line of small grey text at the bottom of the tab.
- **Open-in-new-tab from the keyboard.** If the item has a primary link, one
  key opens it; a reviewer working the queue should never need the mouse.
- **A note that persists across a sweep.** Bulk rejecting 1,378 NHS bodies
  deserves one reason recorded once — the note field already does this; it
  just needs to be obvious and to remember the last value.
- **Undo already exists** (Phase 5) and covers the "wrong key" case, including
  after a bulk decision.

## 7. What I would build first

| Order | Work | Effort | Why |
|---|---|---|---|
| 1 | Context as fields + derived links (§3) | small | Fixes the stated problem; helps every one of the 4,762 |
| 2 | Cluster panel (§2) | small | Turns ~2,000 items into ~8 decisions using write machinery that already exists |
| 3 | Not-decidable grouping (§5, suggestion 5) | small | Removes from view the 25% no human can action |
| 4 | **m08 fetches the PDF, and OCRs the scans** (§5, suggestion 6) — **built** | medium–large | Extracts the evidence instead of asking about it. ~445 from the text layer; OCR reaches the rest when switched on |
| 5 | Evidence panel (§4, suggestion 3) | medium | Removes the second lookup for the items that remain |
| 6 | Scored candidates (§4, suggestion 4) | medium | Only worth it after 1–4; the residue is ~182 items |
| 7 | Flow polish (§6) | small each | Compounding, but pointless before the content is right |

Doing 1–3 first is deliberate: they need no new write paths, no schema change,
and no judgement about what a name means.

**Item 4 is the only one that is not UI work**, and it touches the pipeline
rather than the web layer, so it can proceed in parallel with 1–3 without
either waiting on the other. It does change what 3 is worth: with the m08
concerns extracted, the not-decidable grouping covers the remaining ~130 FOI
and blocked-source items rather than 1,169, so build 3 as the small honest
thing it is and do not size it around a category that is on its way out.

Together these should take the queue from 4,762 undifferentiated items to a
few hundred that genuinely need a person.

## 8. What I would not build

- **Auto-deciding anything.** Not even the 1,378 NHS bodies. The pattern is a
  filter that helps a person decide in bulk; a rule that decides on its own
  puts an unreviewed judgement into an evidence base whose value is that every
  judgement has a name against it.
- **A "confidence" score that drives a default.** See the Ayrshire failures.
- **Editing raw values.** The queue records what a source said; correcting it
  here would make the warehouse disagree with the document it cites.

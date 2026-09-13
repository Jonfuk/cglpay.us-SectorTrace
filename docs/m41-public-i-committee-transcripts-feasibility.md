# Council webcast/transcript techniques feasibility (JON-11)

**Status: feasibility only. No code, migration or module changed.** Written
against commit `5fece46ae1d63fef596e5e35f49fb2384f8198d3` with a clean tree.
JON-11 is labelled `Post-V1` / `Not scheduled`, and its own outcome asks for
feasibility, access terms, provenance, an integration approach and draft
acceptance criteria **before implementation** — not an implementation. This
document proposes a candidate module number `m41_committee_webcast_transcripts`
(numbering to be confirmed at build time, not reserved here) rather than
folding the work into `m10_committee_papers`, for reasons given in §7.

**This document could not be finished to the standard `docs/m39-360giving-grantnav-feasibility.md`
sets — verifying every claim against the live source, not a summary of it —
because the two primary sources named by the ticket, `public-i.tv` and
`opencouncil.network`, are both blocked at the network-egress layer in the
environment this document was written in** (`CONNECT` to `www.public-i.tv:443`
and `opencouncil.network:443` both returned HTTP 403 from the egress gateway,
confirmed via the proxy's own status endpoint, not merely a failed request).
Everything below marked "verified" was checked against a reachable primary
source (chiefly the open-source scraper's own code on GitHub, which is not
blocked); everything marked "not verified here" is a named gap for whoever
next has unrestricted network access, not a guess filled in to complete the
document. Search-engine summaries of blocked pages are cited separately from
verified fact and are not treated as equivalent to it.

## 1. What already exists (read before proposing anything new)

| Piece | What it gives this ticket | Where |
|---|---|---|
| `m10_committee_papers` | The precedent this ticket's own wording invokes: one adapter per committee system (ModernGov, CMIS), committee URL discovered from a verified registry or a homepage link, candidates only, nothing promoted without a human | `pipeline/modules/m10_committee_papers.py` |
| `restricted_committee_result_snippets` | The existing precedent for keeping matched free text that names officers out of anything exportable | `pipeline/migrations/postgres/0020_committee_search.sql` |
| `pipeline/promote.py`, migration `0030` | Enforces settled decision 4 (a person promotes candidates to evidence) at the database level; any transcript-derived table needs the same trigger discipline, not a new bypass | `pipeline/promote.py`, `pipeline/migrations/postgres/0030_evidence_promotions.sql` |
| `pipeline/authority_websites.py` | The confirmed-URL registry `m10` reads for its committee_url; a webcast provider is a **different** URL family (see §2) and needs its own column or table, not a repurposing of `committee_url` | `pipeline/authority_websites.py` |
| `pipeline/licences.py`'s `authority_varies` / `three_sixty_giving_varies` pattern | The precedent for a licence that is not one string — a webcast transcript's rights position (§6) needs the same per-source, not per-module, treatment | `pipeline/licences.py` |
| `pipeline/keywords.COMMITTEE_SEARCH_TERMS` | Reusable directly: the same commissioning/staffing/pay terms `m10` already searches document titles for apply unchanged to transcript text | `pipeline/keywords.py` |

**This ticket does not touch `m10`'s ModernGov/CMIS code.** A webcast
transcript module would run alongside it, matched to the same authority by
`ons_code`, not by editing what `m10` already does.

## 2. What "CouncilSearcher", "Public-i" and "Open Council Network" actually are — three different things

The ticket's phrasing ("CouncilSearcher/Public-i adapters") reads as if these
name one system. Verified separately, they are three:

1. **Public-i** (`public-i.tv`) — a commercial webcasting vendor supplying AV
   services (live streaming, archived video, "meeting transcription/
   subtitles") to UK and Ireland councils. This is the actual data source: the
   council's meeting video, and a machine-generated transcript alongside it.
   Public-i is the provider `m10`'s own ModernGov/CMIS adapters have no
   relationship to — a council can run ModernGov for its agenda papers and
   Public-i for its webcasts, or either alone, or neither.
2. **CouncilSearcher** (`github.com/bellingcat/CouncilSearcher`) — not a data
   source at all. It is Bellingcat's own open-source scraper and search UI
   (FastAPI + SQLite backend, Vue/Vuetify frontend, MIT-licensed code) that
   currently implements exactly one provider adapter, `PublicI`, and states in
   its own docs that it "welcomes contributions... particularly for expanding
   provider support beyond the current Public I implementation." Reading its
   provider code is how §3 below was verified without needing to reach
   `public-i.tv` directly for the technique itself — but the code says nothing
   about Public-i's terms, robots.txt, rate limits or the licence status of
   the transcript text it fetches, none of which this document could verify
   (they require reaching `public-i.tv`, which this session could not do).
3. **Open Council Network** (`opencouncil.network`) — a separate project
   (per its own search-indexed description) that publishes summaries, videos
   and transcripts of UK council meetings, framed by the ticket as "a parallel
   historical corpus" with stable meeting/document/page IDs. This document
   could not reach `opencouncil.network` at all (blocked, per the header) and
   has **no verified facts about it** to report — not its ID scheme, not its
   licensing, not whether it exposes an API versus an HTML site this
   pipeline's robots-respecting client would have to scrape. This is a named
   gap for the next verification pass, not assessed further here.

## 3. Verified: the actual Public-i transcript retrieval technique

Read directly from `api/providers/publici.py` and `api/providers/provider.py`
in the CouncilSearcher repository (commit reachable via
`raw.githubusercontent.com`, itself not blocked). This is the one piece of
the ticket verified against a primary source rather than a summary.

Each Public-i customer is hosted on its own subdomain,
`https://{authority}.public-i.tv`. The scraper's sequence:

1. `GET https://{authority}.public-i.tv/core/portal/magic_rss` — an HTML page
   whose only purpose to the scraper is to yield a hidden form field,
   `<input name="ds_id" value="...">`, which is that council's internal
   Public-i tenant ID (`ds_id`, called `authority_id` in the code).
2. `GET https://{authority}.public-i.tv/core/data/{authority_id}/archived/1/agenda/1`
   — an RSS/XML feed of archived meetings. Each `<item>` carries `title`,
   `description`, a `pi:tags` field, `pi:liveDate` (parsed as
   `"%a, %d %b %Y %H:%M:%S %z"`), a `guid` (the meeting's own webcast URL,
   whose last path segment is a UID), and a `pi:agenda` block of
   `pi:agenda_item` entries each with `pi:agenda_id`, `pi:agenda_text` and
   `pi:agenda_time` — i.e. **the RSS feed itself already links each meeting to
   its agenda item list**, which directly answers the ticket's "link
   timestamped transcript segments to meetings [and] agendas" requirement
   before the transcript is even fetched.
3. `GET https://cl-assets.public-i.tv/{authority}/subtitles/{authority}_{uid}_en_GB.vtt`
   — a WebVTT caption file, one per meeting, templated from the authority
   name and the UID taken from the RSS item's `guid`. WebVTT is inherently
   timestamped (`HH:MM:SS.mmm --> HH:MM:SS.mmm` cue blocks), which is what
   would let a segment be linked to a point in the meeting rather than only
   to the meeting as a whole.

None of this required an account, API key, or authenticated session in the
scraper's own code — every request shown above is a plain unauthenticated
`GET`. **Not verified**: whether `public-i.tv` publishes a `robots.txt`, what
it says, whether these paths are within it, what rate limiting (if any) the
server enforces, and what Public-i's or the commissioning council's terms say
about redistributing the transcript text. All four are blocking questions for
settled decision 5 (politeness) and decision 1 (provenance) and none could be
checked from this session.

## 4. Coverage — genuinely unknown from here

Public-i's own marketing copy (found via search, not fetched directly —
see caveat in §1's header) describes itself as serving "many councils in the
UK and Ireland" and states that transcription/subtitling has used an updated
AI engine for recordings since 2024-09-26, with older archives presumably
using whatever came before. **No verified count of which UK councils are
current Public-i customers exists in this document.** CouncilSearcher does
not hardcode a customer list — the `authority` is a per-deployment operator
input matching a subdomain, not something the code enumerates — so the
customer list is not recoverable from the tool's source and would need
either a request to Public-i, a review of individual council procurement/
webcast pages, or a reachable `opencouncil.network`/similar directory. This
is the same "capture, not a census" caveat this pipeline already carries for
`m23_sector_universe`, but here it applies to the coverage question itself,
before any collection design.

The ticket's own text separately flags "commercial snapshot-based bulk
exports" reported by an unspecified module audit, to be verified for
"coverage, licence and cost before procurement or ingestion." **No such
named product was identified by this document's research.** Search did not
surface a specific commercial provider selling bulk snapshot exports of UK
council webcast transcripts (as distinct from unrelated corporate-meeting
transcript exporters, or the unrelated US MeetingBank academic dataset).
This claim in the ticket is one the ticket's own preamble already marks as
requiring verification ("source claims and repository state require
verification") — this document does not resolve it and the specific product
name needs to come from whoever wrote the audit, not from search.

## 5. Data shape and the caption-vs-generated-transcription distinction the ticket asks for

WebVTT gives per-cue start/end timestamps and text, but **the file itself
does not self-report whether a given council's transcript is a
publisher-supplied caption or Public-i's automatic transcription** — that
distinction, which the ticket explicitly asks this work to preserve, is a
property of Public-i's own pipeline for that specific recording (their
"AI Innovations" announcement implies automatic transcription is the default
and improved arrangement from 2024-09-26 onward, not an opt-in human
captioning service), not something visible in the cue text. Unless Public-i
exposes a field or a page distinguishing the two — unverified here, since
`public-i.tv` could not be reached — a module ingesting these transcripts
would have to **record every transcript as machine-generated by default and
say so in its provenance**, rather than assume caption quality, consistent
with `m10`'s own treatment of ModernGov's `match_quality` as a triage
signal and never a fact this pipeline asserts on the source's behalf
(`docs/CAVEATS.md`).

Speaker attribution inside a transcript (who said what) is the same personal
data problem `m10` already isolates in
`restricted_committee_result_snippets`, at materially larger scale: a whole
meeting transcript routinely names councillors, officers by role and name,
and members of the public who spoke during public-participation slots — not
one matched snippet per document, but the full running text. Settled
decision 3 (personal data in `restricted_` tables, excluded from every
export) applies at that scale from the first row, not as a later add-on.

## 6. Access terms, licensing and provenance — mostly open questions

- **No account or API key was required by any request CouncilSearcher's code
  makes** (§3) — but that is evidence about the technical shape of the
  requests, not a statement about whether making them at production scale is
  within Public-i's or the commissioning council's terms. A commercial
  webcasting vendor's willingness to serve an unauthenticated `GET` is not
  the same thing as a licence to redistribute the resulting transcript text,
  and this document found no terms-of-service, licence or copyright page
  content to report either way, because `public-i.tv` was unreachable from
  this session.
- **robots.txt is unverified.** `m10` and the shared HTTP client both depend
  on reading and honouring it (settled decision 5); this document cannot
  confirm what it says for `public-i.tv`, `cl-assets.public-i.tv`, or any
  individual authority subdomain.
- **Rate limiting is unverified.** No published number was found; the
  scraper's own code makes concurrent thread-pooled requests with no visible
  throttling, which is not evidence of what the server tolerates, only of
  what one uncredited open-source tool currently gets away with.
- **The transcript's copyright/licence position is unverified.** A council's
  own committee papers are typically republished under an open licence the
  council states (the `authority_varies` pattern `m10` and `m24` already
  use); whether a Public-i-hosted transcript of a public meeting carries the
  same status, a Public-i-specific licence, or no stated licence at all is
  not established here.
- **Provenance, if this proceeds, is straightforward relative to the above**:
  the RSS `guid` gives a stable per-meeting source URL, the VTT URL is itself
  the fetched artefact to archive under `data/raw/` with its SHA-256, and
  `pi:liveDate` gives a real meeting date — the mechanics settled decision 1
  needs are all present in the feed; the open question is whether fetching
  and storing the transcript text at all is permitted, which is a licensing
  and terms question, not a provenance one.

## 7. Why this reads as a new module, not an extension of `m10`

The ticket's own words ("m10: add Public-i transcript techniques") propose
folding this into the existing committee-papers module. Against what `m10`
actually is (§1, and `pipeline/modules/m10_committee_papers.py`'s own
docstring), that does not fit cleanly:

- `m10` discovers a **committee_url** (a ModernGov or CMIS instance) from
  `authority_websites.py` or a homepage link, and its whole adapter contract
  (`AuthorityFindings`, `collect_authority`, `write_findings`) is shaped
  around searching a document-management system for agenda papers by
  keyword. Public-i is a **webcast host** at an entirely different subdomain
  family (`{authority}.public-i.tv`), discovered differently (§4 — no
  verified discovery mechanism at all yet, since there is no registry
  precedent for webcast URLs), returning video/transcript records rather
  than document candidates.
- The content model differs: `committee_paper_candidates` is one row per
  document; a transcript module's natural unit is one row per meeting
  (matching the RSS item) plus, if segment-level linking is wanted, one row
  per timestamped cue or per matched-keyword cue — a materially different
  schema, not a same-shaped row with a new source column.
- `m10`'s own file history (its docstring's account of two separately fixed,
  independently wrong assumptions about ModernGov) is itself an argument for
  keeping a genuinely different provider's genuinely different technique in
  its own file: mixing Public-i's RSS/VTT logic into the same module as
  ModernGov's HTML-block parsing and CMIS's ASP.NET postback handling would
  make the next person's job of isolating a provider-specific bug harder, not
  easier.

Recommendation: a new module, evidence layer `accountability_scrutiny`
(alongside `m10`, `m34_icb_board_papers`), matched to the same `ons_code` so
a reviewer sees committee papers and webcast transcripts for one authority
together at the query layer without either module's code depending on the
other.

## 8. Draft acceptance criteria (for a future implementation ticket, not this one)

| Case | Expected result | Check |
|---|---|---|
| `magic_rss` page has no `ds_id` input | Recorded as a review item (e.g. `webcast_authority_id_not_found`), not a crash or a skipped-silently authority | Fixture HTML without the field |
| RSS feed has zero `<item>` entries | Recorded distinctly from "not configured for Public-i at all" — an authority that has a working Public-i tenant with nothing archived is a different fact than one never checked | Fixture empty-channel feed |
| A meeting's VTT fetch 404s (transcript not yet generated, or withheld) | Meeting row stored from the RSS feed; transcript fields left `NULL`, not retried indefinitely inside one run | Fixture RSS item with a dead VTT URL |
| `pi:liveDate` in an unexpected format | `NULL` plus a `parse_failures` row, never a guessed date, matching every other module's tolerant-date discipline | Fixture with a malformed date string |
| Transcript cue text names an identifiable member of the public or officer | Full transcript text goes to a `restricted_` table only; anything portal/export-reachable carries no free transcript text, only structural metadata (meeting date, agenda linkage, matched-keyword cue timestamps) | Fixture transcript with a named individual; test against `guard_columns()` |
| Same council has both a `committee_url` (`m10`) and a Public-i tenant | Both modules run independently and are joined only by `ons_code` at the query layer, never by one module reading the other's tables | Fixture authority configured for both |
| `robots.txt` disallows a path this module needs | Module records `committee_webcast_robots_disallowed` (mirroring `m10`'s `committee_search_robots_disallowed`) and does not fetch it anyway | Fixture disallow rule — **cannot be written until §6's `robots.txt` verification happens** |

## 9. Recommended next decisions (none taken here)

1. **Reach `public-i.tv` from an unrestricted network and verify `robots.txt`,
   any published rate limit, and any terms-of-service or licence statement
   covering transcript redistribution**, before any code is written. This is
   the single blocking item — everything else in this document is
   downstream of it.
2. **Reach `opencouncil.network` and repeat the same verification**,
   independently — this document has no verified facts about it at all
   (§2.3), and the ticket asks for it to be assessed as a parallel corpus,
   not assumed compatible with whatever Public-i's terms turn out to be.
3. **Name the specific "commercial snapshot-based bulk exports" product**
   the module audit referred to (§4) — this document could not identify it,
   and "verify coverage, licence and cost" cannot proceed against an
   unnamed product.
4. **Establish how a webcast tenant subdomain is discovered and confirmed**
   per authority — `m10`'s `authority_websites.py` precedent is for
   committee-management URLs specifically; a Public-i registry entry is a
   new, separate fact about an authority, not a reuse of `committee_url`.
5. **Decide the caption-vs-auto-generated-transcription default** (§5) —
   this document recommends "record everything as machine-generated unless
   Public-i's own metadata states otherwise," but that recommendation itself
   depends on decision 1's verification turning up whether such metadata
   exists.
6. **The `docs/CAVEATS.md` entry this module will need** should state, in
   its own words, that a webcast transcript is Public-i's (or its
   underlying speech-to-text vendor's) automated output unless proven
   otherwise, is a triage lead like ModernGov's `match_quality` and never
   promoted without a human, and is never combined with `m10`'s committee
   papers into one figure — they remain separate evidence layers per
   settled decision 2 even where they describe the same meeting.

## Sources

* This repository: `pipeline/modules/m10_committee_papers.py`,
  `pipeline/migrations/postgres/0020_committee_search.sql`,
  `pipeline/migrations/postgres/0030_evidence_promotions.sql`,
  `pipeline/promote.py`, `pipeline/authority_websites.py`,
  `pipeline/licences.py`, `pipeline/keywords.py`, `docs/SOURCES.md`,
  `docs/CAVEATS.md` (read 2026-09-13).
* `https://github.com/bellingcat/CouncilSearcher`,
  `https://raw.githubusercontent.com/bellingcat/CouncilSearcher/main/README.md`,
  `https://raw.githubusercontent.com/bellingcat/CouncilSearcher/main/api/providers/publici.py`,
  `https://raw.githubusercontent.com/bellingcat/CouncilSearcher/main/api/providers/provider.py`,
  `https://raw.githubusercontent.com/bellingcat/CouncilSearcher/main/.env`,
  and the `api/`, `api/providers/`, `api/config/` directory listings —
  fetched live 2026-09-13 via `raw.githubusercontent.com`/`github.com`
  (reachable; not blocked). The primary source for §3, and for the MIT
  licence and provider-extensibility claims in §2.
* Search-engine result summaries (not independently fetched — see the
  header caveat) for `www.public-i.tv/products/webcasting-services/
  meeting-transcription/`, `www.public-i.tv/products/connect-webcasting/`,
  and Public-i's 2024-10-18 "AI Innovations" post — used only for the
  general marketing description in §4/§5, explicitly not treated as
  verified fact.
* `opencouncil.network`, `council-search.bellingcat.com`,
  `www.public-i.tv` — attempted directly 2026-09-13; all three rejected at
  the network-egress layer (`CONNECT` → HTTP 403), confirmed via
  `$HTTPS_PROXY/__agentproxy/status`'s `recentRelayFailures`. No content
  from these was retrieved by this document.

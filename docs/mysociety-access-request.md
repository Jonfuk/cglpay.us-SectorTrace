# Access request to mySociety (WhatDoTheyKnow)

Status: **not yet sent** — drafted 2026-08-11, revised the same day (see
"What changed" below). **Send this before the next full collection run.**

## Why this exists

Module 15 collects mySociety's published authority CSV, the WhatDoTheyKnow
search feed, and FOI disclosure logs on councils' own websites.

Two separate things are going on, and conflating them is what made the first
draft of this letter wrong.

1. **The Cloudflare 403.** WhatDoTheyKnow's HTML request pages and its JSON
   read API (`/request/<slug>.json`, `/body/<slug>.json`, `/list/all.json`)
   return a 403 challenge to this pipeline. That is an access control and it
   is respected: no user-agent spoofing, no fingerprint impersonation, no
   challenge solving. It is also why full FOI response text is *not*
   collected — only discovery.

2. **The robots.txt exclusion.** `/feed/search/<query>.json` is not behind
   the challenge and returns 200 to this pipeline's own User-Agent. But
   mySociety's `robots.txt` disallows `*/feed/*` and `*/search/*`, so it is
   doubly excluded. It is currently fetched anyway, under a single explicit
   exception in `Settings.robots_exceptions` that logs every use and raises a
   `robots_override_in_use` review item.

Point 2 is the one this letter needs to resolve, and it is a live compliance
gap, not a hypothetical — the collection is happening now. Either mySociety
permit it, or the exception comes out.

**Do not route around the challenge in point 1.** Working implementations
exist that do (TLS fingerprint impersonation, driven browser engines), and
using one would trade a defensible corpus for a larger one — the single
easiest thing for an employer's side to attack in a pay dispute, and a good
way to get this project named publicly by mySociety. The parsing for a
granted route is already written and tested in `pipeline/alaveteli.py`, so
saying yes is the only step missing.

## What changed on 2026-08-11

The first draft said the feed was "excluded in `robots.txt`, so I have not
fetched it". That is no longer true, and sending the letter in that form
would have misrepresented the position. Two discoveries, in order:

* `/feed/search/` was never actually tested, because the exclusion was read
  off `robots.txt` by hand. Tested: it returns 200 `application/json`.
* This pipeline's robots.txt enforcement did not, at that point, honour
  wildcard rules at all — `urllib.robotparser` matches with
  `path.startswith(rule)`, so every `*`-prefixed rule on the host was
  silently ignored. mySociety write nearly all of theirs that way. The
  parser has since been replaced (`pipeline/http.RobotsRules`, RFC 9309
  matching), so the exclusion is now genuinely enforced and the exception is
  a real, deliberate, single-line override rather than an accident.

## Where to send it

Use the **WhatDoTheyKnow contact form** at
<https://www.whatdotheyknow.com/help/contact> rather than
`hello@mysociety.org` — the form routes to the volunteers who can actually
action an allowlist. (`data.mysociety.org` is their bulk-data front door if
they'd rather hand over an extract.)

## Draft

> **Subject:** Request to allowlist a research crawler / bulk data access — substance misuse sector FOI corpus
>
> Hello,
>
> I maintain a public-interest research pipeline gathering published evidence
> about the drug and alcohol treatment sector across every commissioning area
> in England, for use as a trade union pay campaign evidence base. It is a
> reproducible, fully auditable collection: every record stores its source
> URL, the time it was fetched, and the SHA-256 of the exact bytes retrieved,
> which are archived so any figure can be traced back to the document it came
> from.
>
> I already use your published authority CSV (`/body/all-authorities.csv`),
> which joins cleanly to ONS geography via your GSS tags — thank you for
> publishing it, it is the best authority register I have found, and it is
> now this pipeline's authoritative source of a website URL for all 317
> English authorities.
>
> I would also like to collect FOI requests relating to substance misuse
> commissioning, budgets and workforce. My client sends the identifying
> User-Agent below, one request per host every 2 seconds, with conditional
> requests so unchanged pages are not re-fetched:
>
> `cglpay-evidence-pipeline/0.1 (+contact: jon@jonf.uk; purpose: trade union
> pay campaign evidence gathering from public-domain sources)`
>
> **First, something I need to declare rather than ask about.** I am
> currently fetching `/feed/search/<query>.json`, roughly 35 phrase searches
> at up to 4 pages each per run, at the rate above. Your `robots.txt`
> disallows `*/feed/*` and `*/search/*`, so I should not be, and I would
> rather tell you than have you find it in a log. I have it behind a single
> explicit switch that is logged on every use, and I will turn it off
> immediately if you say so — a reply of "please stop" is a completely
> acceptable answer and needs no explanation.
>
> The reason I am asking rather than just stopping is that this endpoint is
> markedly *cheaper* for you than the alternative: it is one cached JSON
> response per 25 results, against crawling the equivalent request pages.
>
> Second, the part I have not worked around. `/body/<slug>` returns a 5.8 KB
> Cloudflare challenge page with HTTP 403, as do `/body/<slug>.json`,
> `/list/all.json` and `/request/<slug>.json`, while `robots.txt` and
> `/body/all-authorities.csv` return 200. Since your `robots.txt` permits
> `/body/` and bare `/request/`, I have taken this as a blanket edge rule
> rather than a decision about crawlers like mine, and I have made no attempt
> to defeat it — no user-agent spoofing, no fingerprint impersonation, no
> challenge solving. The practical effect is that I can see that a request
> exists and what state it reached, but never what the authority actually
> said.
>
> Could you advise on any of the following, in whichever order suits you?
>
> 1. **The feed.** Is the `robots.txt` exclusion of `*/feed/*` a deliberate
>    policy, or a side effect of excluding the HTML feeds? If you are willing
>    to permit it for this user agent, that is the smallest useful grant and
>    the one I would most like. If not, say so and it stops.
> 2. **An API key.** I see Alaveteli exposes an authenticated API under
>    `/api/v2/` with issued keys. Is there a read-side equivalent, or could a
>    key be scoped to read access for a research corpus?
> 3. **Allowlisting the user agent above** for `/body/` and `/request/`,
>    which is the only route to actual response text.
> 4. **A bulk extract**, if that suits your infrastructure better. I would
>    only need requests to English local authorities, and I am happy to work
>    to any conditions on onward use, attribution or republication.
>
> Happy to share the source, the crawler configuration, or the intended
> outputs. If the answer is no, that is genuinely fine — I would just rather
> know than keep guessing at your edge rules.
>
> Thanks for your time, and for running WhatDoTheyKnow.
>
> Jon F — jon@jonf.uk

## If they say yes

1. Set the granted route in `.env` / `pipeline/config.py`.
2. `pipeline/alaveteli.py` already parses the JSON shape — `parse_info_request`,
   `parse_authority`, `extract_response_texts` — following the NULL-and-log
   rule. Its `KNOWN_DESCRIBED_STATES` is an *observed* vocabulary; unknown
   states land in `parse_failures` rather than passing through, so check that
   table after the first real run and extend the set from what appears.
3. `foi_requests` and `foi_attachments` (migration 0019) are already shaped
   for the results.

## If they say no

Record it here with the date, then **remove the
`https://www.whatdotheyknow.com/feed/` entry from
`Settings.robots_exceptions`** — that is the switch, and with it gone the
module degrades to the authority CSV and disclosure logs on its own, logging
a `foi_feed_robots_disallowed` review item rather than failing.

Feed-derived rows already in the warehouse are identifiable by
`discovery_source = 'wdtk_feed_search'`. Decide explicitly whether to keep or
delete them; they were collected against the site's stated wishes, so keeping
them needs a reason.

The `foi_response_text_not_retrievable` review items already carry the
full-text limitation into `review_queue`, and `docs/CAVEATS.md` should then
state plainly that the FOI evidence is discovery-only.

## If they do not reply

Set a date now rather than letting silence become the answer. Silence is not
consent, and "we asked and they never replied" is a much weaker position than
"we asked, waited, heard nothing, and turned it off." Suggested: remove the
exception after 30 days without a reply.

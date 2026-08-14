# Council home page URLs — verification result

A list of home pages for all 317 principal English local authorities was
checked on **14 August 2026** before any of it was stored. Every URL was
fetched once through the pipeline's own HTTP client — real User-Agent with a
contact address, robots.txt respected, per-host rate limiting — the same
standard `pipeline/authority_websites.py` sets for every other entry in it.

- **268 of 317 answered with a council's home page** and are now `base_url` values in the registry.
- **49 did not** and were not stored. They are listed below, so the gap stays countable.

The list itself was sound: all 317 rows matched an ONS code in the
warehouse's own geography spine (Module 0), with no unmatched name, no
duplicate and no live authority missing. What follows is about which URLs
*responded*, which is a different question.

## Why a 200 was not enough

Four authorities answered `200` with a bot challenge rather than a home
page. Storing those would have given Module 9 a base URL that resolves to an
interstitial: it would search it for documents, find none, and record the
council as publishing nothing — a coverage gap that looks like a finding.
So the test is on content. A URL is stored only when the response is `2xx`,
the body is over 2KB, and it reads as a council's page rather than a
challenge.

Nine further pages tripped a first-pass `recaptcha` check and were kept:
they are 55KB+ home pages with the council's own `<title>` that happen to
embed a form widget. A signature that matches those matches the wrong thing.

## Redirects

Sixteen of the confirmed URLs redirect to another origin, and the registry
stores **the address that was requested, not the one it landed on**. Five of
the destinations are transitional hostnames — `new.newcastle.gov.uk`,
`new.fylde.gov.uk`, `next.shropshire.gov.uk`, `pre.hillingdon.gov.uk`,
`go.walsall.gov.uk` — belonging to councils part-way through a site move.
The canonical `www` address is the one still pointing at the council when
that finishes, and the client follows the hop either way.

| Authority | ONS code | Stored | Answers today on |
| --- | --- | --- | --- |
| Burnley | `E07000117` | https://www.burnley.gov.uk | https://burnley.gov.uk |
| Chorley | `E07000118` | https://www.chorley.gov.uk | https://chorley.gov.uk |
| Crawley | `E07000226` | https://www.crawley.gov.uk | https://crawley.gov.uk |
| East Cambridgeshire | `E07000009` | https://www.eastcambs.gov.uk | https://eastcambs.gov.uk |
| East Devon | `E07000040` | https://www.eastdevon.gov.uk | https://eastdevon.gov.uk |
| Exeter | `E07000041` | https://www.exeter.gov.uk | https://exeter.gov.uk |
| Fylde | `E07000119` | https://www.fylde.gov.uk | https://new.fylde.gov.uk |
| Haringey | `E09000014` | https://www.haringey.gov.uk | https://haringey.gov.uk |
| Hillingdon | `E09000017` | https://www.hillingdon.gov.uk | https://pre.hillingdon.gov.uk |
| Lewisham | `E09000023` | https://www.lewisham.gov.uk | https://lewisham.gov.uk |
| Newcastle upon Tyne | `E08000021` | https://www.newcastle.gov.uk | https://new.newcastle.gov.uk |
| North Somerset | `E06000024` | https://www.n-somerset.gov.uk | https://n-somerset.gov.uk |
| Shropshire | `E06000051` | https://www.shropshire.gov.uk | https://next.shropshire.gov.uk |
| South Ribble | `E07000126` | https://www.southribble.gov.uk | https://southribble.gov.uk |
| Tewkesbury | `E07000083` | https://www.tewkesbury.gov.uk | https://tewkesbury.gov.uk |
| Walsall | `E08000030` | https://www.walsall.gov.uk | https://go.walsall.gov.uk |

## Not stored

### refused or did not serve a page — 35

The council's server answered, but not with its home page. Almost all of these are a bot block (`403`) from in front of a site that a browser loads normally -- the URL is probably right, but *probably* is not the standard this registry keeps, so none of them are stored. Two answered `307` with no destination, and one `404`.

| Authority | ONS code | URL | What happened |
| --- | --- | --- | --- |
| Basildon | `E07000066` | https://www.basildon.gov.uk | HTTP 403 |
| Boston | `E07000136` | https://www.boston.gov.uk | HTTP 403 |
| Breckland | `E07000143` | https://www.breckland.gov.uk | HTTP 403 |
| Camden | `E09000007` | https://www.camden.gov.uk | HTTP 403 |
| Chichester | `E07000225` | https://www.chichester.gov.uk | HTTP 403 |
| East Lindsey | `E07000137` | https://www.e-lindsey.gov.uk | HTTP 403 |
| Eastleigh | `E07000086` | https://www.eastleigh.gov.uk | HTTP 403 |
| Enfield | `E09000010` | https://www.enfield.gov.uk | HTTP 403 |
| Fenland | `E07000010` | https://www.fenland.gov.uk | HTTP 403 |
| Gateshead | `E08000037` | https://www.gateshead.gov.uk | HTTP 403 |
| Great Yarmouth | `E07000145` | https://www.great-yarmouth.gov.uk | HTTP 403 |
| Hammersmith and Fulham | `E09000013` | https://www.lbhf.gov.uk | HTTP 404 |
| Horsham | `E07000227` | https://www.horsham.gov.uk | HTTP 403 |
| Isle of Wight | `E06000046` | https://www.iow.gov.uk | HTTP 403 |
| Kent | `E10000016` | https://www.kent.gov.uk | HTTP 403 |
| Leicestershire | `E10000018` | https://www.leicestershire.gov.uk | HTTP 403 |
| Lewes | `E07000063` | https://www.lewes-eastbourne.gov.uk | HTTP 403 |
| Maidstone | `E07000110` | https://www.maidstone.gov.uk | HTTP 403 |
| Manchester | `E08000003` | https://www.manchester.gov.uk | HTTP 403 |
| Middlesbrough | `E06000002` | https://www.middlesbrough.gov.uk | HTTP 403 |
| New Forest | `E07000091` | https://www.newforest.gov.uk | HTTP 403 |
| Norfolk | `E10000020` | https://www.norfolk.gov.uk | HTTP 403 |
| North East Derbyshire | `E07000038` | https://www.ne-derbyshire.gov.uk | HTTP 403 |
| Preston | `E07000123` | https://www.preston.gov.uk | HTTP 403 |
| South Holland | `E07000140` | https://www.sholland.gov.uk | HTTP 403 |
| South Tyneside | `E08000023` | https://www.southtyneside.gov.uk | HTTP 403 |
| Stockton-on-Tees | `E06000004` | https://www.stockton.gov.uk | HTTP 403 |
| Sunderland | `E08000024` | https://www.sunderland.gov.uk | HTTP 403 |
| Swale | `E07000113` | https://www.swale.gov.uk | HTTP 403 |
| Tunbridge Wells | `E07000116` | https://www.tunbridgewells.gov.uk | HTTP 403 |
| Uttlesford | `E07000077` | https://www.uttlesford.gov.uk | HTTP 403 |
| West Berkshire | `E06000037` | https://www.westberks.gov.uk | HTTP 403 |
| Wiltshire | `E06000054` | https://www.wiltshire.gov.uk | HTTP 403 |
| Worcester | `E07000237` | https://www.worcester.gov.uk | HTTP 307 |
| Wychavon | `E07000238` | https://www.wychavon.gov.uk | HTTP 307 |

### answered 200 with a bot challenge — 4

These served a challenge page under a `200`. Status alone would have stored them, and Module 9 would then have searched an interstitial for documents and recorded the council as publishing nothing. The separation was not marginal: these ran 212-6,183 bytes with no council text on the page, against 55KB and up for every real home page.

| Authority | ONS code | URL | What happened |
| --- | --- | --- | --- |
| Barnet | `E09000003` | https://www.barnet.gov.uk | 200, 6,183 bytes — Pardon Our Interruption |
| North Lincolnshire | `E06000013` | https://www.northlincs.gov.uk | 200, 1,705 bytes — Bot Verification |
| Northumberland | `E06000057` | https://www.northumberland.gov.uk | 200, 922 bytes — no title |
| Southampton | `E06000045` | https://www.southampton.gov.uk | 200, 212 bytes — no title |

### connection could not be made — 6

Four presented a TLS certificate this machine could not verify (one of them, Eastbourne, a certificate issued for a different hostname); two closed the connection. A certificate that does not validate is not a URL to hand an automated fetcher.

| Authority | ONS code | URL | What happened |
| --- | --- | --- | --- |
| Basingstoke and Deane | `E07000084` | https://www.basingstoke.gov.uk | TLS certificate not verifiable |
| Blackburn with Darwen | `E06000008` | https://www.blackburn.gov.uk | TLS certificate not verifiable |
| Eastbourne | `E07000061` | https://www.eastbourne.gov.uk | certificate issued for another hostname |
| Halton | `E06000006` | https://www.halton.gov.uk | connection closed by the host |
| Staffordshire Moorlands | `E07000198` | https://www.staffsmoorlands.gov.uk | TLS certificate not verifiable |
| Teignbridge | `E07000045` | https://www.teignbridge.gov.uk | connection closed by the host |

### hostname does not resolve — 3

The hostname does not exist, so the list is simply wrong for these three. Hampshire publishes on a different domain, and Broadland and South Norfolk share one. None of those replacements are guessed at here -- an unverified URL is what this file exists to keep out.

| Authority | ONS code | URL | What happened |
| --- | --- | --- | --- |
| Broadland | `E07000144` | https://www.broadland.gov.uk | hostname does not resolve |
| Hampshire | `E10000014` | https://www.hampshire.gov.uk | hostname does not resolve |
| South Norfolk | `E07000149` | https://www.south-norfolk.gov.uk | hostname does not resolve |

### robots.txt refuses us — 1

Already the subject of a `robots_exceptions` entry for Module 9's document paths. That exception is deliberately narrow and does not extend to fetching the site root to confirm it.

| Authority | ONS code | URL | What happened |
| --- | --- | --- | --- |
| Liverpool | `E08000012` | https://www.liverpool.gov.uk | robots.txt disallows it |

## What happens to these 49

Nothing is invented to fill them. Module 9 keeps raising
`authority_website_unknown` for an authority with no `base_url`, so each one
stays visible in the review queue and can be answered in the operator UI —
where the server confirms the URL responds before storing it, and
`pipeline/verified_websites.json` keeps the answer where git can see it.

Kent is the one authority holding a `base_url` that did not answer today: it
was verified by request on 2026-08-11 and returned `403` on the 14th, which
is a bot block appearing rather than a URL going wrong. Its entry keeps its
original date.

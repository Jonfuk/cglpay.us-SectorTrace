# Public portal UI specification

Status: Phase 1 design contract, 17 August 2026.

## Audiences and tasks

The public portal serves campaign researchers, union representatives,
journalists, commissioners and pipeline operators. Its primary tasks are to
find evidence about a provider or authority, understand what the sector pays,
compare published figures safely, find an evidence-backed claim, and download
or cite the underlying evidence.

## Evidence rules

The interface must keep evidence layers separate. It must not show a composite
score, claims-per-employee calculation, treatment/workforce ratio, workforce
census trend, annualised hourly pay, or percentage-above-minimum-wage result.
Missing data remains missing; it is never treated as zero.

Published evidence, unverified extraction, candidate awaiting human review,
not collected, collected but unavailable/unparseable, and source-suppressed
values must remain visibly distinct. Every figure retains caveat and
provenance controls.

## Quality targets

The target is WCAG 2.2 AA with keyboard access, visible focus, reduced-motion
support, screen-reader landmarks and text alternatives for charts. The portal
must work offline with no CDN, no analytics and no service worker. It targets
320px minimum width, no horizontal page overflow, CLS below 0.1, and under
200ms interaction latency for local filter/search interactions. ECharts,
Tabulator, Fuse and D3 are loaded only where a route needs them.

## Design direction

Navigation follows reader questions: Overview; Pay & benchmarks; Funding &
contracts; Places; Providers; Safety & legal; Evidence-backed claims; and a
low-priority More/Tools area. The public shell and admin interface remain
separate design projects. Bootstrap 5.3.8 is vendored locally and loaded before
the SectorTrace stylesheet; application-specific rules remain authoritative.

Theme choices are System, Light and Dark, persisted locally without a network
request. Filters appear only on routes that consume them, stay in the URL, and
use a mobile offcanvas with active-filter chips and Clear all.

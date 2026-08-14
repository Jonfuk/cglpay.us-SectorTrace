# Security

## Reporting

Use GitHub's private vulnerability reporting:
**[Report a vulnerability](https://github.com/Jonfuk/cglpay.us-SectorTrace/security/advisories/new)**
(Security tab → Report a vulnerability). It opens a draft advisory visible only
to the maintainer, which is the point — a public issue is the wrong first home
for a working exploit.

This is a single-maintainer project, so there is no response-time commitment
worth making. What you will get is an acknowledgement and a decision, and the
fix recorded in `docs/upgrade-roadmap.md` with the reasoning, like every other
finding here.

## What is deliberate, and is not a finding

Read this first — the two most likely reports are both settled design
decisions, and the reasoning is in
[`docs/upgrade-roadmap.md`](docs/upgrade-roadmap.md) and
[`CLAUDE.md`](CLAUDE.md).

**There is no authentication on `/admin`, by explicit decision.** The security
model is the bind address: `--host 127.0.0.1` when the LAN is not trusted. The
operator UI can start pipeline runs, write exports and decide review items, and
[`README.md`](README.md) says so. "The admin UI is unauthenticated" is a
documented property, not a vulnerability. What *would* be a finding is a way to
reach an operator route from the public portal's origin, or a write that
succeeds without the JSON content-type and same-origin `Origin` guard.

**`style-src` keeps `'unsafe-inline'`.** The operator page carries style
attributes and the vendored libraries set styles at runtime; styles are a
defacement vector here rather than an exfiltration one. `script-src` is
`'self'` with a single file-derived hash on the operator page, and that part is
worth reporting on.

## What is in scope, and is worth your time

- **Anything reaching private address space through the pipeline.** The
  destination guard is [`pipeline/netguard.py`](pipeline/netguard.py); it
  resolves before connecting and refuses loopback, private, link-local,
  multicast and reserved addresses, including across redirects. Its documented
  gap is DNS rebinding — the resolve-then-connect window — so a *different*
  bypass is a finding, and that one is a known limit.
- **Anything that puts a `restricted_` table's contents into an export or a
  portal-reachable response.** `guard_columns()` and the reveal gate are meant
  to make this structurally impossible rather than a matter of care.
- **Any value reaching the DOM as markup rather than as a text node.**
  `static/app.js` throws on an `html:` prop; a route around that is a finding.
- **Any write to an evidence table without a matching promotion row.** Database
  triggers (migration `0030`) enforce it. A path around the triggers matters
  more than a bug in `promote.py`.
- Anything in a dependency, the CI workflows, or the release surface.

## Out of scope

Volumetric or denial-of-service testing against this project's *sources*. They
are public bodies — councils, coroners' courts, NHS trusts, the Charity
Commission. This pipeline's politeness commitment (robots.txt respected,
process-wide per-host rate limiting, `Retry-After` honoured, a User-Agent
carrying a contact address) has no exception for security research, and neither
does anything else pointed at them.

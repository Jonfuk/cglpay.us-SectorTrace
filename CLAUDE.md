# Working in this repository

An England-wide substance misuse sector evidence pipeline: it collects
public-domain evidence for a trade union pay campaign, stores it in a
PostgreSQL warehouse with full provenance, and serves a public evidence portal
at `/` and an operator UI at `/admin` from one stdlib HTTP server.

Read [`README.md`](README.md) for what it does.
[`docs/CAVEATS.md`](docs/CAVEATS.md) is not optional reading before touching
anything that produces a figure — it leads with the things that must **not** be
computed.

## What this project optimises for

A figure that can still be defended a year later in a room where someone
disputes it. Every design choice that looks like a limitation — `NULL` over a
guess, candidates that never auto-promote, no arithmetic across evidence
layers, no headline contract total — is that trade taken again: a smaller
defensible dataset over a larger plausible one.

Speed, coverage and polish are pursued only where they cost none of that.

## Settled decisions

These are not defaults to re-litigate. Breaking one is a decision to argue for
explicitly, not to slip in.

1. **Provenance or `NULL`.** Every row carries its source URL, fetch time and
   the SHA-256 of the exact bytes, archived under `data/raw/`. Nothing is
   inferred, interpolated or defaulted. Unparseable is `NULL` plus a
   `parse_failures` row; anything needing judgement goes to `review_queue`.
2. **Evidence layers stay separate.** No composite scores or cross-source
   arithmetic that `docs/CAVEATS.md` forbids.
3. **Personal data lives in `restricted_` tables**, excluded from every export
   and every portal-reachable response, enforced by `guard_columns()` and the
   reveal gate rather than by intention.
4. **Nothing is promoted to evidence without a person.** Database triggers
   enforce it (`migrations/0030`); see `pipeline/promote.py`.
5. **Collection stays polite.** robots.txt respected, process-wide per-host
   rate limiting, `Retry-After` honoured, conditional requests, a User-Agent
   carrying `CONTACT_EMAIL`. Concurrency only ever spans *different* hosts.
   Nothing in CI or tests touches a real source.
6. **Stdlib web server. No framework, no ASGI, no build step, no CDN.** Both
   front ends must render with the network cable unplugged.
7. **Portal isolation.** Admin work never edits
   `pipeline/web/static/public/**`, `public_queries.py`, `public_export.py` or
   any `/api/v1/*` route. New admin endpoints go under `/api/admin/*`, new
   admin assets under `/admin/*`. `tests/test_portal_isolation.py` pins it.
8. **No authentication**, by explicit decision. The security model is the JSON
   content-type + same-origin `Origin` guard on writes, the destination guard
   in `pipeline/netguard.py`, and `--host 127.0.0.1` when the LAN is not
   trusted.
9. **Values reach the DOM as text nodes**, never as concatenated HTML.
   `static/app.js` throws on an `html:` prop — keep it that way.
10. **PostgreSQL discipline.** PostgreSQL 18 is the only application database
    (performance.md Phase 1 reversed the former SQLite-default decision).
    Connection per request or per module, `readonly_connection` for reads (the
    pooled SELECT-only reader role), `db.get_connection` for writes, closed in
    `finally`, commits per unit of work rather than once at the end. There is
    no write slot — MVCC lets writers interleave; the one-overlapping-run rule
    moves to a PostgreSQL advisory lock in the Phase 5 worker cutover. pgvector,
    pg_trgm and PostGIS are required extensions (`db.ensure_extensions` fails
    the migrate without them). `DATABASE_URL` is mandatory; `deploy/docker-compose.postgres.yml`
    provides a local one.

## House style

- **Comments explain constraints and reasoning, not mechanics.** The comments
  here are the documentation; several record a bug that was found the hard way
  and why the code is shaped to prevent it. Match that. Do not reflow them to
  satisfy a linter.
- **Commit messages say why.** They are part of the design record — read
  `git log` before changing something that looks odd.
- Structured logging only: `log.info("web.<event>", ...)`. Never `print`.
- Paths are `Path`-based. Development is Windows; CI is Ubuntu.

## Working here

```bash
uv run python -m pytest          # the offline suite, ~2.5 minutes
uv run ruff check pipeline tests # lint; CI runs both
./start.sh backup                # before anything that rewrites the warehouse
./start.sh web --host 127.0.0.1  # portal on /, operator tools on /admin
```

- **Tests are offline and fixture-backed.** Live-source tests sit behind the
  `integration` marker and are deselected by default. Do not run them in a
  loop, and do not add a test that fetches.
- **Never write into the repository from a test.** Everything writable in the
  `settings` fixture points into `tmp_path`, and a test asserts it. This has
  been got wrong twice — once into `logs/`, once into `data/backups/`.
- **Verify UI changes in a browser**, not only in tests. A header test cannot
  tell you a vendored library still works, and a CSP hash test that recomputes
  the hash the way the code does will agree with itself while the page is
  broken.
- **Several sessions share this checkout.** Stage explicit paths; never
  `git commit -a`. Check `git status` before staging and touch nothing you did
  not write. Push after committing.

## Where things are

| | |
|---|---|
| `pipeline/modules/m00`–`m16` | One per source; each declares its dependencies |
| `pipeline/registry.py`, `runner.py`, `parallel.py` | Module registry, execution, worker fan-out |
| `pipeline/http.py`, `netguard.py` | The shared client; where a fetch may land |
| `pipeline/promote.py` | Candidates becoming evidence |
| `pipeline/backup.py` | `VACUUM INTO` snapshots and restore |
| `pipeline/web/` | Server, admin API, portal API, static front ends |
| `pipeline/migrations/` | Schema, applied in order and recorded |
| [`docs/upgrade-roadmap.md`](docs/upgrade-roadmap.md) | Current findings register and phase status |

# Running against the LAN PostgreSQL warehouse

> Document analysis is intentionally local-heavy.  The Railway Docker image
> installs PostgreSQL and storage support only; it serves persisted canonical
> document records and does not install Docling, OCRmyPDF, Tesseract, or
> Ghostscript.  See [document-analysis.md](document-analysis.md) for local
> setup and the separate derived-artifact storage policy.

Phase 5 of the PostgreSQL port ([issue #21](https://github.com/Jonfuk/cglpay.us-SectorTrace/issues/21)).
Phases 1–3 gave the two backends one interface, moved the rows across and
measured both; Phase 4 optimised the PostgreSQL path. This is the part that is
not code: which warehouse is authoritative, what keeps the other one worth
falling back to, and what a deployment somewhere else would have to change.

## Where things stand

As of **2026-08-15**, `DATABASE_URL` is set in `.env` on the collection
machine, which means:

| | |
| --- | --- |
| **Collection writes to** | the LAN PostgreSQL warehouse |
| **The portal and operator UI read** | the same, through `sectortrace_reader` |
| **`data/warehouse.db` is** | a fallback, current only as of the last `sync-sqlite` |
| **Rolling back means** | unsetting `DATABASE_URL` — which lands on that file, in whatever state it is in |

That last row is why this phase exists. Phases 15–18 were collected against
PostgreSQL, and by the time anyone checked, the SQLite file was 12 migrations
and 33,000 rows behind: the documented rollback would have quietly discarded
four phases of work. A rollback path nobody exercises is a rollback path
nobody has.

```bash
./start.sh sync-sqlite --check    # answer that question before you need to
```

## The server

Read from the live server on 2026-08-15, not assumed:

| | |
| --- | --- |
| Version | PostgreSQL 18.6 (Debian build, in a container) |
| Database | `sectortrace`, 516 MB, 82 tables, 138 indexes |
| Collation | `builtin` provider, `C.UTF-8` |
| Roles | `sectortrace_app` (owner, DML+DDL), `sectortrace_reader` (`SELECT` only) |
| `max_connections` | 100 |
| Extensions installed | `plpgsql` only; `amcheck` and `pg_stat_statements` are available and not installed |
| TLS | **off** |

The collation is the load-bearing one. It is `builtin`/`C.UTF-8` so that
`ORDER BY name` matches SQLite's `BINARY` ordering — see
[`pipeline/migrations/postgres/README.md`](../pipeline/migrations/postgres/README.md)
for why the builtin provider rather than a libc locale. `verify-migration`
compares 688,189 rows in primary-key order on both engines, so a database
created without it fails that check rather than serving subtly reordered
pages.

`sectortrace_reader` holds `SELECT` and nothing else — confirmed against the
live server, which answers `false` to `has_table_privilege(…, 'INSERT')`. That
is the enforcement point for the portal and the SQL box, replacing SQLite's
`PRAGMA query_only`: a session setting the application asks for can be
forgotten by a bug, and a role without `INSERT` cannot be talked into one.

### What the Health tab's integrity check covers

`PRAGMA integrity_check` walks every page of a SQLite file. PostgreSQL has no
in-database equivalent, so the panel does the two things it can and says which
they were:

* every foreign key swept with a generated anti-join — the analogue of
  `PRAGMA foreign_key_check`, and the check that would notice a restore or a
  load having produced orphans (25 constraints, under a second on the live
  warehouse);
* every constraint asked whether it is validated, because a `NOT VALID` one is
  enforced for new rows and never checked against the old ones — a guarantee
  the schema claims and does not have, and a state SQLite cannot even express.

**Pages are not checked.** `pg_amcheck` is a separate binary run against the
server, and the `amcheck` extension — available here, not installed — needs a
superuser to add. The panel says so rather than reporting a clean bill for a
check that did not run; if you want the physical check, run `pg_amcheck` on
the LAN host.

**TLS is off, and that is the one gap in this setup.** The warehouse holds
personal data in `restricted_` tables, and connections cross a private network
rather than the public internet. If that network is not itself encrypted, the
remaining work is `ssl = on` plus `hostssl` entries in `pg_hba.conf` and
`sslmode=require` in the URLs — a server-side change this repository cannot
make for you.

## Configuration

Nothing in the repository holds a hostname or a password. Four keys in `.env`,
all optional, none with a default pointing at a real server:

```
DATABASE_URL=postgresql://sectortrace_app:…@…:5432/sectortrace
DATABASE_RO_URL=postgresql://sectortrace_reader:…@…:5432/sectortrace
POSTGRES_TEST_URL=…        # what the live test suites use
POSTGRES_TEST_RO_URL=…
```

The presence of `DATABASE_URL` selects the backend — there is deliberately no
second `DATABASE_BACKEND` switch that could disagree with it. `DATABASE_RO_URL`
does not select anything on its own and is refused if set alone, because being
configured for a guarantee you do not have is worse than not having it. Every
log line and every UI panel that names the database goes through
`Settings.redacted_database_url`.

The test URLs are separate variables on purpose: everything in the live suites
writes, and several truncate. They build a schema of their own and drop it, so
pointing both pairs at the same database is supported rather than a loaded
gun.

## Dual maintenance, and what it costs

The plan calls for keeping SQLite alive for at least one full collection cycle
after cutover. In practice that is one command, and the honest version of what
it is:

```bash
./start.sh sync-sqlite --check     # divergence, without writing anything
./start.sh sync-sqlite             # rebuild data/warehouse.db from PostgreSQL
./start.sh sync-sqlite --quick     # counts and aggregates instead of every value
```

Run it **after a collection, before anything you might want to roll back**.
On the live warehouse it takes 70 seconds with `--quick` and a little over two
minutes with every one of 688,189 values compared, which is the default.

Two things it is not. It is not a merge — the file is rebuilt and replaced, so
a row written into SQLite while PostgreSQL was authoritative is discarded, and
that is the point of having one writable warehouse. And it is not a second
collection: re-crawling to fill the SQLite file would ask every source for the
same evidence twice, which settled decision 5 does not stop being about
because there are two warehouses now.

Stop the web server first. The rebuilt file is swapped in by renaming, and
Windows refuses to rename a file another process has open; the command says so
by name and keeps the rebuilt warehouse for the retry.

### When to stop

Dual maintenance ends when someone decides it does, and the decision is a
calendar one rather than a technical one. Until then, "unset `DATABASE_URL`"
is a real rollback. After it, rolling back means restoring a PostgreSQL
snapshot, and the SQLite file is an archive with a date on it.

## Backups

Both backends, one set of commands, one retention rule — see
[`BACKUP.md`](BACKUP.md):

```bash
./start.sh backup --keep 7                 # 30s, verified, manifest beside it
./start.sh list-backups
./start.sh restore data/backups/warehouse-20260815T223557Z.sql.gz --force
```

A PostgreSQL snapshot is `warehouse-<stamp>.sql.gz`: every table streamed out
of one `REPEATABLE READ` transaction into a gzipped SQL script, read back and
re-hashed before it is called a backup. It carries data and a migration
ledger, **not** DDL — the schema comes from `pipeline/migrations/postgres/`,
and a restore refuses an archive naming migrations this checkout does not
have.

Schedule it on the machine that runs the collection, not on the server: the
raw archive inventory that goes with each snapshot is on that machine, and a
backup that records only half the evidence base is half a backup.

```bash
# Linux / macOS — crontab -e
0 3 * * * cd /path/to/cglpay.us && ./start.sh backup --keep 7
```

Windows Task Scheduler running `start.cmd backup --keep 7` daily does the
same. Both exit non-zero if the snapshot cannot be verified.

`pg_basebackup` or a server-side `pg_dump` schedule on the LAN host is a
reasonable second line and covers the case this one does not: losing the
machine the backups are written on. Neither is set up, and neither is a
substitute for the above, because only this one verifies the copy and
inventories the archive beside it.

## Cutover checklist

The order matters, and each step is a gate rather than a formality:

1. `./start.sh backup --label before-cutover` on the SQLite warehouse, with
   `DATABASE_URL` unset. The file that is about to stop being authoritative is
   the one worth a labelled copy.
2. `./start.sh migrate-data --dry-run` — the load order and every preflight
   check, writing nothing.
3. `./start.sh migrate-data` — load, then compare every value.
4. `./start.sh verify-migration` — again, from a separate command, on a
   different day if you like. A copy checked by the thing that wrote it agrees
   with itself.
5. Set `DATABASE_URL` in `.env`. Every command now reads and writes
   PostgreSQL; nothing else changes.
6. Run one real collection and one portal session against it, and look at the
   Health tab: it names the warehouse it is serving.
7. `./start.sh backup` — the first PostgreSQL snapshot, so there is one before
   anything depends on there being one.
8. `./start.sh sync-sqlite` after that collection, and after every one until
   dual maintenance ends.

Rolling back at any point before step 8 is unsetting the variable. After it,
the SQLite file is as current as the last sync, which `sync-sqlite --check`
will tell you.

## Somewhere else: your own VPS

`deploy/ansible/` provisions the whole stack — PostgreSQL, Neo4j, the app,
Caddy for TLS, and a built-but-not-running documents-worker image — as a
reproducible Docker Compose build on a single Debian VPS, run locally on the
box itself rather than from a separate control machine. See
[`deploy/ansible/README.md`](../deploy/ansible/README.md).

## A second VPS: mirroring an existing deployment

`deploy/ansible-mirror/` provisions a box that runs the same stack with
nothing collecting into it. The warehouse arrives from an existing
deployment on a nightly timer — either its newest verified backup out of S3,
a direct verified copy of its PostgreSQL over an SSH tunnel, or a direct
verified copy from a managed PostgreSQL URL — and that
deployment's raw archive is pulled out of its bucket onto the mirror's local
disk, where the mirror's own app reads it with no S3 configuration at all.

Six of its seven roles are the self-host build's, used unchanged. The thing
to know before running it is that the warehouse is replaced wholesale on
every sync, so review decisions and promotions made on a mirror are
destroyed at the next one: evidence work belongs on the source deployment.

The decisions a sync makes — which snapshot is current, how old that makes
the data, whether this box already has it — are `pipeline mirror` (see
`pipeline/mirror.py`), not the deployment's shell script, so the offline
suite covers them. Two things follow from the failure a mirror actually has,
which is looking perfectly healthy while serving data that stopped moving
weeks ago: the sync fails rather than reporting "nothing to do" when the
source's newest snapshot is stale, and a failed unit raises an alert instead
of a journal entry. Weekly and monthly timers re-check that this box's copy
still matches its source. See
[`deploy/ansible-mirror/README.md`](../deploy/ansible-mirror/README.md).

## Somewhere else: Railway, or any managed PostgreSQL

The repository now includes a Railway deployment path in `Dockerfile`,
`railway.toml`, and `deploy/railway-start.sh`. The image installs the
PostgreSQL and S3 extras, runs `pipeline migrate` before serving traffic, and
binds the web process to Railway's `PORT`. Migrations are recorded in the
database ledger, so a restart or concurrent release safely re-runs the check.

Create a Railway PostgreSQL service in the same project, then add these
variables to the SectorTrace service:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
CONTACT_EMAIL=operator@example.org
ARCHIVE_S3_BUCKET=...
ARCHIVE_S3_ENDPOINT=...
ARCHIVE_S3_REGION=...
ARCHIVE_S3_URL_STYLE=virtual
ARCHIVE_S3_ACCESS_KEY=...
ARCHIVE_S3_SECRET=...
```

Use Railway's actual PostgreSQL service name in the reference if it is not
`Postgres`. The database URL is the only backend selector; leaving it unset on
a local machine continues to use SQLite. What a hosted deployment needs is:

Set `ADMIN_UI_ENABLED=false` in the Railway service variables. This removes
`/admin` and `/api/admin/*` from the hosted process while leaving the public
portal and public API available. The setting defaults to `true` for local
development.

| | |
| --- | --- |
| **The database** | `DATABASE_URL` from the platform. Nothing else changes; `postgres://` URLs are accepted as well as `postgresql://`, which is what Railway and Heroku hand out. |
| **The migrations** | applied by any command on startup, from `pipeline/migrations/postgres/`. |
| **The read role** | `DATABASE_RO_URL`. A managed database usually gives one superuser-ish role; creating a `SELECT`-only role is a `CREATE ROLE` + two `GRANT`s and is worth doing rather than pointing both variables at the same user. |
| **The raw archive** | An S3-compatible bucket, configured through `ARCHIVE_S3_*`. A container filesystem does not survive a redeploy. |

The archive is independent of `DATABASE_URL`: the warehouse stores
`payload_sha256` and `archived_path` as strings, while `pipeline/archive.py`
selects the filesystem or S3-compatible backend. Migrate it separately with
`archive-migrate`, verify it with `archive-verify`, and retain the local
filesystem as a recovery mirror with `archive-mirror`/`archive-reconcile`.

Raw-object processing is a separate, manual step. It verifies each
content-addressed object again, writes only derived text under the gitignored
`data/text/archive/` directory, and records parser metadata in the warehouse.
It does not create graph claims or promote evidence:

```bash
# Check the immutable archive first
uv run pipeline archive-verify

# Process every object once; repeat runs skip the same extractor version
uv run pipeline archive-process

# Safer first pass: one source and a bounded sample
uv run pipeline archive-process --source-system council_committee_systems --limit 25

# Re-run a parser version deliberately, after reviewing its output
uv run pipeline archive-process --force --extractor-version 2
```

Use `archive_extractions` and `archive_extraction_runs` when inspecting what
was processed. Claims remain a later, reviewed stage; an empty `graph_claims`
table is therefore expected after this command.

Database mirroring is likewise explicit rather than bidirectional replication:

```bash
# Local SQLite -> Railway PostgreSQL (initial load, after a backup)
DATABASE_URL=... ./start.sh migrate-data --dry-run
DATABASE_URL=... ./start.sh migrate-data

# Railway PostgreSQL -> local SQLite recovery mirror
DATABASE_URL=... ./start.sh sync-sqlite --check
DATABASE_URL=... ./start.sh sync-sqlite
```

Only the configured PostgreSQL warehouse should receive live collection writes.
The SQLite file is rebuilt and verified from it, which prevents two writable
copies from silently diverging while preserving a practical local rollback.

### Two PostgreSQL warehouses

If the local mirror is PostgreSQL rather than SQLite, use the same migration
tree and the explicit PostgreSQL transfer commands. `DATABASE_URL` is always
the target; `DATABASE_SOURCE_URL` is always the read-only source for that
command:

```bash
# First deployment: existing local PostgreSQL -> empty Railway PostgreSQL
DATABASE_URL=railway-url DATABASE_SOURCE_URL=local-url \
  ./start.sh migrate-postgres

# Later local refresh: Railway PostgreSQL -> local PostgreSQL
DATABASE_URL=local-url DATABASE_SOURCE_URL=railway-url \
  ./start.sh check-postgres-sync
DATABASE_URL=local-url DATABASE_SOURCE_URL=railway-url \
  ./start.sh migrate-postgres --truncate
```

The transfer refuses to merge into a populated target, rejects schema
differences, preserves primary keys, resets identity sequences, and compares
every value after loading. It is deliberately one-way per invocation: Railway
should be the only live writer after the initial import.

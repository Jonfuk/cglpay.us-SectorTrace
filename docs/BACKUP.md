# Backup, restore, and how big this gets

The warehouse is the only queryable copy of work that took hours of
deliberately slow crawling — one request per two seconds per host — and can
only be rebuilt by doing that again. Until Phase 3 of
[`upgrade-roadmap.md`](upgrade-roadmap.md), nothing copied it.

```bash
./start.sh backup                          # verified snapshot + manifest
./start.sh backup --label before-m04-rerun # same, named for why you took it
./start.sh list-backups                    # what is on disk, newest first
./start.sh restore data/backups/warehouse-20260813T131334Z.db --force
```

## What is copied, and what is not

| | Size (2026-08-13) | Treatment |
| --- | --- | --- |
| `data/warehouse.db` | 483.8 MiB | **Copied** with `VACUUM INTO` |
| `data/raw/` | 3.50 GiB, 6,344 files | **Inventoried**, not copied |

**The warehouse is copied with `VACUUM INTO`**, not with a file copy. SQLite
runs it inside a read transaction, so the result is a consistent snapshot of a
database that may be being written to, with no WAL sidecar to forget and no
chance of catching a half-committed transaction. It also compacts: the first
real backup came out at 473.5 MiB from a 483.8 MiB source, in 30 seconds.

**Every backup is verified before it is called one.** The copy is reopened,
integrity-checked, and compared table by table against the source it came
from. A copy missing a table, or failing `PRAGMA integrity_check`, is an error
and not a file you find out about later. A table whose count moved *while*
copying is reported rather than raised on — the warehouse is live, and a module
committing mid-copy is not a fault in the snapshot.

**The raw archive is inventoried instead of duplicated.** It is seven times
the size of the warehouse, and copying it onto the same disk buys very little.
What is written beside each backup is a listing of every file with its source
system and size. The archive is content-addressed — `data/raw/{source}/{sha256}`
— so the listing is enough to say exactly which documents are missing after a
partial loss, and every surviving file can be checked against its own name:

```bash
python -c "from pathlib import Path; from pipeline import backup; \
  print(backup.missing_from_archive(Path('data/backups/warehouse-….manifest.json')))"
```

## Restoring

`restore` refuses a backup that fails its own integrity check, or that cannot
be read as a database at all. It requires `--force` when a warehouse already
exists, and even then **never deletes it**: the existing file is renamed
`warehouse.db.superseded-<timestamp>`. WAL and shm sidecars beside the target
are removed, because a stale WAL left next to a restored file is how a good
backup becomes a corrupt warehouse.

The common reason to restore is "something went wrong". The second-commonest
is "I restored the wrong one", which is why nothing is thrown away.

## What a backup does and does not protect against

It protects against the failures that actually happen to this project: a bad
migration, a module that overwrote something it should not have, an
interrupted rewrite, a re-run against the wrong source. It does **not** protect
against losing the disk — `data/backups/` sits beside `data/warehouse.db`. If
that is the risk you care about, copy one off the machine; nothing here does
that for you, deliberately, since where it would go is a decision with
personal-data consequences (`restricted_` tables are in the copy).

## How big this gets

Measured 2026-08-13, from the manifest of the first real backup:

| Source system | Files | GiB | Mean file |
| --- | ---: | ---: | ---: |
| `find_a_tender` | 3,096 | 3.14 | 1,064 KiB |
| `contracts_finder` | 126 | 0.07 | 583 KiB |
| `authority_websites_cdp` | 916 | 0.06 | 66 KiB |
| `foi_disclosure` | 210 | 0.06 | 288 KiB |
| `charity_commission_filed_accounts` | 8 | 0.03 | 4,550 KiB |
| `council_committee_systems` | 406 | 0.03 | 71 KiB |
| everything else (17 sources) | 1,582 | 0.11 | — |

**One source is 90% of the archive.** Find a Tender pages a large result set
and each page is around a megabyte of JSON, so `m01_procurement` dominates
both the archive and the warehouse (98,588 of 645,482 rows).

**Growth is driven by changed documents, not by runs.** Archived files are
addressed by the SHA-256 of their bytes, and `pipeline/http.py` checks for an
existing copy before writing one, so re-running a module over unchanged
sources adds nothing. A re-crawl of Find a Tender that returns identical pages
costs no disk. What adds files is new notices, republished documents, and any
source that varies its bytes between fetches — a page carrying a generated
timestamp will archive a new copy every time it is fetched, and is worth
finding if the archive grows without new evidence appearing.

## Retention, and running it without being asked

```bash
./start.sh backup --keep 7
```

Backs up, then keeps the newest seven **automatic** backups. A labelled one is
never pruned: `--label before-m04-rerun` is somebody saying "I am about to do
something and I want this moment back", and a retention rule that discards it
is worse than no retention rule. Each pruned backup's manifest and archive
listing go with it — they describe that file and mean nothing without it.

**Nothing runs this for you, and on 2026-08-13 that mattered.** The
`authority_url_overrides` table was emptied and 191 verified council URLs went
with it; the only backup on disk had been taken *after* the loss. A backup you
have to remember is a backup you take too late. Schedule it:

```bash
# Linux / macOS — crontab -e
0 3 * * * cd /path/to/cglpay.us && ./start.sh backup --keep 7
```

On Windows, Task Scheduler running `start.cmd backup --keep 7` daily does the
same. Both are safe unattended: the command exits non-zero if the copy cannot
be verified, and writes nothing over an existing backup.

The raw archive still has no retention policy and accumulates until someone
deletes something. At its current size that is the right amount of machinery;
revisit it when it is inconveniently large rather than now.

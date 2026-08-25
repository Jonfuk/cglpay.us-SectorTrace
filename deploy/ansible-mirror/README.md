# Mirroring an existing deployment onto a second VPS

Provisions a box that runs the same stack as a SectorTrace deployment —
PostgreSQL, Neo4j, the app, Caddy for TLS — with **nothing collecting into
it**. The warehouse arrives from an existing deployment on a nightly timer,
and that deployment's raw archive is pulled out of its S3 bucket onto this
box's **local disk**.

It is `deploy/ansible/` with one role swapped. Six of the seven roles
(`preflight`, `common`, `tuning`, `hardening`, `docker`, `firewall`) are
used unchanged from `../ansible/roles` — same Debian box, same exposure,
same hardening, and a fix to any of them belongs in one place. Only
`sectortrace_mirror` differs from `sectortrace`.

```bash
git clone <this-repo-url> /opt/sectortrace/app
cd /opt/sectortrace/app/deploy/ansible-mirror
./ansible-mirror.sh
```

## Two things to understand before you build one

**The warehouse is replaced wholesale on every sync.** A review-queue
decision, a promotion, a reveal or a document batch performed on the mirror
is destroyed at the next sync — not merged, not conflicted, gone. There is
no meaning for two independently changed evidence warehouses to "merge"
without a conflict policy, and this project does not have one
(`pipeline/pgmirror.py` says so in its own docstring). Evidence work happens
on the source deployment. Read the mirror; do not work in it.

**The mirror holds the source's data, `restricted_` tables included.** It is
a copy of the warehouse, not a copy of the public export. The same
protections apply here — `guard_columns()`, the reveal gate, the admin
allowlist — because it is the same application, and the same care applies to
the box. A mirror is not a lower-security tier of the thing it copies.

## What the wizard asks

| It asks for | Notes |
|---|---|
| This mirror's domain | The A record for **this** box. Written to `group_vars/all/zz-local.yml` |
| Contact email | Let's Encrypt notices, and the operator contact the app requires |
| This box's database passwords | **Offers to generate them** — say yes. They are not the source's |
| The source deployment's domain | For the record only. Nothing connects to it |
| How the warehouse gets here | Snapshot-from-S3, or direct over an SSH tunnel — below |
| The source's raw archive bucket | Read-only keys. Optional, but see below |
| The source's backup bucket | Snapshot mode only; defaults to the archive bucket and credentials |
| Sync time | Nightly, default 04:30 UTC |
| Vault password | Encrypts all of it. Save it in your password manager |

`--reconfigure` asks again and keeps the previous vault under
`.vault-backups/` (gitignored, `0600`, still encrypted with its **old**
password). `--check` and any other argument passes through to
`ansible-playbook`.

Every credential this box holds for the source deployment should be
**read-only**. A mirror reads a bucket and reads a warehouse; it never
writes to either. A key here that could write to the authoritative
deployment is a key that could damage it from the disposable copy of it.

## The two sync paths

Both are built. `mirror_sync_mode` chooses which the timer runs, and the
wizard sets it.

### `snapshot` — the source's nightly verified backup, from S3

The source deployment already writes a verified `pipeline backup` snapshot
to its offsite bucket every night (`backup_offsite_enabled` in its own
`vars.yml`). The mirror lists that prefix, takes the newest automatic
`warehouse-<stamp>.sql.gz`, downloads it, and `pipeline restore --force`s
it.

- **Needs no inbound access to the source at all** — one bucket, read-only
  keys.
- The snapshot was verified when it was written, and `restore` verifies it
  again before it replaces anything: a snapshot that fails its own checks is
  refused rather than restored.
- Freshness is "as of the source's last backup". Sync after it, not before,
  or you restore last night's file a second time. (Harmless — the sync
  recognises the snapshot it already has and does nothing — but pointless.)
- Labelled snapshots (`warehouse-<stamp>-before-m04-rerun.sql.gz`) are
  deliberately skipped. A labelled backup is a moment somebody kept on the
  source, not necessarily the state the source is in now, and a mirror wants
  the latter. Restore one by hand if you want it.

### `tunnel` — `migrate-postgres`, over an SSH tunnel

`pipeline migrate-postgres --truncate` copies the source's live PostgreSQL
into this one and then compares **every value** against the source before
calling it a success. The source publishes PostgreSQL on its own loopback —
correctly — so `sectortrace-mirror-tunnel.service` holds `ssh -N -L` open
and the sync reaches it at `127.0.0.1:5433`.

- Fresher than a nightly snapshot, and verified against the live warehouse
  rather than against a file.
- Costs an SSH key on the source box and a tunnel to keep up. The wizard
  offers to generate the key and prints the `authorized_keys` line for it,
  restricted to the one port forward it needs:

  ```
  restrict,permitopen="127.0.0.1:5432" ssh-ed25519 AAAA...
  ```

- Use the source's **read-only** role (`sectortrace_reader`).
  `migrate-postgres` only ever reads the source.
- `sectortrace-mirror check-source` compares the two warehouses without
  changing either — the honest answer to "is this mirror actually current?",
  as opposed to "did last night's unit exit zero?".

`migrate-postgres` refuses to run when the source and the target report the
same server identity — database, schema, server address and port — because
copying a warehouse onto itself is not a thing anyone means to do. Left to
Docker that refusal fires on a correct configuration: both boxes take
172.18 from the same default pool and give PostgreSQL 172.18.0.2. This build
pins its own Docker subnet (`mirror_docker_subnet`, default
`172.29.0.0/16`) so the two differ. If you ever do see that refusal, change
that variable in `zz-local.yml` and re-run.

Switching between the two is `./ansible-mirror.sh --reconfigure` and a
re-run. Nothing about the warehouse on this box depends on which one filled
it.

## S3 to local file store

The source keeps its raw archive in an S3 bucket. **The mirror keeps a copy
of it on its own disk** and serves it from there:

- The always-on app container is given **no `ARCHIVE_S3_*` group at all**, so
  its archive backend is the filesystem at `RAW_ARCHIVE_DIR=data/raw`, which
  is `{{ state_dir }}/data/raw` on the host.
- The sync container — and only the sync container — is given the source's
  bucket credentials, in `.env.sync`. `pipeline archive-mirror` reads the
  bucket and writes every object the local store is missing into that
  directory. It never deletes a local file.

The difference between the two containers is one file, which is the point:
the portal serving this warehouse has no way to reach the source's bucket,
because it has never been told the bucket exists.

**The first sync downloads the entire archive.** Ask the source how large
that is (`sectortrace archive-verify` reports its byte count) before you
size the disk. It grows monotonically from then on; nothing is ever pruned,
by design. Set `mirror_archive_sync: false` if you want a mirror that serves
the warehouse alone — a defensible choice, and one that means this portal's
figures have no archived bytes on this box to back them.

## What a sync does

`sectortrace-mirror-sync.timer` → `/usr/local/bin/sectortrace-mirror-sync`,
nightly at `mirror_sync_time` with a randomised delay. One at a time: it
takes a lock, and a timer that fires while the first archive sync is still
running says so and exits rather than starting a second.

1. **Refuses to start** if less than `mirror_min_free_gb` is free. A restore
   writes a snapshot of what it replaces before replacing it, and running
   out of disk part way through is worse than not starting.
2. **Stops the portal** for the warehouse step. Not politeness: the restore
   truncates every table and reloads it in one transaction, holding an
   `ACCESS EXCLUSIVE` lock. Leaving the app up does not avoid the outage —
   it turns it into requests that hang, and lets a long-running portal query
   hold the restore off instead. Caddy answers the window with a 503 saying
   the mirror is refreshing, rather than a bare 502. Set
   `mirror_stop_app_during_sync: false` to leave it up and take that trade.
3. **Warehouse**: restore the newest snapshot, or copy over the tunnel.
4. **Starts the portal again** — including when a step above failed. A
   mirror that is behind still serves; leaving it stopped because a sync
   failed turns a stale copy into no copy.
5. **Raw archive**: download the objects the local store is missing.
6. **Graph**: `graph rebuild --clear` over the warehouse that just arrived.
   After it moved, never before — a projection built from the previous copy
   is wrong in a way nothing would report.
7. **Prunes superseded snapshots**, keeping `mirror_superseded_keep`.

That last one is a deliberate departure from the project's own rule that a
labelled backup is never deleted automatically. `restore --force` sets aside
what it replaces, labelled, because on a real deployment the second-commonest
reason to restore is having restored the wrong thing. On a mirror that
reasoning is weaker in one specific way and stronger in none: what a restore
replaces here is itself a copy of the source, and the source still has the
original. Keeping every night's is how a mirror fills its disk with copies
of a warehouse nobody wrote to. Set `mirror_superseded_keep: 0` to keep them
all.

### The first one is yours to start

The playbook does not run a sync. The first one downloads a whole warehouse
and, usually, an entire archive — start it deliberately, and watch it:

```bash
tmux new -s sync
sectortrace-mirror sync
```

## Day-to-day

```bash
sectortrace-mirror sync                  # refresh now, in the foreground
sectortrace-mirror sync --warehouse-only # skip the archive
sectortrace-mirror sync --force          # re-apply the snapshot already in place
sectortrace-mirror sync-status           # what is in place, and when the timer next fires
sectortrace-mirror sync-log              # follow the journal
sectortrace-mirror check-source          # tunnel mode: compare both warehouses
sectortrace-mirror coverage-report       # any pipeline command, in the app container
sectortrace-mirror psql | health | ps | logs app | restart
```

The command is `sectortrace-mirror`, not `sectortrace`. A box that has been
both a deployment and a mirror would otherwise have one command pointing at
whichever state directory was installed last, and the two are not
interchangeable. The state directory is `/opt/sectortrace-mirror/state`, not
`/opt/sectortrace/state`, for the same reason.

`./start.sh` is the local-development path and does not belong on this box —
see the self-host README's note on it, which applies here unchanged.

## Redeploying

```bash
cd /opt/sectortrace/app
git pull
cd deploy/ansible-mirror
./ansible-mirror.sh
```

**Keep this checkout at or ahead of the source's.** The schema comes from
`pipeline/migrations/postgres/`, not from the snapshot, and `restore` refuses
a snapshot naming migrations this tree does not have — restoring one would
put rows into a schema that predates them. The refusal names the missing
migrations. If you see it, `git pull` here.

Changing a password in `vault.yml` does not rotate it on an existing Postgres
volume: the role-bootstrap SQL only runs against an empty data directory.
Same as the self-host build — `ALTER ROLE` first, then update the vault.

## What this box does not have

- **No collection.** Nothing crawls a source from here. No module API keys
  are written to `.env`: a key that cannot be used is a key that should not
  be on the box.
- **No backup timer.** The mirror is a copy of something that is already
  backed up, and its restore path is "sync again".
- **A documents-worker image, built but pointless to run here.** Derived
  output goes into the warehouse, and the warehouse is replaced at the next
  sync. It is built because a mirror is also the box you take a source
  deployment's place with, and an image that has never been built is a bad
  thing to discover on that day.

## Everything else

Sizing, Cloudflare and certificates, the admin UI and its allowlist, ufw and
what Docker does around it, fail2ban, SSH, the tuning sysctls, upgrades and
reboots: all identical to the self-host build, because they are literally
the same roles. See [`../ansible/README.md`](../ansible/README.md).

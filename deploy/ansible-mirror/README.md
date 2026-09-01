# A second box off `deploy/ansible/`: mirror, or beta

This role provisions a box that runs the same stack as a SectorTrace
deployment — PostgreSQL, Neo4j, the app, Caddy for TLS — seeded from an
existing deployment's data. `ansible-mirror.sh` asks which of two things
you want, up front, because everything else here is shared between them:

- **A disaster-recovery mirror** (`mirror_role: dr_mirror`, the default).
  **Nothing collects into it.** The warehouse is replaced wholesale from the
  source deployment on a nightly timer, and that deployment's raw archive is
  pulled out of its S3 bucket onto this box's **local disk**. This is the
  original, and everything below that talks about nightly syncing, staleness
  alerts and "read it, do not work in it" describes this mode.
- **A beta deployment** (`mirror_role: beta`). Builds a chosen git branch —
  the app image is built from **this box's own checkout**, which the
  playbook itself resets to `origin/<deploy_git_branch>` on every run, not
  from whatever happened to be checked out — and seeds its database from an
  existing deployment **once**, by hand, rather than nightly. After that
  seed this is an ordinary writable database: work in it, test the branch's
  changes against realistic data, and re-seed whenever you want fresh data
  instead of on a timer that would otherwise discard what you just wrote.
  See "Beta deployments" below.

It is `deploy/ansible/` with one role swapped. Six of the seven roles
(`preflight`, `common`, `tuning`, `hardening`, `docker`, `firewall`) are
used unchanged from `../ansible/roles` — same Debian box, same exposure,
same hardening, and a fix to any of them belongs in one place. Only
`sectortrace_mirror` differs from `sectortrace`, and it is one role for
both modes above — see `mirror_role` in `group_vars/all/vars.yml`.

The shared roles run with the same variables as the self-host build bar one:
this playbook sets `sshd_permit_root_login: prohibit-password`, so root SSH
here is by key only. Nothing but an operator with a key on the box ever
reaches a mirror. Non-root password login is untouched, so a lost key is not
a locked door.

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

*(Both paragraphs above describe `mirror_role: dr_mirror`. A beta deployment
keeps the second one — same data, same care — and inverts the first: see
below.)*

## Beta deployments

Choose "Beta deployment" in the wizard's first question and it asks two more
things a mirror never does:

- **Which branch to build.** Every time you re-run `./ansible-mirror.sh` —
  a normal redeploy, not just first setup — the playbook fetches
  `origin/<branch>` and resets this box's checkout to it before building the
  app image, discarding any change made directly on the box. This box always
  runs the tip of the branch you named; there is no separate `git pull` step
  to remember, unlike a `dr_mirror`'s "Redeploying" section below.
- **Whether to reseed nightly too.** Default no. The three "how does the
  warehouse get here" sync paths below (snapshot / tunnel / URL) still apply
  — a beta box seeds from the same sources a mirror would — but by default
  that happens **once**, when you run `sectortrace-mirror sync` yourself, and
  never again on its own. Say yes and it behaves exactly like a `dr_mirror`'s
  nightly sync instead, wholesale-replacing the warehouse on the timer —
  useful if you want beta to track production data closely, but then it
  inherits the same rule: work in the source deployment, not here.

**If your production database is a managed service such as Railway, that is
sync path 3 ("Directly from a PostgreSQL URL") below** — paste its
PostgreSQL connection URL when asked, ideally a read-only role if the
provider offers one. Nothing else about the wizard changes: the raw-archive
question, the vault password and everything after it are identical for both
roles.

**What running the app normally on this box does *not* do on its own:**
collect. `mirror_role: beta` does not add module API keys or a collection
schedule — it inherits the mirror's "no collection" property (see below)
regardless of role, on purpose, so a beta box testing a portal or query
change does not also start crawling live public sources a second time from a
second box. If a queue item specifically needs to exercise collection, that
is a deliberate follow-up decision, not this role's default.

On a beta box, the playbook does start the persistent admin analysis worker in
the documents-worker image. It consumes runs created by `/admin/analysis` and
shares the beta warehouse with the app. Operate it with
`sectortrace-mirror analysis-start`, `sectortrace-mirror analysis-stop`, and
`sectortrace-mirror analysis-worker-logs`. Disaster-recovery mirrors do not
start this consumer because their warehouse is replaced by sync.

That follow-up is a file: **`<state_dir>/.env.merge`**, which for a mirror
is `/opt/sectortrace-mirror/state/.env.merge`. Put the module API keys (and
any other per-box environment overrides) there, one `KEY=VALUE` per line,
and re-run `./ansible-mirror.sh`. On every run `env.j2` appends the file
verbatim to the end of the rendered `.env`, so a key set there overrides the
same key from the template. The file is **gitignored** and is **not**
rendered from a template, so it is the one thing on the box that survives
both the beta pre-task's `git reset --hard` and the `.env` re-render — set
it once and every redeploy keeps it. Keep it `0600` and root-owned; it holds
credentials exactly like `.env`. The playbook's closing summary prints its
path and whether it was found. Start from
[`.env.merge.example`](.env.merge.example), which lists the keys
`pipeline/config.py` asks for (`CHARITY_COMMISSION_API_KEY`,
`COMPANIES_HOUSE_API_KEY`, `CQC_SUBSCRIPTION_KEY`, …).

## What the wizard asks

| It asks for | Notes |
|---|---|
| This mirror's domain | The A record for **this** box. Written to `group_vars/all/zz-local.yml` |
| Contact email | Let's Encrypt notices, and the operator contact the app requires |
| This box's database passwords | **Offers to generate them** — say yes. They are not the source's |
| The source deployment's domain | For the record only. Nothing connects to it |
| How the warehouse gets here | Snapshot-from-S3, SSH tunnel, or a directly reachable PostgreSQL URL — below |
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

## The three sync paths

All three are built. `mirror_sync_mode` chooses which the timer runs, and the
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

Switching between the modes is `./ansible-mirror.sh --reconfigure` and a
re-run. Nothing about the warehouse on this box depends on which one filled
it.

### `url` — `migrate-postgres`, from a managed PostgreSQL URL

Use this when the source database is hosted by a provider such as Railway and
its public PostgreSQL URL is reachable from the mirror VPS. The wizard asks
for the complete URL and stores it in the encrypted vault; it is rendered only
in `.env.sync`, which is read by the one-shot sync container. The always-on
portal does not receive the source URL or credentials.

Use a read-only source role where the provider offers one. The URL must be a
normal PostgreSQL connection URL, such as `postgresql://...`, and reserved
characters in its username or password must be percent-encoded. For example,
the `@` separating the password from the host is not part of the password;
an `@` inside a password must be written as `%40`.

For this mode the local warehouse is initialized with the managed source's
`libc/en_US.utf8` collation, so a fresh beta box does not need a manual
database recreation before its first import.

This mode uses the same `migrate-postgres --truncate` and row-by-row
verification as tunnel mode. `sectortrace-mirror check-source` is available
too, and compares the live managed database with this mirror without changing
either one. No SSH key or tunnel service is installed.

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
2. **Asks what needs doing** — `pipeline mirror plan` — so the portal is only
   stopped when there is actually a snapshot to restore.
3. **Stops the portal** for the warehouse step. Not politeness: the restore
   truncates every table and reloads it in one transaction, holding an
   `ACCESS EXCLUSIVE` lock. Leaving the app up does not avoid the outage —
   it turns it into requests that hang, and lets a long-running portal query
   hold the restore off instead. Caddy answers the window with a 503 saying
   the mirror is refreshing, rather than a bare 502. Set
   `mirror_stop_app_during_sync: false` to leave it up and take that trade.
4. **Warehouse**: `pipeline mirror pull` restores the newest snapshot, or
   `migrate-postgres` copies over the tunnel or from the configured URL. Either way the result is
   checked before it is called a success — `restore` re-counts every table
   against the snapshot's own manifest and rolls the whole thing back on a
   disagreement; `migrate-postgres` compares every value against the source.
5. **Starts the portal again** — including when a step above failed. A
   mirror that is behind still serves; leaving it stopped because a sync
   failed turns a stale copy into no copy.
6. **Raw archive**: download the objects the local store is missing,
   `mirror_archive_workers` at a time.
7. **Graph**: `graph rebuild --clear` over the warehouse that just arrived.
   After it moved, never before — a projection built from the previous copy
   is wrong in a way nothing would report.
8. **Semantic-analysis layer** (only when `mirror_nlp_rebuild: true`):
   `nlp chunk` then `nlp embed` in the documents worker — the one image on
   this box with the `nlp` extra — rebuilding `document_embeddings` from the
   warehouse that just arrived. Off by default; turn it on where the source
   deployment cannot embed (a managed source such as Railway ships no `nlp`
   extra, so `document_embeddings` arrives from every sync empty). Same
   after-not-before rule as the graph, and the same cost note: the warehouse
   is replaced wholesale each sync, so this re-embeds the whole corpus every
   run — a one-off on a hand-seeded `beta` box, nightly work on a recurring
   mirror. Model weights persist in `{{ state_dir }}/nlp-cache`.
9. **Prunes superseded snapshots**, keeping `mirror_superseded_keep`, and
   **writes the metrics file**.

`sectortrace-mirror sync --dry-run` runs the same decisions and changes
nothing: which snapshot would be restored, and how many archive objects are
missing locally. It takes no lock and stops nothing, so it is safe at any
time.

### Where the decisions live

The steps above are a shell script's; the judgement in them is not. Which
snapshot is current, how old that makes the data, whether this box already
has it, and what may be pruned are all `pipeline/mirror.py`, under
`tests/test_mirror.py`. That split is deliberate: those are exactly the
decisions that are subtly wrong for a month before anyone notices, and in a
templated shell script the project's offline suite could not reach them. What
is left in bash is what only bash can do — take a lock, stop a container,
start it again.

```bash
pipeline mirror plan --json     # what a sync would do
pipeline mirror status          # what is in place, and how stale
pipeline mirror pull --dry-run  # the same decision, changing nothing
```

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

## Knowing when it stops

Two failures matter here and only one of them looks like a failure.

**A sync that fails** exits non-zero, and both the sync and verify units carry
`OnFailure=sectortrace-mirror-alert@%n.service`. That records the failure in
the mirror's own state — where `sectortrace-mirror sync-status` shows it — and
then POSTs to `mirror_alert_webhook`, and/or pipes the journal to
`mirror_alert_command`. With neither set the local record still happens; it
just waits for somebody to look, and the playbook says so on every run.

**A source that has quietly stopped producing snapshots** does not fail
anything. The bucket answers, the snapshot in it still verifies, the mirror
still holds it — so the sync finds nothing to do and exits 0, which is
exactly what being up to date looks like. Silence is not success. The mirror
therefore checks the *age* of the newest snapshot in the bucket whether or not
there is anything to restore, and `--fail-if-stale` (which the sync always
passes) turns anything older than `mirror_max_snapshot_age_hours` — 48 by
default, one missed nightly run — into a failed unit, and so into an alert.

That case exits 3 rather than 1, and the sync treats it differently for it:
the archive sync and the graph rebuild still run, and the unit fails at the
end. A source that has stopped taking backups is a real problem and it is not
this box's problem, and abandoning everything else over it would leave the
mirror further behind on two counts instead of one.

If you scrape this box, set `mirror_metrics_dir` and alert on
`sectortrace_mirror_snapshot_timestamp_seconds`. That is the age of the
evidence being served, which is the question anyone quoting a figure from a
mirror is really asking — as opposed to when this box last did some work, on
which a mirror of a dead source has a spotless record.

## Proving it still matches

The sync proves that what it restored is what the snapshot held. Nothing
re-checks anything afterwards, so two timers do:

| | | |
|---|---|---|
| `sectortrace-mirror-verify.timer` | weekly | The bucket's key set against local disk, transferring nothing (`archive-mirror --dry-run --fail-if-missing`). In tunnel mode, also `check-postgres-sync` — both warehouses compared value by value, changing neither |
| `sectortrace-mirror-verify-deep.timer` | monthly | Every object in the **local** store re-hashed against its own content-addressed key |

Run either by hand with `sectortrace-mirror verify` / `verify --deep`. Both
take the sync's lock and skip rather than compare against a warehouse that is
being replaced underneath them, and both alert on failure.

The deep one runs `archive-verify` in the **app** container, and that detail is
load-bearing: the app has no `ARCHIVE_S3_*` group, so it verifies the archive
on this box's disk. Run in the sync container the same command would verify
the *source's bucket* instead — the wrong question, and it would download the
whole archive to answer it.

## Taking the source's place

A mirror is also the box you would fall back to. `sectortrace-mirror promote`
is that path, written down so it is not improvised on the day:

```bash
sectortrace-mirror promote --confirm   # stops the timers, then locks syncing off
sectortrace-mirror promote --undo      # back to mirroring
```

It stops and disables the sync timer, both verify timers and the tunnel, then
sets an interlock in the mirror's state that makes `pipeline mirror pull`
refuse. The interlock is the part that matters: a timer somebody re-enables by
hand, or a unit already queued, must not be able to overwrite a warehouse that
has since been written to.

What it deliberately does **not** do, because none of it can be guessed:
point DNS at this box, give it the module API keys it was never issued,
decide where the raw archive is written from now on, or start taking backups.
That last one is the one people forget — a mirror takes none, because until
this moment it was a copy of something that did.

Worth rehearsing once, deliberately, before you need it. A rollback path
nobody exercises is a rollback path nobody has.

## Day-to-day

```bash
sectortrace-mirror sync                  # refresh now, in the foreground
sectortrace-mirror sync --dry-run        # what it would do; changes nothing
sectortrace-mirror sync --warehouse-only # skip the archive
sectortrace-mirror sync --reset          # recreate local PostgreSQL, then sync
sectortrace-mirror sync --force          # re-apply the snapshot already in place
sectortrace-mirror sync-status           # what is in place, and how stale that is
sectortrace-mirror sync-log              # follow the journal
sectortrace-mirror verify [--deep]       # prove this box still matches its source
sectortrace-mirror check-source          # live mode: compare both warehouses
sectortrace-mirror promote --confirm     # stop mirroring; take the source's place
sectortrace-mirror coverage-report       # any pipeline command, in the app container
sectortrace-mirror psql | health | ps | logs app | restart
```

The command is `sectortrace-mirror`, not `sectortrace`. A box that has been
both a deployment and a mirror would otherwise have one command pointing at
whichever state directory was installed last, and the two are not
interchangeable. The state directory is `/opt/sectortrace-mirror/state`, not
`/opt/sectortrace/state`, for the same reason.

`sync --reset` is an explicit live-PostgreSQL recovery option. It removes only
the mirror's `sectortrace-mirror_postgres-data` volume, recreates PostgreSQL
from the current initialization SQL, waits for it to become healthy, and then
continues the verified sync. It is unavailable in snapshot mode and cannot be
combined with `--archive-only`; Neo4j, the raw archive, and the source database
are never touched.

`./start.sh` is the local-development path and does not belong on this box —
see the self-host README's note on it, which applies here unchanged.

## Redeploying

```bash
cd /opt/sectortrace/app
git pull
cd deploy/ansible-mirror
./ansible-mirror.sh
```

**A beta deployment does not need the `git pull` above** — the playbook's
own pre-task fetches and resets to `origin/<deploy_git_branch>` before
building, every run, specifically so redeploying beta is just re-running
`./ansible-mirror.sh`. Run it anyway if you like; it is a no-op once the
playbook has already fetched the same commit. A `dr_mirror` still needs it:
`deploy_git_branch` is empty by default in that mode, and the playbook
touches nothing about this box's checkout.

**Keep this checkout at or ahead of the source's.** The schema comes from
`pipeline/migrations/postgres/`, not from the snapshot, and `restore` refuses
a snapshot naming migrations this tree does not have — restoring one would
put rows into a schema that predates them. The refusal names the missing
migrations. If you see it, `git pull` here.

Changing a password in `vault.yml` does not rotate it on an existing Postgres
volume: the role-bootstrap SQL only runs against an empty data directory.
Same as the self-host build — `ALTER ROLE` first, then update the vault.

## Direct PostgreSQL access

By default 5432 is bound to `127.0.0.1` — the self-host build's posture,
reachable only from on the box or an SSH tunnel. `postgres_external_allowed_ips`
in [`group_vars/all/vars.yml`](group_vars/all/vars.yml) opens it to specific
source addresses (CIDR ranges accepted). On the next `./ansible-mirror.sh`
run, a non-empty list:

- publishes the container's 5432 on `0.0.0.0`
  (`docker-compose.mirror.yml.j2`);
- installs `/usr/local/bin/sectortrace-mirror-pg-firewall` and
  `sectortrace-mirror-pg-firewall.service`, which put an `ACCEPT` for each
  listed address plus a default-drop for every other off-box source into a
  dedicated `SECTORTRACE_PG` chain jumped to from the top of `DOCKER-USER`.

**It has to be iptables, not ufw.** A published Docker port bypasses ufw
entirely — see [`../ansible/README.md`](../ansible/README.md), "What ufw
doesn't cover". The rules are re-applied at boot and on a Docker restart by
the unit, because the kernel's tables are not persistent and Docker
recreates `DOCKER-USER` empty. A reboot before the unit runs fails closed
(5432 unreachable from off-box).

Check it: `sudo iptables -S SECTORTRACE_PG`.

What this does **not** add: TLS. The session is straight TCP to PostgreSQL —
`scram-sha-256` keeps the password off the wire (postgres:18), but the
traffic itself is not encrypted, and a home broadband address that changes
takes the rule with it. It is a weaker boundary than the SSH tunnel the sync
modes use; prefer a tunnel or a VPN for anything that is not read-only.
Point external read-only clients at `sectortrace_reader` / `DATABASE_RO_URL`.

Set the list back to empty and re-run to tear all of it down again.

## What this box does not have

- **No collection by default.** Nothing crawls a source from here, and
  `env.j2` writes no module API keys: on a `dr_mirror` a key that cannot be
  used is a key that should not be on the box. A `beta` box that has to
  exercise one real collection module is the documented exception — put that
  module's key in `<state_dir>/.env.merge`
  (`/opt/sectortrace-mirror/state/.env.merge`) and the playbook merges it
  onto the end of the rendered `.env` on every run. That file is gitignored,
  `0600`, outside the checkout the beta pre-task resets each run, so it
  survives every redeploy. See
  [`.env.merge.example`](.env.merge.example). A `dr_mirror` needs none of
  this.
- **No backup timer.** The mirror is a copy of something that is already
  backed up, and its restore path is "sync again". Note what that means the
  moment you promote it: from then on nothing here is backed up by anything.
- **The documents-worker image.** Document parsing remains available on
  demand, and beta boxes additionally keep the `analysis-worker` queue
  consumer running so `/admin/analysis` can execute against the seeded,
  writable warehouse. Disaster-recovery mirrors do not start that consumer.
  `sectortrace-mirror nlp <args>` routes here too, because the `nlp` extra is
  in this image rather than the always-on app.

## The analyst assistant (optional, off)

Off by default. Since BETA-114 both inference legs run on **OpenRouter**
([`docs/assistant.md`](../../docs/assistant.md)). Set
`assistant_app_enabled: true` and the roles build `openai` into the `app`
and documents-worker images and write `ASSISTANT_OLLAMA_URL` /
`ASSISTANT_NEEDLE_URL` = `https://openrouter.ai/api/v1`, `ASSISTANT_API_KEY`
(from `vault_assistant_api_key`, or put it in `.env.merge`), and the router /
answerer slugs `ASSISTANT_NEEDLE_MODEL` / `ASSISTANT_LFM_MODEL` (set
`assistant_needle_model` / `assistant_lfm_model` in group_vars — no pinned
default; an unset slug fails closed). `sectortrace-mirror nlp assistant` and
`nlp assistant-eval` run in the documents worker (where the `nlp` extra and
the eval fixtures are); the `app` container carries `openai` for the HTTP
admin endpoint only. It reads only warehouse content, so a mirror is a
legitimate host for it.

Two mirror-specific things:

- **Retrieval needs embeddings the sync keeps wiping.** The assistant's
  document-search tool reads `document_embeddings`, replaced wholesale on
  every sync. On a `beta` box set `mirror_nlp_rebuild: true` (and a real
  `mirror_nlp_embed_model`), or run `sectortrace-mirror nlp embed` after
  each deliberate reseed, or that tool has nothing to work with.
- **Enabling stays gated and manual.** Building the images does not turn the
  feature on. Leave `ASSISTANT_ENABLED` unset until
  `sectortrace-mirror nlp assistant-eval` reports `gate.may_enable: true`
  (re-score `FROZEN_ROUTING_THRESHOLD` against your router model first); then
  put `ASSISTANT_ENABLED=true` in `.env.merge` and re-run the playbook so it
  survives the beta checkout reset.

**Self-host escape hatch.** `assistant_runtime_enabled: true` instead adds
the Ollama container from `docker-compose.assistant.yml` that pulls
`assistant_lfm_ollama_ref` (`hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M`),
swings the two URLs to it and relaxes the timeouts; set the model vars to
the pulled reference on that path. Its weights volume sits outside the
warehouse, untouched by a sync or a `beta` reseed.

## Everything else

Sizing, Cloudflare and certificates, the admin UI and its allowlist, ufw and
what Docker does around it, fail2ban, SSH, the tuning sysctls, upgrades and
reboots: all identical to the self-host build, because they are literally
the same roles. See [`../ansible/README.md`](../ansible/README.md).

# Self-hosting the full stack on one VPS

Provisions PostgreSQL, Neo4j, the app, and Caddy (TLS + reverse proxy) as an
always-on Docker Compose stack, and builds — but does not run — the
documents-worker image for on-demand OCR/parsing batches. Designed for a
single fresh Debian VPS: it runs *on* the box it provisions
(`ansible_connection=local`, see `inventory/localhost.ini`), not from a
separate control machine over SSH.

Sizing this was worked out against a VM6 "UK AMD G8" box (4 vCPU / 8GB DDR5 /
200GB NVMe) with the raw archive already offloaded to S3 — see
`group_vars/all/vars.yml` for the Postgres/Neo4j memory split that assumes
that headroom. Resize the numbers there if your box differs.

## First deploy

On the fresh VPS, as root:

```bash
git clone <this-repo-url> /opt/sectortrace/app
cd /opt/sectortrace/app/deploy/ansible
./ansible-install.sh
```

That's the whole thing. On a first run the script installs Ansible if it's
missing, then **asks for what it can't guess** and writes an encrypted
vault itself — there's no file to hand-edit first:

| It asks for | Notes |
|---|---|
| Domain | Written to `group_vars/all/zz-local.yml` |
| Contact email | `User-Agent` on every request, and Let's Encrypt notices |
| Database passwords | **Offers to generate them** — say yes |
| S3 archive | Optional; skip to use local disk |
| Module API keys | All optional, all skippable |
| Vault password | Encrypts the rest. Save it in your password manager |

The generated passwords are 32 alphanumeric characters. That's deliberate
rather than lazy: they're interpolated into `postgresql://user:PASS@host`
URLs, and a generated `@`, `/`, `:`, `#` or `?` would split the URL
somewhere it shouldn't, surfacing as a confusing connection error that names
nothing. 32 alphanumerics is ~190 bits, far more than punctuation variety
would buy.

Point the domain's **A record at this VPS's IP before running it** — Caddy
requests a Let's Encrypt certificate on first start and the ACME HTTP-01
challenge needs it to already resolve. The script tells you to check with
`dig +short <domain>`.

Then it builds the `app` and `documents` images, brings up `postgres` +
`neo4j` + `app` + `caddy`, and installs a daily `sectortrace-backup.timer`.

### Later runs

```bash
./ansible-install.sh                 # finds the vault configured, goes straight to the playbook
./ansible-install.sh --check         # dry run; any other args pass through to ansible-playbook
./ansible-install.sh --reconfigure   # ask all the questions again
```

`--reconfigure` keeps the previous vault under `.vault-backups/` (gitignored,
`0600`, still encrypted with its **old** password) rather than beside the
original, where a stray `git add` could commit it.

Two files the wizard writes are gitignored, so `git pull` never conflicts
with your answers: `group_vars/all/vault.yml` and
`group_vars/all/zz-local.yml`. The latter loads *after* `vars.yml` —
`group_vars/all/*` is read alphabetically and later files win — so it
overrides the tracked defaults without making the tracked file dirty. Put
any other local override in there too.

To edit the vault by hand later:

```bash
ansible-vault edit group_vars/all/vault.yml
```

## What it does to the box

Six roles, in this order:

| Role | What it does |
|---|---|
| `preflight` | Sizes the host, checks DNS — fails before anything is changed |
| `common` | Full `apt dist-upgrade`, operator toolkit, UTC + chrony, bounded journal, swapfile |
| `tuning` | Performance sysctls, transparent hugepages off, raised `nofile` limits, I/O scheduler |
| `hardening` | SSH drop-in, fail2ban, kernel security sysctls, automatic security updates |
| `docker` | Engine + Compose plugin, daemon log rotation and `no-new-privileges` |
| `firewall` | ufw: only 80/443 and SSH inbound |
| `sectortrace` | The stack itself, `.env`, backups timer |

### Sizing: it reads the host

Nothing is hardcoded to the 8GB box. `preflight` reads the host's actual RAM
and CPU count and derives everything, so the same playbook suits a 4GB
instance or a 16GB one:

| Host | `shared_buffers` | `work_mem` | Neo4j heap | Docs limit | Parse jobs |
|---|---|---|---|---|---|
| 4GB / 2 vCPU | 993MB | 4MB | 512MB | 1986MB | 1 |
| 8GB / 4 vCPU | 1986MB | 9MB | 953MB | 3973MB | 2 |
| 16GB / 8 vCPU | 3973MB | 19MB | 1907MB | 7946MB | 4 |

`shared_buffers` takes the conventional 25%, capped at 8GB (past that the OS
page cache serves this workload better). Neo4j gets a deliberately modest
12%, floored at 512MB — it's a disposable projection, and the warehouse is
what must never be slow. `random_page_cost` and `effective_io_concurrency`
are set for NVMe; their defaults describe a spinning disk and make the
planner avoid index scans it should prefer.

Preflight **asserts the budget fits** before building anything, so an
undersized box gets a clear message naming the numbers rather than the OOM
killer explaining it at 3am. 4GB is the practical floor for the full stack;
2GB is refused.

Override any single value in `zz-local.yml`, or set `auto_tune_memory: false`
and pin them all.

### Where the data lives

PostgreSQL, Neo4j and Caddy state are in **named Docker volumes**
(`sectortrace_postgres-data`, `sectortrace_neo4j-data`, …), not bind mounts
under `state_dir`. Two reasons, both found on a real box:

- PostgreSQL 18+ images store data in a major-version subdirectory and
  declare their volume at `/var/lib/postgresql`, not `.../data`. A bind
  mount one level too deep is reported as an "unused mount/volume" and the
  container refuses to start if anything is in it.
- Both entrypoints drop from root to their own service user and neither
  chowns the *parent* of its data directory, so a root-owned bind mount is
  untraversable by the user that needs it. Docker seeds a fresh named volume
  from the image, ownership included, so the question never arises.

`docker volume inspect sectortrace_postgres-data` says where a volume
physically sits. `docker compose down` keeps them; only `down -v` destroys
them.

What *is* under `state_dir`: `.env`, the rendered compose and Caddyfile,
`postgres-init/`, `logs/`, and the whole of `data/` — which is bind-mounted
into the app and documents containers as `/app/data`, so everything the
pipeline writes lands on the host rather than on a container layer.

That last point matters most for **`data/raw`**. With no `ARCHIVE_S3_*`
group configured the pipeline archives raw response bytes there, and that
archive is the audit trail behind every figure (settled decision 1),
rebuildable only by crawling every source again at one request per two
seconds. An earlier revision mounted only `data/backups`, which left it on
the container's writable layer where `docker compose up -d` would discard
it. The parent is mounted now, so a future `data/` subdirectory is
persistent by default rather than by remembering to add it.

It grows monotonically — nothing is ever pruned, by design — so watch it,
and move to `ARCHIVE_S3_*` if it starts crowding the disk.

`state_dir` itself is `0750` root-owned — that's the privacy boundary,
which is why individual files inside can carry whatever mode a container
needs without widening host access.

Backups go through `pipeline backup` (verified, plus the offsite copy), not
by copying a data directory out from under a running server.

### Blast radius

The failure this guards against: a document batch allocates hard, the kernel
OOM killer picks a victim host-wide, and it picks PostgreSQL.

- The documents worker has a `mem_limit` and a CPU cap, so it hits its own
  cgroup limit and is killed **alone**, recording a retryable failure.
- Neo4j has a limit too (heap + pagecache + JVM overhead). If something must
  die, this is the right thing — `graph rebuild --clear` puts it back.
- PostgreSQL gets `oom_score_adj: -500`, making it the last thing the kernel
  considers. Everything else here is restartable or rebuildable; the
  warehouse is neither.

### Installed tooling

`base_packages` in `vars.yml` carries the standard operator toolkit —
`tmux`, `htop`, `iotop`, `ncdu`, `sysstat`, `mc`, `rsync`, `jq`,
`dnsutils`, `mtr-tiny`, `tree`, `lsof`, `vim`, `bash-completion` and the
rest. Add your own to `extra_packages` rather than editing the base list, so
a `git pull` doesn't conflict.

Three of those are load-bearing rather than taste:

- **`tmux`** — a collection run or a document batch outlives an SSH
  session. Start one inside `tmux` or a dropped connection kills it. A
  default `/etc/tmux.conf` is installed with a 50k-line scrollback and mouse
  support.
- **`sysstat`** — Debian ships it with collection *disabled*, so `sar`
  reports nothing. The playbook enables it, because the moment you want
  performance history is always after the incident.
- **`dnsutils`** — `dig <your-domain>` is how you confirm the A record
  points here before Caddy's first Let's Encrypt request depends on it.

No PostgreSQL client is installed on the host: the container already has
one, so use `docker compose exec postgres psql -U sectortrace_app
sectortrace` and avoid a client/server version mismatch.

### fail2ban

Configured in `roles/hardening/templates/fail2ban-jail.local.j2`, with two
jails:

| Jail | Trigger | Ban |
|---|---|---|
| `sshd` | 4 failures in 10 minutes | 24 hours |
| `recidive` | 3 bans in a day | 1 week |

Two details that make the difference between this working and only looking
like it works: the backend is **`systemd`** (a minimal Debian image may have
no `rsyslog`, so the stock jail watches a `/var/log/auth.log` that never
appears and bans nobody while reporting healthy), and the ban action is
**`ufw`**, so bans land in the firewall this box actually uses rather than
in a parallel iptables chain ufw doesn't know about.

Put your own static IP in `fail2ban_ignoreip` if you have one.

There is deliberately **no Caddy jail**: the portal is public, read-only and
unauthenticated, so there are no failed logins to count, and a filter
banning on HTTP status codes would mostly catch crawlers and people
reloading a slow page. The admin UI — the part with something worth guessing
at — isn't reachable from the internet at all.

```bash
fail2ban-client status
fail2ban-client status sshd
fail2ban-client set sshd unbanip 203.0.113.7
```

### Upgrades and reboots

`apt_full_upgrade: true` runs a full `dist-upgrade` on every run — a fresh
VPS image is usually weeks behind. That's the one task that can pull a new
kernel, so the play **checks `/var/run/reboot-required` at the end and tells
you** rather than rebooting: Ansible can't reboot a box over a local
connection anyway, and taking one silently mid-provision is unpleasant.
Reboot when convenient (`systemctl reboot`); containers come back on their
own and re-running the playbook afterwards is safe.

Ongoing, `unattended-upgrades` installs **security updates only** — a
full dist-upgrade stays a deliberate act you take by re-running the
playbook, because an unattended major-version bump of Docker or Postgres is
not something to learn about from a monitoring alert. Set
`unattended_upgrades_reboot: true` if you want the box to reboot itself to
finish one; it's off by default because a reboot mid-run loses an in-flight
collection.

### SSH

**Password authentication stays enabled, by explicit decision.** The
playbook does not turn it off and should not be "improved" to — this box
must stay reachable without a key on it. Two settings most hardening guides
change are therefore deliberately left alone, both marked as such in
`roles/hardening/templates/sshd-hardening.conf.j2`:

- `PasswordAuthentication yes` — see above.
- `AllowTcpForwarding yes` — the admin-UI tunnel below depends on it.

`PermitRootLogin` follows the same logic as password auth and defaults to
`yes` here. Set `sshd_permit_root_login: prohibit-password` if every box that
needs root has a key on it — that leaves root reachable by key only while
non-root password login is unchanged. The mirror playbook ships with that
value set.

What hardens SSH here instead: `MaxAuthTries 3`, a 30-second
`LoginGraceTime`, modern ciphers/KEX/MACs only, no X11 or agent forwarding,
ufw's rate-limited SSH rule, and a fail2ban jail that bans for 24h after 4
failures in 10 minutes. That combination makes password guessing
impractical without removing your way in. **Use a long password**, and put
your own static IP in `fail2ban_ignoreip` if you have one, so a mistyped
password can't lock you out.

The config is validated with `sshd -t` before it's written, so a syntax
error can't cost you the ability to log in.

### Tuning, and one thing deliberately not tuned

Transparent hugepages are turned off (both PostgreSQL and Neo4j document
that), `vm.max_map_count` is raised to Neo4j's documented 262144,
`vm.swappiness` is dropped to 10, writeback ratios are lowered to suit NVMe,
and `nofile` limits are raised for both PAM sessions and systemd services.

`vm.overcommit_memory` is **left at the kernel default**. The PostgreSQL
docs suggest `2` to keep the OOM killer away from the postmaster, but on an
8GB box that computes a commit limit a JVM's large virtual reservation blows
straight through — Neo4j would fail to start. `1` is Redis's recommendation
and buys nothing here.

Neither sysctl file touches `net.ipv4.ip_forward`. Docker owns it and needs
it at `1`; hardening templates that blanket-zero it break every published
port on the box.

## Redeploying / updating

```bash
cd /opt/sectortrace/app
git pull
cd deploy/ansible
./ansible-install.sh
```

Every task is idempotent: this rebuilds the app image with whatever changed,
re-renders `.env`/compose/Caddyfile only if their inputs changed, and runs
`docker compose up -d` to reconcile. `pipeline migrate` runs automatically
inside the app container's entrypoint on every start, so schema changes in
the pulled code apply on the same restart.

**Changing a password in `vault.yml` does not rotate it on an existing
Postgres volume** — `POSTGRES_INITDB_ARGS` and the role-bootstrap SQL only
run against an empty data directory. To actually rotate
`vault_postgres_app_password` or `vault_postgres_reader_password`, change it
in Postgres itself first (`ALTER ROLE … PASSWORD …` via `psql`), *then*
update `vault.yml` to match and re-run — otherwise `.env` and Postgres
disagree and the app fails to connect.

## DNS, Cloudflare, and certificates

Preflight resolves the domain before anything else happens, because Caddy
asks Let's Encrypt for a certificate the moment it starts and LE's failure
limit (5 per hostname per hour) is low enough that a few hopeful re-runs
lock you out for the rest of the hour.

It also works out **whether the record is proxied**, by checking the
resolved address against Cloudflare's published ranges. This is not
cosmetic — it decides how the admin allowlist is enforced:

| | Resolves to | Admin matched on |
|---|---|---|
| **DNS-only** (grey cloud) | this box | `remote_ip` — the connecting address |
| **Proxied** (orange cloud) | Cloudflare | `client_ip` — the real address from `X-Forwarded-For` |

Get that wrong in the proxied direction and every request appears to come
from Cloudflare, so a `remote_ip` allowlist matches nobody and **locks you
out of your own admin UI**. When proxied, Caddy is given Cloudflare's ranges
as `trusted_proxies`, which is what makes `X-Forwarded-For` believable — and
is also why that range list is a security boundary: anything trusted there
can claim to be any client. Refresh it from
[cloudflare.com/ips](https://www.cloudflare.com/ips/) occasionally.

Detection is automatic (`behind_cloudflare: "auto"`); force it with
`true`/`false` if you'd rather not have it inferred.

If your record **is** proxied, set Cloudflare's SSL mode to **Full
(strict)** — Caddy holds a real certificate for the origin, which is exactly
what that mode wants. Flexible mode would talk plain HTTP to this box. If
the ACME challenge fails, the usual cause is "Always Use HTTPS" redirecting
`/.well-known/acme-challenge` before it arrives.

Rehearsing a deploy? `caddy_use_staging_ca: true` uses Let's Encrypt's
staging endpoint — untrusted certificates, but failures cost nothing against
the real limit.

## Reaching the operator UI

The app has no authentication of its own (settled decision 8), so `/admin`
and `/api/admin/*` are never served to the open internet. Two ways in:

**1. SSH tunnel — nothing exposed, and the safer option:**

```bash
ssh -L 1801:127.0.0.1:1801 <user>@<this-vps> -N
# then open http://127.0.0.1:1801/admin
```

**2. IP allowlist** — `admin_allowed_ips` in `vars.yml`. Caddy serves
`/admin` over HTTPS to those addresses and 403s everyone else. CIDR ranges
work too.

Understand what the second one trades. The admin UI decides review-queue
items and can read `restricted_` tables, and it has **no login of any
kind** — the allowlist *is* the authentication. So:

- If the address is a home broadband line it can change without warning,
  and whoever the ISP hands it to next inherits your access.
- TLS protects it in transit. Nothing protects it if the address is wrong.
- Whether that check even works depends on the Cloudflare question above.

An empty list falls back to tunnel-only. `expose_admin_publicly: true`
drops the restriction entirely — think hard first; at that point nothing
stands between the internet and the review queue.

## Day-to-day

### Don't use `./start.sh` on this box

`./start.sh` and `start.cmd` are the **local-development** path. They expect
`uv` and a Python environment on the host, and they read the checkout's own
`.env`. This deployment has neither by design: the pipeline's Python lives
inside the app container, and its configuration is
`/opt/sectortrace/state/.env`, not the one in the checkout.

Running it here gets you `error: uv is not on PATH`. Installing `uv` to make
that go away would give you a second, unrelated environment pointing at no
database — don't. If it already created `data/raw`, `logs` and a stray
`.env` inside the checkout, those are inert (nothing mounts them) and can be
deleted.

Use `sectortrace` instead. It is installed early in the playbook —
before the images are built — precisely so it exists even when the stack
is not up.

### The `sectortrace` command

You don't have to remember which compose file and container each thing
lives in:

```bash
sectortrace run all                  # a pipeline command in the app container
sectortrace coverage-report
sectortrace documents documents process --source-system committee_papers --limit 25
sectortrace psql                     # psql on the warehouse (container's own client)
sectortrace health                   # what /health says
sectortrace logs app                 # follow logs
sectortrace backup                   # verified snapshot now
sectortrace ps | restart | up | down
```

`documents` routes to the heavy worker image rather than the app, because
the app image deliberately has no parser or OCR toolchain in it.

## Running collection

The app image is the same one Railway runs, so it can run any pipeline
command, not just serve the web UI:

```bash
cd /opt/sectortrace/state
docker compose exec app python -m pipeline run all
docker compose exec app python -m pipeline coverage-report
```

Nothing here schedules collection automatically — which modules to run and
how often is a policy decision (see settled decision 5, polite collection)
this playbook doesn't make for you. Add your own `systemd` timer calling
`docker compose exec -T app python -m pipeline run all` if you want one.

## Running a document-processing batch

Built, not started, by the main deploy — invoke it explicitly:

```bash
cd /opt/sectortrace/state
docker compose -f docker-compose.documents.yml run --rm documents documents status
docker compose -f docker-compose.documents.yml run --rm documents documents process \
  --source-system committee_papers --limit 25
```

It shares the `sectortrace_net` Docker network with the always-on stack, so
`postgres` and `neo4j` resolve by service name inside it exactly as they do
for `app`. `.env` defaults it to `DOCUMENT_PARSER=pymupdf` rather than
Docling — Docling pulls in torch-based layout models that cost several GB
of RAM during inference for no benefit over pymupdf on a CPU-only 8GB box;
override `DOCUMENT_PARSER` per invocation if you deliberately want Docling
for a specific batch and are watching memory while it runs.

## Bootstrapping the evidence graph

Also manual, and data-dependent — `graph backfill`/`rebuild` need the
warehouse to already hold authority/provider registries, so there's nothing
useful to run against a brand-new empty database:

```bash
docker compose exec app python -m pipeline graph status
docker compose exec app python -m pipeline graph backfill   # once, after your first collection
docker compose exec app python -m pipeline graph rebuild --clear
```

## The analyst assistant (optional, off)

Off by default. Since BETA-114 both inference legs run on **OpenRouter** (a
CPU-only VPS could not meet the routing bars locally — see
[`docs/assistant.md`](../../docs/assistant.md)).

Set `assistant_app_enabled: true` and the roles build the `assistant` extra
(`openai`) into the `app` and documents-worker images and write, into `.env`:
`ASSISTANT_OLLAMA_URL` / `ASSISTANT_NEEDLE_URL` = `https://openrouter.ai/api/v1`,
`ASSISTANT_API_KEY` (from `vault_assistant_api_key`), and
`ASSISTANT_NEEDLE_MODEL` / `ASSISTANT_LFM_MODEL` — the router and answerer
slugs, which you must set (`assistant_needle_model` / `assistant_lfm_model`
in group_vars; there is no pinned default and an unset slug fails closed).

The CLI and the release gate run in the **documents worker** (it has the
`nlp` extra the retrieval tool needs and the frozen eval fixtures); the
`app` container gets `openai` for the `POST /api/admin/assistant` HTTP path
only. Building the images does **not** turn the feature on.
`ASSISTANT_ENABLED` stays false until you run

```bash
sectortrace nlp assistant-eval
```

and it reports `gate.may_enable: true`. Re-score `FROZEN_ROUTING_THRESHOLD`
against your router model first if its confidence calibration differs from
the retired Needle 2's.

**Self-host escape hatch.** `assistant_runtime_enabled: true` instead adds an
Ollama container from `docker-compose.assistant.yml` that `ollama pull`s
`assistant_lfm_ollama_ref` (`hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M`,
1.59 GB), swings the two URLs to `http://ollama:11434`, and relaxes the
timeouts (`assistant_router_timeout` / `_overall_timeout`) since CPU
inference does not route in 8 s. On this path set `assistant_lfm_model` /
`assistant_needle_model` to the pulled reference. Weights live in the
`sectortrace-assistant_ollama-models` volume; its `mem_limit` is **not** in
the preflight RAM budget, so leave headroom on a box that also runs a
document worker.

## What ufw doesn't cover

Docker manipulates `iptables` directly for published ports, bypassing ufw's
own rules — the reason Postgres, Neo4j, and the app are published to
`127.0.0.1` only in `docker-compose.yml` rather than relied on to stay
unreachable because ufw denies them. Only Caddy's 80/443 are actually meant
to be internet-reachable, and those are allowed explicitly in the
`firewall` role.

## Backups

`sectortrace-backup.timer` runs `pipeline backup --keep <backup_keep>`
daily (both from `vars.yml`, default 7 kept / 03:15) inside the `app`
container, writing verified, re-hashed snapshots to
`<state_dir>/data/backups` (default `/opt/sectortrace/state/data/backups`)
— outside both the git checkout and the Postgres data volume. That's the
application-aware layer; the VPS provider's own daily snapshot is the
disaster-recovery layer under it, in case this disk is lost entirely.

**Snapshots are also copied off the box** (`backup_offsite_enabled`, on by
default when an S3 bucket is configured). A backup on the same disk as the
warehouse covers operator error and corruption and nothing whatsoever about
losing the disk. The copy goes to a prefix of its own, never near the raw
archive's keys, and mirrors local retention rather than growing forever. It
runs as a second `ExecStart` in the same unit, so a *failed* snapshot is
never followed by an upload that would rotate a good remote copy out.

Better still: point `backup_s3_*` at a **different** bucket with its own
credentials. A key that can delete the archive shouldn't also be able to
delete the archive's backups.

Restoring is the part nobody exercises — this project's own deployment doc
says a rollback path nobody exercises is a rollback path nobody has. Worth
doing once, deliberately, onto a scratch database.

```bash
systemctl status sectortrace-backup.timer
journalctl -u sectortrace-backup.service
```

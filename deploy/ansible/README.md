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

cp group_vars/all/vault.yml.example group_vars/all/vault.yml
$EDITOR group_vars/all/vault.yml       # passwords, S3 creds, module API keys
ansible-vault encrypt group_vars/all/vault.yml

$EDITOR group_vars/all/vars.yml        # at minimum, set `domain`

./ansible-install.sh
```

Point the domain's **A record at this VPS's IP before running it** —
Caddy requests a Let's Encrypt certificate on first start and the ACME
HTTP-01 challenge needs that to already resolve.

`ansible-install.sh` installs Ansible itself if it's missing, then runs
`site.yml` with `--ask-vault-pass`. It builds the `app` and `documents`
images from this checkout, brings up `postgres` + `neo4j` + `app` + `caddy`,
and installs a daily `sectortrace-backup.timer`.

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

## Reaching the operator UI

`/admin` and `/api/admin/*` are refused by Caddy on the public domain — the
app has no authentication of its own (settled decision 8), so it isn't
exposed there. Reach it over an SSH tunnel instead:

```bash
ssh -L 1801:127.0.0.1:1801 <user>@<this-vps> -N
# then open http://127.0.0.1:1801/admin in a browser
```

Set `expose_admin_publicly: true` in `vars.yml` and re-run if you'd rather
have Caddy proxy it too — you'll then want to add your own restriction
(an IP allowlist, HTTP basic auth) to the `Caddyfile.j2` template, since
nothing else stands between the internet and the review queue at that point.

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

```bash
systemctl status sectortrace-backup.timer
journalctl -u sectortrace-backup.service
```

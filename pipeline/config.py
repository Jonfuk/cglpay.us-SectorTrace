"""Configuration loaded from .env. No secrets or endpoints are hardcoded here
beyond structural defaults — API base URLs live in each module since the
brief requires discovering current endpoints/layer IDs rather than pinning
them at scaffold time.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    contact_email: str = Field(..., description="Used in User-Agent and as an operator contact point")

    # The operator UI is useful on a local checkout but should not be exposed
    # by a hosted public service. Keep it enabled by default so existing local
    # invocations continue to work; hosted deployments can set
    # ADMIN_UI_ENABLED=false to remove both the UI and its admin API routes.
    admin_ui_enabled: bool = True

    # Release identity, surfaced read-only at GET /api/v1/meta and in the
    # portal footer (BETA-039). A beta is not auditable if a reviewer cannot
    # tell which build, schema and optional capabilities they are exercising.
    # All three are injected by the deployment: `deploy/railway-start.sh` sets
    # GIT_REVISION (from Railway's RAILWAY_GIT_COMMIT_SHA), BUILD_TIME and
    # ENVIRONMENT before the web process starts. Left unset on a local
    # checkout, `meta` falls back to reading .git/HEAD and reports the
    # environment as "development".
    environment: str = "development"
    git_revision: str | None = None
    build_time: str | None = None

    # A per-IP token bucket on the public /api/v1/* routes, answering
    # sustained abuse with 429 + Retry-After. Generous by design: it exists
    # to deter a scraper hammering the API, not to meter ordinary interactive
    # use, and several readers behind one shared NAT address (a union office,
    # a campaign meeting) must never see it. Set API_RATE_LIMIT_ENABLED=false
    # to disable entirely — the LAN-only, --host 127.0.0.1 case does not need
    # it, and it costs nothing to leave off there.
    api_rate_limit_enabled: bool = True
    api_rate_limit_per_minute: float = 120.0
    api_rate_limit_burst: float = 40.0

    # A short-lived, in-process cache over the public API's derived responses
    # (/api/v1/*). Optional and in-memory by deliberate choice (settled
    # decision 6): no external store, nothing to run, nothing to unplug. Off by
    # default so a checkout and the offline suite behave byte-identically until
    # it is turned on. A completed pipeline run invalidates it (the job
    # registry calls bump_version); the TTL is only a backstop for a write that
    # does not go through a job. See pipeline/web/cache.py — the seam is the one
    # an optional shared store (Valkey) would slot into unchanged.
    cache_enabled: bool = False
    cache_ttl_seconds: float = 300.0
    cache_max_entries: int = 512
    # A longer backstop for near-static public routes (currently /api/v1/
    # boundaries -- authority geometry, rewritten only by an m00 run that
    # happens about never). A completed run still invalidates it the instant
    # the geometry changes, so this only governs how long a *non-job* write
    # (a hand-edit) can go unnoticed; a day is short enough to catch that and
    # long enough that the large GeoJSON is parsed once daily rather than every
    # few minutes. See pipeline/web/server.py `_cache_ttl`.
    cache_static_ttl_seconds: float = 86400.0

    default_rate_limit_seconds: float = 2.0
    # Per-host overrides. Kept in code (not .env) since it's structural
    # config modules will extend. Contracts Finder documents a harsh
    # multi-minute block on repeat rate-limit violations (unlike Find a
    # Tender's simple Retry-After backoff), so it gets a more conservative
    # default than the general 2s/host.
    rate_limit_overrides: dict[str, float] = {
        "www.contractsfinder.service.gov.uk": 5.0,
        # Its own robots.txt states "Crawl-Delay: 10", which RobotsRules does
        # not parse (only Allow/Disallow) — honoured here explicitly instead.
        "ckan.publishing.service.gov.uk": 10.0,
    }

    # URL prefixes fetched despite robots.txt disallowing them. Structural
    # config, deliberately in code and not .env, so that turning one on is a
    # reviewable diff rather than an invisible local setting.
    #
    # THIS IS THE ONE PLACE THIS PIPELINE OVERRIDES A PUBLISHER'S ROBOTS.TXT.
    # Adding to it is a judgement call about a specific publisher, not a
    # technical convenience. Every entry must carry the reasoning, and every
    # use is logged (`http.robots_override`) and raises a review item, so the
    # override always shows up in the audit trail rather than only here.
    #
    # whatdotheyknow.com /feed/ — mySociety's robots.txt disallows `*/feed/*`
    # and `*/search/*`. The endpoint is unauthenticated, is the documented
    # route other published FOI clients use, serves this pipeline's real
    # User-Agent a 200, and returns content that is already public and
    # reusable under the OGL. It is fetched at the standard 2s/host with
    # conditional requests, so the load is lower than crawling the equivalent
    # request pages would be. Set against that: it *is* a disallowed path, and
    # the ask in docs/mysociety-access-request.md remains the right way to put
    # this on a permitted footing. Remove this entry the moment they answer —
    # either because they said yes and it is no longer needed, or because they
    # said no.
    #
    # Council sites whose robots.txt disallows the paths Modules 9 and 10
    # need, audited 2026-08-13 by fetching each with the pipeline's real
    # User-Agent: every one of these served a robots.txt that refuses the
    # paths below, and the alternative to overriding is a council recorded as
    # publishing nothing when it publishes plenty. The override is
    # prefix-scoped to the specific host, the fetches still run at the
    # standard 2s/host with conditional requests and the identifying
    # User-Agent, and every use logs `http.robots_override` and raises a
    # `robots_override_in_use` review item — the same shape as the mySociety
    # entry above. These are not 403 bypasses: a server that refuses the
    # request outright stays refused and is recorded as blocked, which is
    # different from "publishes nothing". Treat each entry as an access
    # request pending a reply from the council, and remove it if they say no.
    #
    #   liverpool.gov.uk      — m09 base URL. robots.txt refuses automated
    #                           fetching of the council's own pages.
    #   democracy.eastsussex.gov.uk — m10 committee portal. robots.txt refuses
    #                           the ModernGov search paths.
    #   committees.scilly.gov.uk — m10 committee portal. robots.txt refuses
    #                           automated access; note the scheme is http.
    #
    # Second batch, audited 2026-08-22 during a regional sweep for committee
    # URLs that resolve but are blocked. Same shape as the first batch: each
    # host served this pipeline's real User-Agent a robots.txt that refuses
    # the committee-search paths m10 needs, none of them are 403s (which stay
    # blocked, not overridden), and each is an m10 ModernGov or CMIS committee
    # portal unless noted. councillors.liverpool.gov.uk is a distinct host
    # from the www.liverpool.gov.uk m09 exception above — Liverpool also has
    # 7 existing cdp_path_robots_disallowed review items, a consistently
    # robots-strict site. www.herefordshire.gov.uk is m24's transparency
    # section rather than a committee portal (70+ individual spend files
    # already sitting in review_queue as council_spend_file_robots_disallowed)
    # and is scoped to the domain root only because no narrower transparency
    # path is on file — tighten this prefix if the actual sub-path turns up.
    #
    # Third batch, 2026-08-27, clearing the standing *_robots_disallowed
    # review backlog. Each host below is one those modules recorded a
    # robots.txt *disallow* against (not a 403 — those raise *_blocked and
    # stay blocked), and each serves public, OGL-reusable content: m10
    # ModernGov committee search (cheshireeast), m24 transparency spend files
    # (wealden), an m09 JSNA page (coventry), and three council FOI
    # disclosure logs on hosted "/w/webpage/" platforms (adur & worthing,
    # hertsmere, westmorland & furness). Same footing as the batches above —
    # an access request pending a reply, prefix-scoped to what the review
    # items actually show, fetched at 2s/host with the identifying
    # User-Agent, every use logged and raising a `robots_override_in_use`
    # item. coventry is scoped to /jsna only; m09 may surface sibling paths
    # (/public-health, /drug-and-alcohol) that need the same treatment.
    #
    # Fourth batch, 2026-08-27, from m32's first crawl of England Safeguarding
    # Adults Board sites. Seven hosts, 125 review items between them, all
    # Safeguarding Adults Board / Safeguarding Partnership sites whose
    # robots.txt disallows either the review-listing paths (cindex.camden,
    # safeguardingdurhamadults) or the asset directory the published SAR
    # documents sit in (bromley /assets/, southwark /assets/, east sussex
    # /media/, kent & medway /assets/, wiltshire /assets/). A SAR is a public
    # document a board publishes for reuse; same footing as the batches
    # above — prefix-scoped to what the review items show, fetched at the
    # standard per-host interval with the identifying User-Agent, every use
    # logged and raising a `robots_override_in_use` item, and removed if a
    # board asks.
    #
    # Fifth batch, 2026-08-27, from m32's second crawl (wider path set). Same
    # footing again: lancashiresafeguardingpartnership.org.uk publishes 31
    # SAR documents under /assets/ behind a robots.txt disallow, and
    # kmsab.org.uk answers on its bare host as well as www (the fourth batch
    # scoped only the www form) — the prefix match is a literal startswith,
    # so both forms are listed.
    robots_exceptions: tuple[str, ...] = (
        # data.gov.uk's real API host. Its robots.txt disallows /api/
        # wholesale, which reads as aimed at crawlers hitting the CKAN search
        # UI rather than at scripted reuse of a public open-data catalogue
        # API under OGL -- the same reasoning as the WhatDoTheyKnow feed
        # exception below. Scoped to the one endpoint m01 (G6, the Contracts
        # Finder CSV archive backfill) actually calls, not the whole /api/
        # tree.
        "https://ckan.publishing.service.gov.uk/api/3/action/package_search",
        "https://www.whatdotheyknow.com/feed/",
        "https://www.liverpool.gov.uk/",
        "https://democracy.eastsussex.gov.uk/",
        "http://committees.scilly.gov.uk/",
        "https://democracy.newcastle.gov.uk/",
        "https://moderngov.stoke.gov.uk/",
        "https://www.herefordshire.gov.uk/",
        "https://democracy.bathnes.gov.uk/",
        "https://democracy.cornwall.gov.uk/",
        "https://ww5.swindon.gov.uk/moderngov",
        "https://cms.wiltshire.gov.uk/",
        "https://democracy.blackpool.gov.uk/",
        "https://moderngov.halton.gov.uk/",
        "https://councillors.knowsley.gov.uk/",
        "https://councillors.liverpool.gov.uk/",
        "https://sccdemocracy.salford.gov.uk/",
        "https://democracy.stockport.gov.uk/",
        "https://cds.bromley.gov.uk/",
        "https://democracy.cityoflondon.gov.uk/",
        "https://modgov.hillingdon.gov.uk/",
        "https://democraticservices.hounslow.gov.uk/",
        "https://moderngov.lambeth.gov.uk/",
        "https://moderngov.redbridge.gov.uk/",
        "https://cabnet.richmond.gov.uk/",
        "https://moderngov.southwark.gov.uk/",
        "https://democracy.walthamforest.gov.uk/",
        "https://democracy.wandsworth.gov.uk/",
        # Third batch (2026-08-27) — see the note above the tuple.
        "https://moderngov.cheshireeast.gov.uk/",
        "https://www.wealden.gov.uk/UploadedFiles/",
        "https://www.coventry.gov.uk/jsna",
        "https://adur-worthing-hr.onmats.com/w/webpage/",
        "https://hertsmere-foi.oncreate.app/w/webpage/",
        "https://contactus.digital.westmorlandandfurness.gov.uk/w/webpage/",
        # Fourth batch (2026-08-27) — m32 SAB sites; see the note above.
        "http://cindex.camden.gov.uk/",
        "http://www.safeguardingdurhamadults.info/",
        "https://bromleysafeguardingadults.org/assets/",
        "https://safeguarding.southwark.gov.uk/assets/",
        "https://www.eastsussexsab.org.uk/media/",
        "https://www.kmsab.org.uk/assets/",
        "https://www.wiltshiresvpp.org.uk/assets/",
        # Fifth batch (2026-08-27) — m32 second crawl; see the note above.
        "https://lancashiresafeguardingpartnership.org.uk/assets/",
        "https://kmsab.org.uk/assets/",
        # A handful of the earliest (Dec 2014) files in the m01 CSV archive
        # backfill are hosted on www.dropbox.com rather than CCS's own
        # domain. Dropbox's robots.txt disallows /s/ (shared-link paths) for
        # every crawler except Twitterbot/facebookexternalhit -- a general
        # anti-scraping stance aimed at arbitrary user-shared content, not at
        # this specific case: a public open-data CSV, published under OGL by
        # a government body (CCS), that happens to be link-hosted on Dropbox
        # rather than gov.uk. Scoped to the /s/ prefix those files sit under,
        # not the whole domain.
        "https://www.dropbox.com/s/",
    )

    # How many hosts the council-walking modules (m09, m10, m15) read at once.
    # Not a rate limit and no substitute for one: the per-host interval is
    # enforced process-wide by pipeline.http.HOST_CLOCK, so workers that land
    # on the same host queue behind each other. This only decides how many
    # *different* councils are in flight. 1 restores fully serial collection.
    max_fetch_workers: int = 8

    # Read scanned PDFs by OCR (m08's paper reports). Off even when the `ocr`
    # extra is installed, because it is expensive rather than merely slow: a
    # real report took 14 seconds a page, which puts m08's backlog of scans at
    # something like ten hours of CPU. Turning it on is a decision about how to
    # spend an evening, so it is made deliberately and not by having run
    # `uv sync --extra ocr` at some point.
    ocr_enabled: bool = False

    # Document analysis is a separate downstream workflow.  Collection must
    # remain able to succeed when parsing dependencies are deliberately not
    # installed, so this setting is never consulted by collectors.
    document_analysis_enabled: bool = True
    document_parser: str = "docling"
    document_worker_concurrency: int = 2
    document_ocr_enabled: bool = False
    document_ocr_language: str = "eng"
    document_max_file_size_mb: int = 100
    document_max_pages: int = 500
    document_min_text_chars_per_page: int = 40
    document_max_zero_text_page_ratio: float = 0.60
    document_parse_timeout_seconds: int = 900

    # The semantic-analysis layer (pipeline/nlp): a downstream stage over the
    # document-analysis output, the same "never consulted by collectors" rule
    # as the block above. 034A ships chunking, embeddings and hybrid search.
    # `nlp_embedding_model` selects the embedder: "stub" is the deterministic,
    # no-download default that CI, the retrieval-eval harness and offline
    # development use; a real sentence-transformers id (e.g.
    # "sentence-transformers/all-MiniLM-L6-v2", behind the `nlp` extra) is the
    # opt-in that turns on `--mode semantic` / `hybrid`. The model name is not
    # an identity — the resolved revision SHA is recorded on every nlp_run and
    # the nlp_model_registry row.
    nlp_enabled: bool = True
    nlp_embedding_model: str = "stub"
    nlp_chunk_batch_size: int = 200
    nlp_embed_batch_size: int = 256

    # BETA-107, retargeted to OpenRouter by BETA-114: the optional
    # natural-language operator layer. Off by default and never on Railway —
    # the Docker image installs neither the `[assistant]` extra nor a key, and
    # `railway-start.sh` runs the base install. `pipeline/assistant/` imports
    # with none of it present; `runtime_status()` reports what is installed
    # and configured without connecting.
    #
    # Two OpenAI-chat-compatible HTTP endpoints, configured independently: the
    # answerer leg (`assistant_ollama_url` — the name is historical) and the
    # router leg (`assistant_needle_url`). Both default to OpenRouter. BETA-107
    # served both from a local Ollama/Needle runtime; a CPU-only VPS could not
    # meet the routing bars (see `docs/assistant.md`), so BETA-114 lifted the
    # "processing remains local; no cloud fallback" clause of the BETA-107–113
    # contract for this feature. Point these back at a self-hosted endpoint to
    # return to local inference.
    assistant_enabled: bool = False
    assistant_ollama_url: str = "https://openrouter.ai/api/v1"
    assistant_needle_url: str = "https://openrouter.ai/api/v1"

    # The OpenRouter bearer token. `resolved_api_key` falls back to the
    # `OPENROUTER_API_KEY` env var (the same one `nlp suggest-decisions`
    # reads), so a host that already set that needs no second entry. Never
    # logged; not redacted anywhere because it is never put in a log line.
    # Empty is allowed for a self-hosted endpoint that ignores it.
    assistant_api_key: str | None = None

    # The model slug each leg sends, and what `assistant_runs` records as the
    # model that answered. There is no pinned default (BETA-114): OpenRouter
    # has no single right choice and a stale default would 404 on the wire, so
    # an unset slug fails closed in the adapter. A deployment names both — a
    # cheap/fast model for `assistant_needle_model` (routing), a stronger one
    # for `assistant_lfm_model` (grounding). `assistant_lfm_quant` is only a
    # ledger annotation now (OpenRouter serves its own quantisation).
    assistant_lfm_model: str = ""
    assistant_lfm_quant: str = ""
    assistant_needle_model: str = ""

    # Send `response_format={"type":"json_object"}` on the router call. The
    # router prompt already demands a bare JSON object, but a small model
    # (observed: gpt-4o-mini) still drops the `confidence` field often enough
    # to fail the gate; JSON mode fixes that. Only the router leg — the
    # answerer writes prose. On by default because most chat models on
    # OpenRouter honour it; set false if the chosen router model 400s on an
    # unsupported `response_format`.
    assistant_router_json_mode: bool = True

    # The routing leg and the whole-turn ceilings, in seconds. 0 means the
    # code defaults (`ROUTER_TIMEOUT_SECONDS` = 8, `OVERALL_TIMEOUT_SECONDS`
    # = 30). OpenRouter's first-token latency on a cold or busy model can
    # exceed 8 s; a deployment that sees router timeouts relaxes these. The
    # frozen confidence threshold is NOT here — that stays a deliberate edit
    # in `pipeline/assistant/routing.py`.
    assistant_router_timeout_seconds: float = 0.0
    assistant_overall_timeout_seconds: float = 0.0

    database_path: Path = REPO_ROOT / "data" / "warehouse.db"

    # The PostgreSQL warehouse, when there is one. Absent by default: SQLite is
    # still the backend of record, and a checkout with no `.env` entry here
    # behaves exactly as it did before PostgreSQL existed.
    #
    # Presence of the URL is what selects the backend — there is deliberately
    # no separate DATABASE_BACKEND switch. Two settings that can disagree have
    # a third state where they do, and the failure ("why is it writing to the
    # file when the URL is set?") is silent and reads like a bug in the driver.
    # To force SQLite for one command, unset the variable: `DATABASE_URL= …`.
    #
    # No default points at a real server, and nothing in the repository holds a
    # hostname or a password. `redacted_database_url` is what goes in a log.
    database_url: str | None = None

    # A second PostgreSQL URL used only by the explicit mirror commands. It
    # never selects the application's backend: DATABASE_URL remains the
    # database normal commands write to. Keeping the source opt-in prevents a
    # stale local URL from changing ordinary Railway or local runs.
    database_source_url: str | None = None

    # The same warehouse, as a role that holds SELECT and nothing else.
    #
    # This is what the portal and the operator UI read through, and it is the
    # PostgreSQL replacement for SQLite's `mode=ro` + `PRAGMA query_only`. The
    # difference between the two is worth being precise about, because it is
    # the reason this setting exists rather than being folded into the one
    # above: `default_transaction_read_only` is a session setting *this
    # application asks for*, so a bug in the code that forgets it leaves a
    # writable connection serving the SQL box. A role without INSERT cannot be
    # talked into one, whatever the code does. Enforcement at the server, not
    # by intention — the same argument as settled decision 3.
    #
    # Optional. Left unset, reads use `database_url` and are protected only by
    # the session setting; that is a working configuration and a weaker one,
    # and `pipeline.web.queries` says so where it happens.
    database_ro_url: str | None = None

    # Neo4j is a disposable projection of the authoritative warehouse.  It is
    # deliberately disabled by default so an unavailable graph service cannot
    # interrupt collection or ordinary local development.
    neo4j_enabled: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    neo4j_database: str = "neo4j"
    neo4j_verify_connectivity: bool = True
    graph_batch_size: int = 500
    graph_max_nodes: int = 10_000
    graph_max_edges: int = 50_000

    raw_archive_dir: Path = REPO_ROOT / "data" / "raw"
    # Derived files are never placed below RAW_ARCHIVE_DIR.  Keeping a
    # separate root makes it mechanically difficult for an OCR or parser run
    # to replace the immutable retrieved bytes.
    derived_archive_dir: Path = REPO_ROOT / "data" / "derived"
    # Derived artifacts may use their own S3-compatible bucket.  They are not
    # allowed to share RAW_ARCHIVE_DIR paths, even when the same provider is
    # used, because an OCR output must never be addressable as retrieved bytes.
    derived_archive_s3_bucket: str | None = None
    derived_archive_s3_endpoint: str | None = None
    derived_archive_s3_region: str | None = None
    derived_archive_s3_url_style: str | None = None
    derived_archive_s3_access_key: str | None = None
    derived_archive_s3_secret: str | None = None
    archive_s3_bucket: str | None = None
    archive_s3_endpoint: str | None = None
    archive_s3_region: str | None = None
    archive_s3_url_style: str | None = None
    archive_s3_access_key: str | None = None
    archive_s3_secret: str | None = None
    # --- Mirroring an existing deployment -------------------------------------
    # A mirror is a second deployment that collects nothing: its warehouse is
    # replaced wholesale from the deployment it copies, and its raw archive is
    # pulled out of that deployment's bucket onto local disk. See
    # deploy/ansible-mirror/ and pipeline/mirror.py.
    #
    # Off by default, and it has to be, because every command that reads it
    # behaves differently on a mirror: `mirror pull` replaces the warehouse
    # without being asked twice, and `archive-mirror` records what it did into
    # the mirror's own state. Neither is something a collecting deployment
    # should do because a variable happened to be set.
    mirror_enabled: bool = False

    # The deployment this box copies, for the record. Nothing connects to it:
    # it names the source in the sync log, the status output and the metrics,
    # so a figure taken from a mirror can be traced back to the box it came
    # from.
    mirror_source_label: str | None = None

    # Which snapshot is in place, when the last sync ran, and what it found.
    # Small JSON, rewritten atomically; the operator-facing half of it is
    # `pipeline mirror status`.
    mirror_state_dir: Path = REPO_ROOT / "data" / "mirror-state"
    # Snapshots downloaded from the source's bucket, on their way into the
    # warehouse. Deliberately not backup_dir: that holds snapshots this box
    # took, including the one `restore --force` sets aside, and mixing "what
    # we made" with "what we fetched from somewhere else" is how a retention
    # rule deletes the wrong one.
    mirror_inbox_dir: Path = REPO_ROOT / "data" / "mirror-inbox"

    # How old the newest snapshot in the source's bucket may be before the
    # mirror calls it stale. This is the check that catches a source whose
    # backup timer has quietly stopped: without it the mirror finds the same
    # file it restored last week, recognises it, and reports "nothing to do"
    # — which is indistinguishable from being up to date. 48 hours allows one
    # missed nightly run before anyone is woken.
    mirror_max_snapshot_age_hours: int = 48

    # The source deployment's offsite backup bucket — where its
    # sectortrace-backup-offsite script puts verified `pipeline backup`
    # snapshots. Read-only credentials are enough and are what to use: a
    # mirror reads this bucket and never writes to it.
    #
    # Separate from the ARCHIVE_S3_* group even when it is the same bucket
    # under a different prefix, because on a mirror those two are read by
    # different containers with different credentials, and collapsing them
    # would put the archive keys in the portal's environment.
    mirror_backup_s3_bucket: str | None = None
    mirror_backup_s3_endpoint: str | None = None
    mirror_backup_s3_region: str | None = None
    mirror_backup_s3_url_style: str | None = None
    mirror_backup_s3_access_key: str | None = None
    mirror_backup_s3_secret: str | None = None
    mirror_backup_s3_prefix: str = "warehouse-backups"

    migrations_dir: Path = REPO_ROOT / "pipeline" / "migrations"
    keywords_path: Path = REPO_ROOT / "pipeline" / "keywords.py"
    logs_dir: Path = REPO_ROOT / "logs"
    # Where `pipeline export` writes, and the only directory the web UI will
    # serve a file from. Declared rather than inferred from another path: the
    # server needs to know it without being told on a command line, and
    # "wherever the warehouse is, two levels up" is a guess that happens to be
    # right for this layout and silently wrong for any other.
    export_output_dir: Path = REPO_ROOT / "exports" / "output"
    # Where `pipeline backup` writes. Inside data/ so it sits beside what it
    # copies, and gitignored for the same reason the warehouse is. A backup
    # kept on the same disk protects against the failures that actually happen
    # to this project -- a bad migration, a module that overwrote something,
    # an interrupted rewrite -- and not against losing the disk. Copy one off
    # the machine if that is the risk you are covering.
    backup_dir: Path = REPO_ROOT / "data" / "backups"
    # Where a URL answered in the review UI is written so it outlives the
    # warehouse. Inside pipeline/ and tracked in git, unlike everything else
    # above: that is the whole point of it. See pipeline/authority_websites.py.
    verified_websites_path: Path = REPO_ROOT / "pipeline" / "verified_websites.json"

    # How much log a module may keep. Nothing pruned these until now, and the
    # directory had reached 7.2 MB with no ceiling of any kind (O-03). 10 MB
    # per generation and five kept is roughly a full crawl's worth of `http.get`
    # lines several times over, and bounds each module at 60 MB.
    #
    # Settings rather than constants because discarding the oldest generation
    # is a deletion, and an operator who wants a longer operational record
    # should be able to say so without editing pipeline/logging_conf.py. See
    # its docstring for what a discarded generation does and does not cost.
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    charity_commission_api_key: str | None = None
    companies_house_api_key: str | None = None
    cqc_subscription_key: str | None = None

    # m01's --kag channel: a third-party (not the publisher) re-hosting of
    # Contracts Finder notices on Kaggle, downloaded via Kaggle's API rather
    # than an anonymous fetch — see the module docstring for why this channel
    # never writes to `contracts` itself. Kaggle authenticates downloads with
    # HTTP basic auth: username plus an API key, both from a free account's
    # kaggle.json (Account settings -> Create New Token).
    kaggle_username: str | None = None
    kaggle_key: str | None = None

    # Deliberately opt-in. These are used only by m15 when a person promotes a
    # WhatDoTheyKnow request candidate; no other module may route traffic
    # through either provider, and the ordinary CSV/feed/disclosure-log
    # fetches remain on PipelineHTTPClient.
    wdtk_web_unlocker_enabled: bool = False
    brightdata_api_key: str | None = None
    brightdata_unlocker_zone: str = "web_unlocker1"
    wdtk_zenrows_enabled: bool = False
    zenrows_api_key: str | None = None
    zenrows_js_render: bool = True
    zenrows_premium_proxy: bool = False
    zenrows_proxy_country: str = "gb"

    google_service_account_json: Path | None = None
    # Railway cannot see a local credential path. Deployments may provide the
    # same JSON as base64 in this secret variable; the Sheets exporter decodes
    # it in memory and never writes it into the container filesystem.
    google_service_account_json_b64: str | None = None
    google_sheets_spreadsheet_id: str | None = None

    @field_validator("contact_email")
    @classmethod
    def _non_empty_email(cls, v: str) -> str:
        if not v or "@" not in v:
            raise ValueError(
                "CONTACT_EMAIL must be set in .env — it is required for the "
                "User-Agent sent to every source (politeness requirement)."
            )
        return v

    @field_validator("database_url", "database_ro_url", "database_source_url")
    @classmethod
    def _usable_database_url(cls, v: str | None) -> str | None:
        """An unusable URL is refused here, not at the first connection.

        The alternative is a run that applies migrations, fetches for an hour
        and then fails on a write, which is the shape of failure this project
        spends most of its design avoiding. An empty string is treated as
        unset so `DATABASE_URL=` on a command line forces SQLite back on
        without editing `.env`.
        """
        if v is None or not v.strip():
            return None
        v = v.strip()
        # postgres:// is what Railway and Heroku hand out; psycopg accepts
        # both, and rejecting the shorter one would fail on a URL the platform
        # generated rather than one anybody typed.
        if not v.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            raise ValueError(
                f"DATABASE_URL must be a PostgreSQL URL, got {v.split(':', 1)[0]!r}. "
                "PostgreSQL is the only alternative backend; leave it unset to "
                "use the SQLite warehouse at DATABASE_PATH."
            )
        return v

    @model_validator(mode="after")
    def _ro_url_needs_a_backend_to_read(self) -> Settings:
        """A read-only URL with no `DATABASE_URL` is refused rather than
        ignored.

        The backend selector is deliberately one setting, so `DATABASE_RO_URL`
        alone does not switch anything on. Silently ignoring it would leave
        somebody who set only this one believing the portal reads PostgreSQL
        through a restricted role while every query in the process goes to the
        SQLite file — configured for a guarantee they do not have, which is
        worse than not having it.
        """
        if self.database_ro_url and not self.database_url:
            raise ValueError(
                "DATABASE_RO_URL is set but DATABASE_URL is not. The read-only "
                "URL names a second role on the same PostgreSQL warehouse; it "
                "does not select the backend by itself. Set DATABASE_URL too, "
                "or unset this one."
            )
        return self

    @model_validator(mode="after")
    def _neo4j_configuration(self) -> Settings:
        """Reject an enabled graph that cannot be connected securely.

        The password is intentionally optional while graph support is off,
        preserving the existing no-Neo4j startup path.
        """
        if self.neo4j_enabled and not (self.neo4j_password or "").strip():
            raise ValueError("NEO4J_PASSWORD must be set when NEO4J_ENABLED=true.")
        if self.graph_batch_size < 1 or self.graph_max_nodes < 1 or self.graph_max_edges < 1:
            raise ValueError("Graph batch and safety limits must be positive integers.")
        return self

    @model_validator(mode="after")
    def _archive_configuration(self) -> Settings:
        values = (self.archive_s3_bucket, self.archive_s3_endpoint,
                  self.archive_s3_region, self.archive_s3_url_style,
                  self.archive_s3_access_key, self.archive_s3_secret)
        if any(values) and not all(values):
            raise ValueError("ARCHIVE_S3_BUCKET, ENDPOINT, REGION, URL_STYLE, ACCESS_KEY, "
                             "and SECRET must be set together")
        if self.archive_s3_url_style and self.archive_s3_url_style not in {"virtual", "path"}:
            raise ValueError("ARCHIVE_S3_URL_STYLE must be 'virtual' or 'path'")
        derived = (self.derived_archive_s3_bucket, self.derived_archive_s3_endpoint,
                   self.derived_archive_s3_region, self.derived_archive_s3_url_style,
                   self.derived_archive_s3_access_key, self.derived_archive_s3_secret)
        if any(derived) and not all(derived):
            raise ValueError("DERIVED_ARCHIVE_S3_BUCKET, ENDPOINT, REGION, URL_STYLE, ACCESS_KEY, "
                             "and SECRET must be set together")
        if self.derived_archive_s3_url_style and self.derived_archive_s3_url_style not in {"virtual", "path"}:
            raise ValueError("DERIVED_ARCHIVE_S3_URL_STYLE must be 'virtual' or 'path'")
        return self

    @model_validator(mode="after")
    def _mirror_configuration(self) -> Settings:
        """The snapshot bucket is all-or-nothing, like the archive one.

        Same argument as `_archive_configuration`: a partially configured
        bucket is refused here rather than falling back to something that
        looks like it worked. On a mirror the fallback would be worse than
        usual — a sync that silently finds no snapshots reports "nothing to
        do", which is what being up to date also looks like.
        """
        values = (self.mirror_backup_s3_bucket, self.mirror_backup_s3_endpoint,
                  self.mirror_backup_s3_region, self.mirror_backup_s3_url_style,
                  self.mirror_backup_s3_access_key, self.mirror_backup_s3_secret)
        if any(values) and not all(values):
            raise ValueError("MIRROR_BACKUP_S3_BUCKET, ENDPOINT, REGION, URL_STYLE, "
                             "ACCESS_KEY, and SECRET must be set together")
        if self.mirror_backup_s3_url_style and self.mirror_backup_s3_url_style not in {"virtual", "path"}:
            raise ValueError("MIRROR_BACKUP_S3_URL_STYLE must be 'virtual' or 'path'")
        if self.mirror_max_snapshot_age_hours < 1:
            raise ValueError("MIRROR_MAX_SNAPSHOT_AGE_HOURS must be a positive number of hours")
        return self

    @model_validator(mode="after")
    def _wdtk_transport_configuration(self) -> Settings:
        if self.wdtk_web_unlocker_enabled and self.wdtk_zenrows_enabled:
            raise ValueError(
                "Enable only one WDTK promotion transport: "
                "WDTK_WEB_UNLOCKER_ENABLED or WDTK_ZENROWS_ENABLED."
            )
        return self

    @property
    def archive_backend(self) -> str:
        return "s3" if self.archive_s3_bucket else "filesystem"

    @property
    def database_backend(self) -> str:
        """`"postgres"` or `"sqlite"`. The single answer to "which backend?".

        Derived, never set: see the note on `database_url` for why there is no
        second switch that could disagree with this one.
        """
        return "postgres" if self.database_url else "sqlite"

    @staticmethod
    def _redact(url: str | None) -> str | None:
        if not url:
            return None
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        if parts.password is None:
            return url
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        userinfo = f"{parts.username}:***@" if parts.username else "***@"
        return urlunsplit((parts.scheme, f"{userinfo}{host}", parts.path,
                            parts.query, parts.fragment))

    @property
    def redacted_database_ro_url(self) -> str | None:
        return self._redact(self.database_ro_url)

    @property
    def redacted_database_url(self) -> str | None:
        """The URL with its password replaced, safe to log or show in the UI.

        Every structured log line that names a database has to go through
        this. The URL carries a password, structlog writes to a file that is
        kept for five generations, and the health tab renders what it is told
        — three places a credential would otherwise come to rest.
        """
        if not self.database_url:
            return None
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(self.database_url)
        if parts.password is None:
            return self.database_url
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        userinfo = f"{parts.username}:***@" if parts.username else "***@"
        return urlunsplit((parts.scheme, f"{userinfo}{host}", parts.path,
                            parts.query, parts.fragment))

    @property
    def user_agent(self) -> str:
        return (
            "cglpay-evidence-pipeline/0.1 "
            f"(+contact: {self.contact_email}; purpose: trade union pay "
            "campaign evidence gathering from public-domain sources)"
        )

    def rate_limit_for_host(self, host: str) -> float:
        return self.rate_limit_overrides.get(host, self.default_rate_limit_seconds)

    def robots_override_for(self, url: str) -> str | None:
        """The configured prefix permitting `url` past robots.txt, or None.

        Returns the prefix rather than a bool so the caller can name the
        specific exception in the log and the review item — "we overrode
        robots" is not auditable, "we overrode robots for
        https://www.whatdotheyknow.com/feed/" is.
        """
        for prefix in self.robots_exceptions:
            if url.startswith(prefix):
                return prefix
        return None

    def require_charity_commission_key(self) -> str:
        if not self.charity_commission_api_key:
            raise RuntimeError(
                "CHARITY_COMMISSION_API_KEY is not set in .env. Register for "
                "a free key and set it before running m03_charity_finance."
            )
        return self.charity_commission_api_key

    def require_companies_house_key(self) -> str:
        if not self.companies_house_api_key:
            raise RuntimeError(
                "COMPANIES_HOUSE_API_KEY is not set in .env. Register for a "
                "free key and set it before running m04_companies."
            )
        return self.companies_house_api_key

    def require_cqc_key(self) -> str:
        if not self.cqc_subscription_key:
            raise RuntimeError(
                "CQC_SUBSCRIPTION_KEY is not set in .env. Register for a "
                "subscription key and set it before running m05_cqc."
            )
        return self.cqc_subscription_key

    def require_kaggle_credentials(self) -> tuple[str, str]:
        if not self.kaggle_username or not self.kaggle_key:
            raise RuntimeError(
                "KAGGLE_USERNAME and KAGGLE_KEY are not both set in .env. "
                "Create a free Kaggle account and an API token (Account "
                "settings -> Create New Token) before running "
                "m01_procurement --kag."
            )
        return self.kaggle_username, self.kaggle_key

    def require_brightdata_key(self) -> str:
        if not self.brightdata_api_key:
            raise RuntimeError(
                "BRIGHTDATA_API_KEY is not set in .env. Set it before enabling "
                "WDTK_WEB_UNLOCKER_ENABLED for m15."
            )
        return self.brightdata_api_key

    def require_zenrows_key(self) -> str:
        if not self.zenrows_api_key:
            raise RuntimeError(
                "ZENROWS_API_KEY is not set in .env. Set it before enabling "
                "WDTK_ZENROWS_ENABLED for m15."
            )
        return self.zenrows_api_key

    def require_google_service_account(self) -> Path:
        """Path to the service-account JSON file. This must be a *path*, not
        the JSON itself — dotenv can't parse an unquoted multi-line value,
        so pasting the blob into .env silently truncates it.
        """
        if not self.google_service_account_json:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is not set in .env. It must be a "
                "path to a credential file (e.g. secrets/google-service-account.json), "
                "not the JSON contents."
            )
        path = self.google_service_account_json
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            raise RuntimeError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON points to {path}, which does not exist. "
                "Set it to the path of the service-account credential file."
            )
        return path


def get_settings() -> Settings:
    return Settings()

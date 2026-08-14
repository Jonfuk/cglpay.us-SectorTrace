"""Configuration loaded from .env. No secrets or endpoints are hardcoded here
beyond structural defaults — API base URLs live in each module since the
brief requires discovering current endpoints/layer IDs rather than pinning
them at scaffold time.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    contact_email: str = Field(..., description="Used in User-Agent and as an operator contact point")

    default_rate_limit_seconds: float = 2.0
    # Per-host overrides. Kept in code (not .env) since it's structural
    # config modules will extend. Contracts Finder documents a harsh
    # multi-minute block on repeat rate-limit violations (unlike Find a
    # Tender's simple Retry-After backoff), so it gets a more conservative
    # default than the general 2s/host.
    rate_limit_overrides: dict[str, float] = {
        "www.contractsfinder.service.gov.uk": 5.0,
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
    robots_exceptions: tuple[str, ...] = (
        "https://www.whatdotheyknow.com/feed/",
        "https://www.liverpool.gov.uk/",
        "https://democracy.eastsussex.gov.uk/",
        "http://committees.scilly.gov.uk/",
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
    raw_archive_dir: Path = REPO_ROOT / "data" / "raw"
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

    google_service_account_json: Path | None = None
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

    @field_validator("database_url")
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

    @property
    def database_backend(self) -> str:
        """`"postgres"` or `"sqlite"`. The single answer to "which backend?".

        Derived, never set: see the note on `database_url` for why there is no
        second switch that could disagree with this one.
        """
        return "postgres" if self.database_url else "sqlite"

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

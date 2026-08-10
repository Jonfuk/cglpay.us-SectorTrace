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

    database_path: Path = REPO_ROOT / "data" / "warehouse.db"
    raw_archive_dir: Path = REPO_ROOT / "data" / "raw"
    migrations_dir: Path = REPO_ROOT / "pipeline" / "migrations"
    keywords_path: Path = REPO_ROOT / "pipeline" / "keywords.py"
    logs_dir: Path = REPO_ROOT / "logs"

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

    @property
    def user_agent(self) -> str:
        return (
            "cglpay-evidence-pipeline/0.1 "
            f"(+contact: {self.contact_email}; purpose: trade union pay "
            "campaign evidence gathering from public-domain sources)"
        )

    def rate_limit_for_host(self, host: str) -> float:
        return self.rate_limit_overrides.get(host, self.default_rate_limit_seconds)

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

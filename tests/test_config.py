from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline.config import Settings


def test_contact_email_required():
    with pytest.raises(ValidationError):
        Settings(contact_email="", _env_file=None)


def test_contact_email_must_look_like_an_email():
    with pytest.raises(ValidationError):
        Settings(contact_email="not-an-email", _env_file=None)


def test_user_agent_includes_contact_email():
    settings = Settings(contact_email="ops@example.com", _env_file=None)
    assert "ops@example.com" in settings.user_agent


def test_rate_limit_override_falls_back_to_default():
    settings = Settings(
        contact_email="ops@example.com",
        default_rate_limit_seconds=3.0,
        rate_limit_overrides={"api.example.com": 0.5},
        _env_file=None,
    )
    assert settings.rate_limit_for_host("api.example.com") == 0.5
    assert settings.rate_limit_for_host("unlisted.example.com") == 3.0


def test_require_api_key_raises_clear_error_when_missing():
    settings = Settings(contact_email="ops@example.com", _env_file=None)
    with pytest.raises(RuntimeError, match="CHARITY_COMMISSION_API_KEY"):
        settings.require_charity_commission_key()


def test_require_google_service_account_missing_setting():
    settings = Settings(contact_email="ops@example.com", _env_file=None)
    with pytest.raises(RuntimeError, match="must be a path"):
        settings.require_google_service_account()


def test_require_google_service_account_nonexistent_path(tmp_path):
    settings = Settings(
        contact_email="ops@example.com",
        google_service_account_json=tmp_path / "nope.json",
        _env_file=None,
    )
    with pytest.raises(RuntimeError, match="does not exist"):
        settings.require_google_service_account()


def test_require_google_service_account_returns_existing_path(tmp_path):
    cred = tmp_path / "sa.json"
    cred.write_text("{}")
    settings = Settings(
        contact_email="ops@example.com",
        google_service_account_json=cred,
        _env_file=None,
    )
    assert settings.require_google_service_account() == cred


def test_the_test_settings_never_write_into_the_repo(settings):
    """Every writable path the fixture hands out points into tmp.

    The suite has twice deposited its own output beside the operator's --
    5 MB of fake module logs in logs/, and 7.7 MB of backups in data/backups/
    -- both because a Settings default reaches back into the repository.
    """
    from pipeline.config import REPO_ROOT

    root = REPO_ROOT.resolve()
    for name in ("database_path", "raw_archive_dir", "logs_dir",
                  "export_output_dir", "backup_dir"):
        resolved = getattr(settings, name).resolve()
        assert not resolved.is_relative_to(root), f"{name} points into the repo"

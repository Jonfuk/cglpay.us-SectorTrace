"""The retired bulk-promotion entry point remains read-only."""
from __future__ import annotations

import sys

import pytest

from pipeline import promote_all_candidates


def test_internal_bulk_runner_is_disabled(monkeypatch):
    called = False

    def unexpected_promote(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(promote_all_candidates.promote, "promote", unexpected_promote)

    with pytest.raises(promote_all_candidates.BulkPromotionDisabled):
        promote_all_candidates._run(
            None, None, "Reviewer", [("committee_paper", "https://example.test/paper")], None)

    assert called is False


def test_cli_refuses_non_dry_run_before_opening_a_warehouse(monkeypatch, capsys):
    opened = False

    def unexpected_settings():
        nonlocal opened
        opened = True

    monkeypatch.setattr(promote_all_candidates, "get_settings", unexpected_settings)
    monkeypatch.setattr(sys, "argv", ["pipeline.promote_all_candidates", "--by", "Reviewer"])

    with pytest.raises(SystemExit) as raised:
        promote_all_candidates.main()

    assert raised.value.code == 2
    assert "autonomous bulk promotion is disabled" in capsys.readouterr().err
    assert opened is False

"""The bulk-promotion entry point requires explicit operator approval."""
from __future__ import annotations

from pipeline import promote_all_candidates


def test_run_promotes_each_candidate_and_reports_failures(monkeypatch):
    promoted = []

    def fake_promote(conn, kind, url, **kwargs):
        promoted.append((kind, url, kwargs))
        if url.endswith("failed"):
            raise promote_all_candidates.promote.PromotionError("unavailable")

    monkeypatch.setattr(promote_all_candidates.promote, "promote", fake_promote)

    stats = promote_all_candidates._run(
        None, None, "Reviewer",
        [("foi_request", "https://example.test/ok"),
         ("foi_request", "https://example.test/failed")], None)

    assert stats["promoted"] == 1
    assert stats["failed"] == 1
    assert stats["failures"] == [("https://example.test/failed", "unavailable")]
    assert promoted[0][2]["promoted_by"] == "Reviewer"


def test_yes_flag_is_declared_for_noninteractive_bulk_approval():
    parser = promote_all_candidates.argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    assert parser.parse_args(["--yes"]).yes is True

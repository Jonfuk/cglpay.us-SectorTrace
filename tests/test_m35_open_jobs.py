"""Pure boundaries for the disabled-by-default Open Jobs collector."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.modules import m35_open_jobs
from pipeline.open_jobs.commands import OpenJobsClient
from pipeline.open_jobs.policy import OpenJobsPolicy, PolicyError
from pipeline.open_jobs.store import _stable_id


def _settings(**overrides):
    values = {"open_jobs_enabled": False}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_disabled_collector_does_not_touch_connection_or_network():
    class NoUse:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("disabled collector touched the database")

    ctx = SimpleNamespace(settings=_settings(), conn=NoUse(), since=None, source="all")
    assert m35_open_jobs.collect(ctx) == {"releases": 0, "artifacts": 0, "records": 0}


def test_policy_rejects_cross_origin_and_bad_size_bounds():
    policy = OpenJobsPolicy()
    with pytest.raises(PolicyError, match="configured origin"):
        policy.url("https://elsewhere.example/data/part.parquet")
    with pytest.raises(PolicyError, match="artifact"):
        policy.accept_size(policy.max_run_bytes, used=1)


def test_policy_selects_newest_complete_entries_and_honours_since():
    entries = [
        {"dir": "2026-09-06", "to": "2026-09-06", "parts": [{"file": "a", "bytes": 1, "sha256": "a" * 64}]},
        {"dir": "2026-09-08", "to": "2026-09-08", "parts": [{"file": "b", "bytes": 1, "sha256": "b" * 64}]},
        {"dir": "incomplete", "to": "2026-09-09", "parts": []},
    ]
    selected = OpenJobsPolicy(max_releases_per_run=5).select_entries(entries, since="2026-09-07")
    assert [row["dir"] for row in selected] == ["2026-09-08"]


def test_client_builds_lite_artifact_urls_without_network():
    policy = OpenJobsPolicy()
    client = OpenJobsClient(object(), policy)
    parts = client.artifacts("diffs", {
        "dir": "diffs/2026-09-07__2026-09-08/",
        "parts": [{"file": "data_0.parquet", "bytes": 4, "sha256": "a" * 64}],
        "lite": {"parts": [{"file": "data_0.parquet", "bytes": 3, "sha256": "b" * 64}]},
    })
    assert parts[0].url.endswith("/data/diffs/2026-09-07__2026-09-08/lite/data_0.parquet")
    assert parts[0].byte_size == 3


def test_advert_event_identity_is_stable_for_replay_and_changes_by_release():
    first = _stable_id("oj-advert-event", "generation", "release-1", "ats",
                       "board", "job-1", "changed", "")
    replay = _stable_id("oj-advert-event", "generation", "release-1", "ats",
                        "board", "job-1", "changed", "")
    later = _stable_id("oj-advert-event", "generation", "release-2", "ats",
                       "board", "job-1", "changed", "")
    assert replay == first
    assert later != first

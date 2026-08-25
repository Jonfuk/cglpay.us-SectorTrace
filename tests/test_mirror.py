"""Keeping a mirror in step, and knowing when it has stopped.

The thing worth testing here is not that a file downloads. It is the
judgement: which snapshot is the current one, how old that makes the data,
whether the box has already got it, and — the failure this exists to catch —
that a source which has quietly stopped producing snapshots is reported as a
problem rather than as "nothing to do", which is what being up to date also
looks like.

These are the decisions that lived in a shell script until they were moved
here (see `pipeline/mirror.py`), and they were untestable there. Every S3 call
below goes through an injected fake client: nothing in this file touches a
network, a bucket, or a real deployment.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from pipeline import mirror

NOW = datetime(2026, 8, 25, 6, 0, 0, tzinfo=timezone.utc)


def stamp(moment: datetime) -> str:
    return moment.strftime(mirror.STAMP_FORMAT)


class FakeS3:
    """The three calls `pipeline/mirror.py` makes of a bucket, and no more.

    Modelled on `S3Archive`'s injected client: the module takes a client
    rather than building one, which is what keeps the suite offline.
    """

    def __init__(self, objects: dict[str, bytes]):
        self.objects = dict(objects)
        self.downloaded: list[str] = []

    def list_objects_v2(self, **kwargs):
        prefix = kwargs.get("Prefix", "")
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        return {"Contents": [{"Key": k, "Size": len(self.objects[k])} for k in keys],
                "IsTruncated": False}

    def download_fileobj(self, bucket, key, handle):
        self.downloaded.append(key)
        handle.write(self.objects[key])

    def download_file(self, bucket, key, destination):
        if key not in self.objects:
            raise FileNotFoundError(key)
        with open(destination, "wb") as fh:
            fh.write(self.objects[key])


@pytest.fixture
def mirror_settings(settings, tmp_path):
    """The suite's settings, told they belong to a mirror.

    Derived from the shared fixture rather than built fresh so every writable
    path still points into tmp_path — see tests/conftest.py on the three
    occasions this suite has written into the operator's own directories.
    """
    return settings.model_copy(update={
        "mirror_enabled": True,
        "mirror_source_label": "sectortrace.example.org",
        "mirror_state_dir": tmp_path / "mirror-state",
        "mirror_inbox_dir": tmp_path / "mirror-inbox",
        "mirror_backup_s3_bucket": "snapshots",
        "mirror_backup_s3_endpoint": "s3.example.com",
        "mirror_backup_s3_region": "ams",
        "mirror_backup_s3_url_style": "virtual",
        "mirror_backup_s3_access_key": "key",
        "mirror_backup_s3_secret": "secret",
        "mirror_backup_s3_prefix": "warehouse-backups",
    })


def bucket_with(*names: str, prefix: str = "warehouse-backups") -> FakeS3:
    return FakeS3({f"{prefix}/{name}": b"x" * 100 for name in names})


class TestWhichSnapshotIsCurrent:
    def test_the_newest_automatic_snapshot_wins(self, mirror_settings):
        client = bucket_with(
            f"warehouse-{stamp(NOW - timedelta(days=2))}.sql.gz",
            f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz",
            f"warehouse-{stamp(NOW - timedelta(days=9))}.sql.gz")

        rows = mirror.available(mirror_settings, client=client, now=NOW)

        assert [r["age_hours"] for r in rows] == [3.0, 48.0, 216.0]

    def test_a_labelled_snapshot_is_not_a_candidate(self, mirror_settings):
        """A label is somebody keeping a moment, not the source's current state.

        `warehouse-…-before-m04-rerun.sql.gz` can easily be the newest file in
        the bucket and is still the wrong thing for a mirror to hold.
        """
        client = bucket_with(
            f"warehouse-{stamp(NOW - timedelta(hours=6))}.sql.gz",
            f"warehouse-{stamp(NOW - timedelta(hours=1))}-before-m04-rerun.sql.gz")

        rows = mirror.available(mirror_settings, client=client, now=NOW)

        assert [r["age_hours"] for r in rows] == [6.0]

    def test_the_collision_suffix_is_still_automatic(self, mirror_settings):
        """`pipeline backup` appends -<n> when two land in the same second."""
        name = f"warehouse-{stamp(NOW - timedelta(hours=2))}-2.sql.gz"

        rows = mirror.available(mirror_settings, client=bucket_with(name), now=NOW)

        assert [r["name"] for r in rows] == [name]

    def test_anything_else_in_the_bucket_is_ignored(self, mirror_settings):
        client = bucket_with("archive-manifest.json", "notes.txt",
                             "warehouse-not-a-stamp.sql.gz")

        assert mirror.available(mirror_settings, client=client, now=NOW) == []

    def test_a_truncated_listing_without_a_cursor_is_refused(self, mirror_settings):
        """Silently mirroring a partial listing would look like a fresh bucket."""
        class Truncated(FakeS3):
            def list_objects_v2(self, **kwargs):
                return {"Contents": [], "IsTruncated": True}

        with pytest.raises(mirror.MirrorError, match="continuation token"):
            mirror.available(mirror_settings, client=Truncated({}), now=NOW)


class TestThePlan:
    def test_it_restores_when_the_bucket_is_ahead(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"

        decision = mirror.plan(mirror_settings, client=bucket_with(name), now=NOW)

        assert decision["action"] == "restore"
        assert decision["snapshot"]["name"] == name
        assert decision["stale"] is False

    def test_it_does_nothing_when_the_snapshot_is_already_in_place(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        mirror.record(mirror_settings, snapshot=name)

        decision = mirror.plan(mirror_settings, client=bucket_with(name), now=NOW)

        assert decision["action"] == "up-to-date"

    def test_force_restores_the_snapshot_already_in_place(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        mirror.record(mirror_settings, snapshot=name)

        decision = mirror.plan(mirror_settings, client=bucket_with(name),
                               now=NOW, force=True)

        assert decision["action"] == "restore"


class TestSilenceIsNotSuccess:
    """The failure this module exists to catch.

    A source whose backup timer has stopped raises no error anywhere: the
    bucket still answers, the snapshot in it still verifies, and the mirror
    still holds it. "Nothing to do" and "up to date" are the same sentence,
    and only the age of the newest snapshot tells them apart.
    """

    def test_an_old_newest_snapshot_is_stale_even_when_it_is_in_place(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(days=9))}.sql.gz"
        mirror.record(mirror_settings, snapshot=name)

        decision = mirror.plan(mirror_settings, client=bucket_with(name), now=NOW)

        assert decision["action"] == "up-to-date"
        assert decision["stale"] is True
        assert "backup timer may have stopped" in decision["reason"]

    def test_the_staleness_note_appears_on_a_restore_too(self, mirror_settings):
        """Same wording either way, so an alert matches one thing, not two."""
        name = f"warehouse-{stamp(NOW - timedelta(days=9))}.sql.gz"

        decision = mirror.plan(mirror_settings, client=bucket_with(name), now=NOW)

        assert decision["action"] == "restore"
        assert decision["stale"] is True

    def test_an_empty_bucket_is_stale_not_merely_empty(self, mirror_settings):
        decision = mirror.plan(mirror_settings, client=bucket_with(), now=NOW)

        assert decision["action"] == "none-available"
        assert decision["stale"] is True

    def test_the_limit_is_configurable(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(hours=50))}.sql.gz"
        relaxed = mirror_settings.model_copy(update={"mirror_max_snapshot_age_hours": 96})

        assert mirror.plan(mirror_settings, client=bucket_with(name), now=NOW)["stale"]
        assert not mirror.plan(relaxed, client=bucket_with(name), now=NOW)["stale"]


class TestTheDryRun:
    def test_it_downloads_nothing(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        client = bucket_with(name)

        result = mirror.pull(mirror_settings, client=client, dry_run=True, now=NOW)

        assert result["action"] == "restore"
        assert result["would_download_bytes"] == 100
        assert client.downloaded == []
        assert not (mirror_settings.mirror_inbox_dir / name).exists()

    def test_it_answers_the_same_question_as_the_real_run(self, mirror_settings):
        """A dry run that plans differently is a dry run nobody should trust."""
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        client = bucket_with(name)

        dry = mirror.pull(mirror_settings, client=client, dry_run=True, now=NOW)
        planned = mirror.plan(mirror_settings, client=client, now=NOW)

        assert dry["snapshot"] == planned["snapshot"]
        assert dry["reason"] == planned["reason"]


class TestTheDownload:
    def test_a_short_download_is_refused_rather_than_restored(self, mirror_settings):
        """The bucket said how big it is; a smaller file is a truncated one."""
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        client = bucket_with(name)
        client.objects[f"warehouse-backups/{name}"] = b"short"
        snapshot = mirror.available(mirror_settings, client=client, now=NOW)[0]
        snapshot["bytes"] = 100_000

        with pytest.raises(mirror.MirrorError, match="truncated"):
            mirror._download(mirror_settings, snapshot, client=client)

        assert list(mirror_settings.mirror_inbox_dir.glob("warehouse-*")) == []

    def test_an_interrupted_download_leaves_nothing_that_looks_finished(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"

        class Interrupted(FakeS3):
            def download_fileobj(self, bucket, key, handle):
                handle.write(b"half")
                raise OSError("connection reset")

        snapshot = mirror.available(mirror_settings,
                                    client=bucket_with(name), now=NOW)[0]
        with pytest.raises(OSError):
            mirror._download(mirror_settings, snapshot, client=Interrupted({}))

        assert not (mirror_settings.mirror_inbox_dir / name).exists()

    def test_the_manifest_comes_too_but_its_absence_is_not_fatal(self, mirror_settings):
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        client = bucket_with(name)
        client.objects[f"warehouse-backups/{mirror.manifest_name(name)}"] = b'{"rows": 1}'
        snapshot = mirror.available(mirror_settings, client=client, now=NOW)[0]

        mirror._download(mirror_settings, snapshot, client=client)

        assert (mirror_settings.mirror_inbox_dir / mirror.manifest_name(name)).is_file()

        # And again with no manifest in the bucket at all.
        bare = f"warehouse-{stamp(NOW - timedelta(hours=2))}.sql.gz"
        bare_client = bucket_with(bare)
        bare_snapshot = mirror.available(mirror_settings, client=bare_client, now=NOW)[0]
        mirror._download(mirror_settings, bare_snapshot, client=bare_client)

        assert (mirror_settings.mirror_inbox_dir / bare).is_file()


class TestTheStateFile:
    def test_it_survives_being_unreadable(self, mirror_settings):
        """A status command that dies on a corrupt state file dies when needed."""
        mirror_settings.mirror_state_dir.mkdir(parents=True, exist_ok=True)
        (mirror_settings.mirror_state_dir / mirror.STATE_FILE).write_text("{not json")

        assert "unreadable" in mirror.state(mirror_settings)
        # And a write past it starts clean rather than raising.
        assert mirror.record(mirror_settings, snapshot="x")["snapshot"] == "x"

    def test_it_is_replaced_atomically(self, mirror_settings):
        mirror.record(mirror_settings, snapshot="one")
        mirror.record(mirror_settings, warehouse_rows=5)

        written = json.loads(
            (mirror_settings.mirror_state_dir / mirror.STATE_FILE).read_text())

        assert written == {"snapshot": "one", "warehouse_rows": 5}
        assert list(mirror_settings.mirror_state_dir.glob("*.partial")) == []

    def test_the_inbox_keeps_only_what_is_in_place(self, mirror_settings):
        mirror_settings.mirror_inbox_dir.mkdir(parents=True, exist_ok=True)
        for name in ("warehouse-20260801T000000Z.sql.gz",
                     "warehouse-20260801T000000Z.manifest.json",
                     "warehouse-20260824T000000Z.sql.gz"):
            (mirror_settings.mirror_inbox_dir / name).write_bytes(b"x")

        removed = mirror._prune_inbox(mirror_settings, "warehouse-20260824T000000Z.sql.gz")

        assert removed == ["warehouse-20260801T000000Z.manifest.json",
                           "warehouse-20260801T000000Z.sql.gz"]
        assert [p.name for p in sorted(mirror_settings.mirror_inbox_dir.iterdir())] == [
            "warehouse-20260824T000000Z.sql.gz"]


class TestRefusals:
    def test_a_box_that_has_not_said_it_is_a_mirror_is_refused(self, settings):
        """MIRROR_ENABLED is an assertion about the box, not a convenience."""
        with pytest.raises(mirror.MirrorError, match="MIRROR_ENABLED"):
            mirror.plan(settings, client=bucket_with(), now=NOW)

    def test_a_promoted_box_refuses_to_be_overwritten(self, mirror_settings):
        """The interlock under `sectortrace-mirror promote`.

        Once this box has taken its source's place, its warehouse is no longer
        a copy of anything — so a timer somebody re-enables must not be able
        to replace it.
        """
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        mirror.promote(mirror_settings, now=NOW)

        with pytest.raises(mirror.MirrorError, match="promoted"):
            mirror.pull(mirror_settings, client=bucket_with(name), now=NOW)

        mirror.promote(mirror_settings, undo=True)
        assert mirror.plan(mirror_settings, client=bucket_with(name),
                           now=NOW)["action"] == "restore"

    def test_no_bucket_configured_says_which_variables(self, settings, tmp_path):
        bare = settings.model_copy(update={
            "mirror_enabled": True, "mirror_state_dir": tmp_path / "state"})

        with pytest.raises(mirror.MirrorError, match="MIRROR_BACKUP_S3_"):
            mirror.plan(bare, now=NOW)


class TestTheRestoreItWraps:
    """`pull` does not reimplement restoring; these pin how it uses the real one.

    The restore itself is `pipeline/backup.py`'s and is exercised there — it
    is a PostgreSQL path, so a snapshot cannot be restored end-to-end in the
    offline suite. What is testable here is the contract around it: force is
    passed (the target always holds the previous copy), success is recorded,
    and a failure records why without claiming the warehouse moved.
    """

    def test_a_successful_pull_records_what_is_now_in_place(self, mirror_settings, monkeypatch):
        from pipeline import backup as backup_module

        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"
        seen = {}

        def fake_restore(path, settings, force=False):
            seen["path"], seen["force"] = path, force
            return {"rows": 688_189, "tables": 77, "superseded": None,
                    "from": str(path), "restored": "postgres"}

        monkeypatch.setattr(backup_module, "restore", fake_restore)
        result = mirror.pull(mirror_settings, client=bucket_with(name), now=NOW)

        assert seen["force"] is True
        assert seen["path"].name == name
        assert result["action"] == "restored"

        current = mirror.state(mirror_settings)
        assert current["snapshot"] == name
        assert current["warehouse_rows"] == 688_189

    def test_a_failed_restore_says_what_the_box_still_holds(self, mirror_settings, monkeypatch):
        from pipeline import backup as backup_module

        held = "warehouse-20260801T000000Z.sql.gz"
        mirror.record(mirror_settings, snapshot=held)
        name = f"warehouse-{stamp(NOW - timedelta(hours=3))}.sql.gz"

        def fake_restore(path, settings, force=False):
            raise backup_module.BackupError("fails its own verification")

        monkeypatch.setattr(backup_module, "restore", fake_restore)
        with pytest.raises(mirror.MirrorError, match="still holds " + held):
            mirror.pull(mirror_settings, client=bucket_with(name), now=NOW)

        current = mirror.state(mirror_settings)
        assert current["snapshot"] == held
        assert "fails its own verification" in current["last_failure"]


class TestSupersededSnapshots:
    """`restore --force` sets aside what it replaces, and a mirror does that nightly.

    `backup.prune` deliberately never deletes a labelled backup, because on a
    collecting deployment that copy is the way back from a wrong restore. The
    departure here is narrow and argued in the module: what a restore replaces
    on a mirror is itself a copy the source still holds.
    """

    def superseded(self, settings, *stamps):
        settings.backup_dir.mkdir(parents=True, exist_ok=True)
        for moment in stamps:
            name = f"warehouse-{moment}-{mirror.SUPERSEDED_LABEL}"
            (settings.backup_dir / f"{name}.sql.gz").write_bytes(b"x")
            (settings.backup_dir / f"{name}.manifest.json").write_text("{}")

    def test_it_keeps_the_newest_and_their_manifests_go_too(self, mirror_settings):
        self.superseded(mirror_settings, "20260801T000000Z", "20260810T000000Z",
                        "20260820T000000Z", "20260824T000000Z")

        removed = mirror.prune_superseded(mirror_settings, keep=2)

        assert removed == ["warehouse-20260810T000000Z-superseded-by-restore.sql.gz",
                           "warehouse-20260801T000000Z-superseded-by-restore.sql.gz"]
        assert sorted(p.name for p in mirror_settings.backup_dir.iterdir()) == [
            "warehouse-20260820T000000Z-superseded-by-restore.manifest.json",
            "warehouse-20260820T000000Z-superseded-by-restore.sql.gz",
            "warehouse-20260824T000000Z-superseded-by-restore.manifest.json",
            "warehouse-20260824T000000Z-superseded-by-restore.sql.gz"]

    def test_zero_keeps_every_one_of_them(self, mirror_settings):
        self.superseded(mirror_settings, "20260801T000000Z", "20260824T000000Z")

        assert mirror.prune_superseded(mirror_settings, keep=0) == []
        assert len(list(mirror_settings.backup_dir.glob("*.sql.gz"))) == 2

    def test_a_backup_somebody_labelled_by_hand_is_left_alone(self, mirror_settings):
        """A retention rule nobody asked for is how the useful copy disappears."""
        self.superseded(mirror_settings, "20260801T000000Z", "20260810T000000Z",
                        "20260820T000000Z")
        theirs = mirror_settings.backup_dir / "warehouse-20260101T000000Z-before-the-migration.sql.gz"
        theirs.write_bytes(b"x")
        automatic = mirror_settings.backup_dir / "warehouse-20260101T000000Z.sql.gz"
        automatic.write_bytes(b"x")

        mirror.prune_superseded(mirror_settings, keep=1)

        assert theirs.is_file()
        assert automatic.is_file()


class TestMetrics:
    def test_a_mirror_that_has_never_synced_reports_no_success(self, mirror_settings):
        """Never worked and stopped working a month ago are the same problem."""
        text = mirror.metrics(mirror_settings, now=NOW)

        assert "sectortrace_mirror_last_success_timestamp_seconds" not in text
        assert 'sectortrace_mirror_info{source="sectortrace.example.org"' in text
        assert "sectortrace_mirror_last_sync_success 0" in text

    def test_it_reports_the_age_of_the_data_not_of_the_run(self, mirror_settings):
        """The question anyone quoting a mirrored figure is really asking."""
        taken = NOW - timedelta(days=3)
        mirror.record(mirror_settings,
                      snapshot="warehouse-x.sql.gz",
                      snapshot_taken_at=taken.isoformat(timespec="seconds"),
                      last_sync_finished_at=NOW.isoformat(timespec="seconds"),
                      last_success_at=NOW.isoformat(timespec="seconds"),
                      last_sync_status="ok", warehouse_rows=688_189)

        text = mirror.metrics(mirror_settings, now=NOW)

        assert f"sectortrace_mirror_snapshot_timestamp_seconds {int(taken.timestamp())}" in text
        assert f"sectortrace_mirror_last_sync_timestamp_seconds {int(NOW.timestamp())}" in text
        assert "sectortrace_mirror_warehouse_rows 688189" in text
        assert "sectortrace_mirror_last_sync_success 1" in text

    def test_the_file_is_replaced_atomically(self, mirror_settings, tmp_path):
        """node_exporter reads the directory whenever it likes, and a
        half-written file is a parse error that takes every other collector's
        output with it."""
        destination = tmp_path / "textfile" / "sectortrace_mirror.prom"

        mirror.write_metrics(mirror_settings, destination, now=NOW)

        assert destination.read_text().startswith("# HELP sectortrace_mirror_info")
        assert list(destination.parent.glob("*.partial")) == []

    def test_a_label_with_a_quote_in_it_cannot_break_the_format(self, mirror_settings):
        odd = mirror_settings.model_copy(update={"mirror_source_label": 'a"b'})

        assert "source=\"a'b\"" in mirror.metrics(odd, now=NOW)


class TestHowOldTheDataIs:
    """The question anyone quoting a figure off a mirror is really asking.

    Not "when did this box last do some work" — a mirror that syncs
    faithfully every night from a source that stopped taking backups a month
    ago has a spotless record and month-old evidence.
    """

    def test_snapshot_mode_dates_the_data_by_the_snapshot_not_the_sync(self, mirror_settings):
        mirror.record(mirror_settings,
                      snapshot_taken_at=(NOW - timedelta(days=30)).isoformat(timespec="seconds"),
                      last_success_at=NOW.isoformat(timespec="seconds"),
                      last_sync_status="ok")

        report = mirror.status(mirror_settings, now=NOW)

        assert report["data_age_hours"] == 720.0
        assert report["stale"] is True

    def test_tunnel_mode_dates_it_by_the_verified_copy(self, mirror_settings):
        """There is no file and no stamp; the successful copy is the fact."""
        mirror.record(mirror_settings,
                      last_success_at=(NOW - timedelta(hours=4)).isoformat(timespec="seconds"),
                      last_sync_status="ok")

        report = mirror.status(mirror_settings, now=NOW)

        assert report["data_age_hours"] == 4.0
        assert report["stale"] is False

    def test_the_metric_follows_the_same_rule(self, mirror_settings):
        copied = NOW - timedelta(hours=4)
        mirror.record(mirror_settings, last_success_at=copied.isoformat(timespec="seconds"),
                      last_sync_status="ok")

        text = mirror.metrics(mirror_settings, now=NOW)

        assert f"sectortrace_mirror_snapshot_timestamp_seconds {int(copied.timestamp())}" in text


class TestStatus:
    def test_it_needs_no_credentials_to_say_what_is_in_place(self, mirror_settings):
        """The common case is an operator asking, not a machine checking."""
        mirror.record(mirror_settings, snapshot="warehouse-x.sql.gz",
                      snapshot_taken_at=(NOW - timedelta(hours=5)).isoformat(timespec="seconds"))

        report = mirror.status(mirror_settings, now=NOW)

        assert report["snapshot"] == "warehouse-x.sql.gz"
        assert report["data_age_hours"] == 5.0
        assert report["stale"] is False

    def test_a_mirror_that_has_never_synced_is_stale(self, mirror_settings):
        report = mirror.status(mirror_settings, now=NOW)

        assert report["snapshot"] is None
        assert report["stale"] is True

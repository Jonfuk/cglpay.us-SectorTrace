"""The Phase 3 harness, offline.

What matters about a benchmark is not the numbers — those are the output —
but that it measures the right thing, measures it the same way twice, and
cannot damage what it is measuring. Those are all testable without a server
and without caring how fast anything is, so none of the assertions here are
about durations.
"""
from __future__ import annotations

import json

import pytest

from pipeline import benchmark, db


class TestTheCasesItMeasures:
    def test_every_case_says_why_it_is_there(self):
        """A case with no argument for its presence is one nobody will know
        whether to keep when it starts failing."""
        for case in benchmark._read_cases():
            assert case["why"].strip(), case["name"]
            assert callable(case["call"])

    def test_case_names_are_unique(self):
        names = [case["name"] for case in benchmark._read_cases()]
        assert len(names) == len(set(names))

    def test_the_names_say_which_front_end(self):
        """Reports are read months later. `portal.` and `admin.` are the
        difference between a public page and an operator one, and Phase 4
        will care which it made faster."""
        for case in benchmark._read_cases():
            assert case["name"].split(".")[0] in {"portal", "admin"}, case["name"]


class TestPercentiles:
    def test_they_come_back_ordered(self):
        measured = benchmark._percentiles([0.003, 0.001, 0.002])
        assert measured["min_ms"] <= measured["p50_ms"] <= measured["max_ms"]
        assert measured["n"] == 3

    def test_a_single_sample_is_all_of_them(self):
        measured = benchmark._percentiles([0.005])
        assert measured["min_ms"] == measured["p99_ms"] == measured["max_ms"] == 5.0

    def test_the_first_run_is_discarded(self):
        """It pays for the page cache on one backend and the plan cache on the
        other, and a warm portal pays neither."""
        calls = []
        benchmark._time(lambda: calls.append(1), repetitions=3)
        assert len(calls) == 4, "the warm-up run should not be counted"

    def test_a_result_with_no_length_is_recorded_as_such(self):
        assert benchmark._time(lambda: 42, repetitions=2)["rows"] is None
        assert benchmark._time(lambda: [1, 2], repetitions=2)["rows"] == 2


class TestItRunsAgainstARealWarehouse:
    def test_a_report_has_every_section(self, conn, settings):
        conn.commit()
        report = benchmark.benchmark(settings)
        assert report["environment"]["backend"] == "sqlite"
        assert report["environment"]["server"].startswith("sqlite ")
        assert "reads" in report and report["reads"]
        assert "write_throughput" in report
        assert "write_contention" in report

    def test_every_read_case_runs(self, conn, settings):
        """On an empty-but-migrated warehouse. A case that raises is recorded
        rather than raised, so this checks none of them did."""
        conn.commit()
        report = benchmark.benchmark(settings, writes=False)
        failed = [case for case in report["reads"] if "error" in case]
        assert not failed, failed

    def test_a_failing_case_does_not_take_the_rest_of_the_run_with_it(
            self, conn, settings):
        """The cases read on a write connection, and on PostgreSQL a failed
        statement aborts the transaction — so one broken case reported itself
        and then made every later case report "current transaction is
        aborted". Sixteen findings, fifteen of them fictional, which is worse
        than the one real one being missed.

        Asserted on SQLite, where the rollback is a no-op, because what is
        being tested is that the harness performs one at all: the cases either
        side of the broken one have to come back measured.
        """
        cases = [
            {"name": "before", "why": "runs", "call": lambda c: c.execute(
                "SELECT 1").fetchone()},
            {"name": "broken", "why": "does not", "call": lambda c: c.execute(
                "SELECT * FROM a_table_that_is_not_there").fetchone()},
            {"name": "after", "why": "must still be measured",
             "call": lambda c: c.execute("SELECT 1").fetchone()},
        ]
        results = {r["name"]: r for r in benchmark.read_latency(conn, cases)}

        assert "error" in results["broken"]
        assert "error" not in results["before"], results["before"]
        assert "error" not in results["after"], results["after"]

    def test_it_records_the_row_counts_it_measured(self, conn, settings):
        """A comparison between two backends is only a comparison if they hold
        the same rows, so each report carries its own evidence of what it was
        measuring rather than inheriting the claim from Phase 2."""
        conn.commit()
        report = benchmark.benchmark(settings, writes=False)
        assert "contracts" in report["tables"]
        assert report["tables"]["contracts"] == 0

    def test_the_report_is_written_where_it_is_told(self, conn, settings, tmp_path):
        conn.commit()
        report = benchmark.benchmark(settings, writes=False,
                                      output_dir=tmp_path / "benchmarks")
        written = json.loads(
            (tmp_path / "benchmarks" / report["written_to"].split("\\")[-1].split("/")[-1])
            .read_text(encoding="utf-8"))
        assert written["environment"]["backend"] == "sqlite"

    def test_the_filename_carries_the_backend_and_the_time(self, conn, settings,
                                                            tmp_path):
        conn.commit()
        report = benchmark.benchmark(settings, writes=False, output_dir=tmp_path)
        assert report["written_to"].endswith("-sqlite.json")


class TestItCannotDamageWhatItMeasures:
    def test_writes_go_somewhere_else_entirely(self, conn, settings):
        """The measured warehouse must contain exactly what it did before.

        A benchmark that inserted two thousand rows into the warehouse would
        leave it no longer equal to the other backend's, which is the property
        every comparison here rests on.
        """
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM parse_failures").fetchone()[0]
        benchmark.benchmark(settings, reads=False)
        assert conn.execute(
            "SELECT COUNT(*) FROM parse_failures").fetchone()[0] == before

    def test_the_scratch_warehouse_is_not_the_real_one(self, settings):
        with benchmark.scratch_warehouse(settings) as scratch:
            assert scratch.settings.database_path != settings.database_path
            assert db.backend_of(scratch.conn) == "sqlite"
            path = scratch.settings.database_path
            assert path.is_file()
        assert not path.is_file(), "the scratch warehouse outlived its context"

    def test_the_throughput_run_tidies_up(self, settings):
        with benchmark.scratch_warehouse(settings) as scratch:
            measured = benchmark.write_throughput(scratch.conn, rows=20)
            assert measured["rows"] == 20
            assert measured["rows_per_second"] > 0
            assert scratch.conn.execute(
                "SELECT COUNT(*) FROM parse_failures").fetchone()[0] == 0

    def test_the_contention_run_tidies_up(self, settings):
        with benchmark.scratch_warehouse(settings) as scratch:
            measured = benchmark.write_contention(scratch.settings,
                                                   counts=(1, 2), rows_each=10)
            assert measured["errors"] == []
            assert [e["writers"] for e in measured["by_writers"]] == [1, 2]
            assert scratch.conn.execute(
                "SELECT COUNT(*) FROM parse_failures").fetchone()[0] == 0

    def test_scaling_is_measured_against_one_writer(self, settings):
        """Not against thread lifetimes. Serialised writers are all still
        *alive* for the whole run, so a ratio of elapsed times reads about N
        whether anything overlapped or not — it could not tell the two
        backends apart, which was the only thing it was for."""
        with benchmark.scratch_warehouse(settings) as scratch:
            measured = benchmark.write_contention(scratch.settings,
                                                   counts=(1, 2), rows_each=10)
            one, two = measured["by_writers"]
            assert one["scaling_vs_one_writer"] == 1.0
            assert two["scaling_vs_one_writer"] is not None


class TestComparingTwoReports:
    def _report(self, cases):
        return {"environment": {"backend": "sqlite"}, "reads": cases}

    def test_a_ratio_per_case(self):
        left = self._report([{"name": "a", "p50_ms": 10.0, "p95_ms": 20.0}])
        right = self._report([{"name": "a", "p50_ms": 5.0, "p95_ms": 40.0}])
        row = benchmark.compare(left, right)[0]
        assert row["p50_ratio"] == 0.5
        # Both are reported because they frequently disagree, and only one of
        # them is what somebody waiting for a page notices.
        assert row["p95_ratio"] == 2.0

    def test_a_case_missing_from_one_side_is_said_so(self):
        left = self._report([{"name": "a", "p50_ms": 10.0, "p95_ms": 20.0}])
        row = benchmark.compare(left, self._report([]))[0]
        assert "not measured on both" in row["note"]

    def test_a_case_that_errored_carries_its_error(self):
        left = self._report([{"name": "a", "error": "boom"}])
        right = self._report([{"name": "a", "p50_ms": 1.0, "p95_ms": 1.0}])
        assert benchmark.compare(left, right)[0]["note"] == "boom"


@pytest.mark.parametrize("column", ["p50_ms", "p95_ms", "p99_ms", "n"])
def test_the_shape_a_later_phase_will_read(conn, settings, column):
    """Phase 4 diffs its numbers against these files. The keys are the
    interface, so they are pinned."""
    conn.commit()
    report = benchmark.benchmark(settings, writes=False)
    assert column in report["reads"][0]

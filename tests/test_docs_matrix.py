"""Machine-owned documentation blocks (BETA-067).

The generator is deterministic, the committed tree is in sync (this is the CI
guard — change a registry without `docs-sync` and this fails), and
`docs-check` / `docs-sync` behave on a hand-edited block.
"""
from __future__ import annotations

from typer.testing import CliRunner

from pipeline import cli as cli_module
from pipeline import docs_matrix
from pipeline.web import datasets


def test_the_matrix_is_deterministic():
    assert docs_matrix.source_capability_matrix() == docs_matrix.source_capability_matrix()


def test_every_collecting_module_is_a_row_with_its_registry_licence():
    from pipeline import licences

    body = docs_matrix.source_capability_matrix()
    for dataset in datasets.DATASETS:
        assert f"| `{dataset.module}` |" in body, f"{dataset.module} missing from the matrix"
        licence = licences.for_module(dataset.module)
        # The licence column is read from the registry, not retyped.
        assert licence is not None and licence.name.replace("|", "\\|") in body


def test_the_committed_source_matrix_is_in_sync():
    """If this fails, a registry changed and `pipeline docs-sync` was not run.
    Run it and commit the docs/ change with the code change."""
    assert docs_matrix.check(["source-capability-matrix"]) == []


def test_render_is_bounded_by_its_markers():
    block = docs_matrix.render("source-capability-matrix")
    assert block.startswith("<!-- BEGIN GENERATED: source-capability-matrix -->")
    assert block.rstrip().endswith("<!-- END GENERATED: source-capability-matrix -->")


def test_locate_raises_when_a_marker_is_missing():
    import pytest

    with pytest.raises(KeyError):
        docs_matrix._locate("no markers here", "source-capability-matrix")


def _redirect_to_tmp(monkeypatch, tmp_path, body: str):
    path = tmp_path / "SOURCES.md"
    name = "source-capability-matrix"
    path.write_text(
        "intro\n\n"
        f"<!-- BEGIN GENERATED: {name} -->\n{body}<!-- END GENERATED: {name} -->\n"
        "\ntail\n", encoding="utf-8")
    monkeypatch.setitem(docs_matrix.GENERATED_BLOCKS, name,
                        (path, docs_matrix.source_capability_matrix))
    return path


def test_check_flags_a_hand_edited_block_and_sync_repairs_it(monkeypatch, tmp_path):
    path = _redirect_to_tmp(monkeypatch, tmp_path, "stale hand-written content\n")

    stale = docs_matrix.check(["source-capability-matrix"])
    assert len(stale) == 1 and stale[0]["diff"]

    changed = docs_matrix.sync(["source-capability-matrix"])
    assert changed == ["source-capability-matrix"]
    assert docs_matrix.check(["source-capability-matrix"]) == []
    # The hand-owned text around the markers is untouched.
    text = path.read_text(encoding="utf-8")
    assert text.startswith("intro\n") and text.rstrip().endswith("tail")

    # Idempotent second sync.
    assert docs_matrix.sync(["source-capability-matrix"]) == []


def test_docs_check_cli_exits_zero_on_a_synced_tree():
    result = CliRunner().invoke(cli_module.app, ["docs-check"])
    assert result.exit_code == 0
    assert "in sync" in result.stdout


def test_docs_check_cli_exits_nonzero_on_a_stale_block(monkeypatch, tmp_path):
    _redirect_to_tmp(monkeypatch, tmp_path, "stale\n")
    result = CliRunner().invoke(cli_module.app, ["docs-check"])
    assert result.exit_code == 1
    assert "docs-sync" in result.stdout

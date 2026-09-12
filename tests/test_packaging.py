from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_deployment_paths_do_not_request_removed_postgres_extra() -> None:
    """PostgreSQL is core, so deployment syncs must use the declared project."""
    for relative in (
        "Dockerfile",
        "deploy/Dockerfile.documents",
        "deploy/document-batch-all.sh",
        "start.cmd",
        ".github/workflows/tests.yml",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "--extra postgres" not in text, relative

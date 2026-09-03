"""Running export targets, for both the CLI and the browser.

Same reasoning as pipeline/runner.py: the CLI was the only caller, so the loop
over targets lived inside its command alongside the lines it printed. It is
not the only caller now, and an export written by the operator UI has to be
the export `pipeline export` writes -- same files, same directories, same
companion provenance -- because these are the artefacts that leave the project
and get quoted.

What is deliberately *not* here is `--push`. Pushing tabs to Google Sheets
needs credentials and, more to the point, needs someone watching it: it writes
to a shared document that other people are reading. It stays a CLI flag.
"""
from __future__ import annotations

from pathlib import Path

# Order matters, and only for the last one: `bundle` zips what is in the export
# directory, so under `all` it must run after the three targets that put files
# there. A bundle taken first would be a zip of the previous run.
TARGETS: tuple[str, ...] = ("sheets", "geojson", "echarts", "docs", "bundle")


class ExportError(ValueError):
    """An export target that does not exist."""


def run_targets(conn, targets: list[str], base: Path, docs_dir: Path, settings,
                 push: bool = False) -> list[dict]:
    """Write each target, and report what each one produced.

    Imports are inside the function, as they were in the CLI command: the
    export modules pull in the whole schema layer, and `pipeline web` should
    not pay for that at startup to serve a review queue.
    """
    from pipeline.exports import bundle as bundle_export
    from pipeline.exports import docs as docs_export
    from pipeline.exports import echarts as echarts_export
    from pipeline.exports import geojson as geojson_export
    from pipeline.exports import sheets as sheets_export

    unknown = [name for name in targets if name not in TARGETS]
    if unknown:
        raise ExportError(
            f"Unknown export target {unknown[0]!r}. "
            f"Use {', '.join(TARGETS)} or all.")

    results: list[dict] = []
    for name in targets:
        if name == "sheets":
            paths = sheets_export.export_sheets(conn, base / "sheets", push, settings)
            noun = "tabs"
        elif name == "geojson":
            paths = geojson_export.export_all(conn, base / "geojson")
            noun = "layers"
        elif name == "echarts":
            paths = echarts_export.export_all(conn, base / "echarts")
            noun = "charts"
        elif name == "bundle":
            # The only target that reads the export directory rather than the
            # warehouse. Refusing an empty one is deliberate: a zip holding a
            # README and nothing else is an artefact that looks like a
            # successful export.
            try:
                paths = bundle_export.write_bundle(base)
            except bundle_export.BundleError as exc:
                raise ExportError(str(exc)) from None
            noun = "bundles"
        else:
            paths = [docs_export.write_data_dictionary(
                conn, settings.migrations_dir / "postgres", docs_dir)]
            noun = "documents"

        results.append({
            "target": name, "noun": noun,
            "count": len(paths), "paths": [str(path) for path in paths],
        })
    return results


def resolve_targets(target: str) -> list[str]:
    """"all" or one name, as a list. Raises for anything else."""
    if target == "all":
        return list(TARGETS)
    if target not in TARGETS:
        raise ExportError(
            f"Unknown export target {target!r}. Use {', '.join(TARGETS)} or all.")
    return [target]

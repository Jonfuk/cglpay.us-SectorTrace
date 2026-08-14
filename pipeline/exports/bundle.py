"""One zip of everything the exports produced, with a manifest and a README.

W-16: a researcher who wants "the evidence" was clicking nine CSVs, four
GeoJSONs and five JSONs one at a time, and the `.provenance.json` beside each
one is a second click most people do not make. A companion that has to be
fetched separately is a companion that gets lost, and constraint 1 is the one
thing this project will not trade.

So the bundle is not a convenience wrapper. Three things go in it that the
individual downloads cannot carry:

  * **The manifest**, which names every file and its SHA-256. A bundle that
    arrives somewhere can be checked against it — including by someone who did
    not download it.
  * **The pairing**, stated. Each data file is listed with the provenance
    companion that belongs to it, and a file with no companion is listed as
    such rather than silently looking like the rest. That check has never
    existed anywhere else: the export writers pair the two at write time, and
    nothing afterwards ever looked.
  * **The README**, which says what the reader is holding, where the caveats
    are, and that the licences are per source rather than one blanket grant.

What it deliberately does not do is read the warehouse. The bundle is taken
over the export directory as it stands, so it holds exactly the files the
operator can see on the Exports tab — no more, and nothing regenerated behind
their back. If those files are stale, the bundle is stale in the same way and
by the same amount, which is what the staleness line beside them is for.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger()

# Where the zip lands, relative to the export root. Its own directory so the
# bundle can exclude itself: a bundle that included the previous bundle would
# double in size every time anyone pressed the button.
BUNDLE_DIR = "bundle"

MANIFEST_NAME = "manifest.json"
README_NAME = "README.md"

PROVENANCE_SUFFIX = ".provenance.json"

# Read in blocks rather than whole: treatment_numbers.geojson is 23 MB and
# this runs over every file in the directory.
HASH_BLOCK = 1024 * 1024


class BundleError(Exception):
    """Nothing to bundle, which is a state worth a message rather than an
    empty zip that looks like a successful export."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(HASH_BLOCK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def collect(base: Path) -> list[Path]:
    """Every export file, excluding the bundle directory itself.

    Symlinks are resolved and anything landing outside the export root is
    dropped, the same rule `pipeline/web/artefacts.py` applies to downloads: a
    link planted in the export tree pointing at the warehouse must not be able
    to travel out inside a zip either.
    """
    if not base.is_dir():
        return []
    root = base.resolve()
    bundle_dir = (base / BUNDLE_DIR).resolve()

    found = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        real = path.resolve()
        if not real.is_relative_to(root) or real.is_relative_to(bundle_dir):
            continue
        found.append(path)
    return found


def manifest_for(base: Path, files: list[Path]) -> dict:
    """The manifest, with each data file paired to its provenance companion.

    The pairing is the part worth reading. `contracts.geojson` and
    `contracts.geojson.provenance.json` are one artefact and two files, and
    listing them as siblings would double the manifest and halve its use --
    worse, it would make a data file with no provenance look exactly like one
    that has it.
    """
    companions = {
        path.relative_to(base).as_posix()[: -len(PROVENANCE_SUFFIX)]: path
        for path in files if path.name.endswith(PROVENANCE_SUFFIX)
    }

    entries = []
    for path in files:
        relative = path.relative_to(base).as_posix()
        if relative.endswith(PROVENANCE_SUFFIX):
            continue
        companion = companions.get(relative)
        entries.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "provenance": (companion.relative_to(base).as_posix()
                            if companion else None),
            "provenance_sha256": _sha256(companion) if companion else None,
        })

    # A companion whose subject has gone is still in the zip -- dropping it
    # would misreport what the file holds -- so it is named here too.
    orphans = sorted(subject + PROVENANCE_SUFFIX
                      for subject in companions
                      if not (base / subject).is_file())

    return {
        "bundle": "SectorTrace evidence export",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "export_root": str(base),
        "file_count": len(entries),
        "bytes": sum(entry["bytes"] for entry in entries),
        "without_provenance": [entry["path"] for entry in entries
                                if entry["provenance"] is None],
        "orphan_provenance": orphans,
        "files": entries,
        # Named so a reader -- or a test -- can account for every member of the
        # zip. These two are written by the bundler and have no provenance of
        # their own to carry.
        "also_included": [README_NAME, MANIFEST_NAME],
    }


def readme_for(manifest: dict) -> str:
    """What the reader is holding, in the file they will open first."""
    lines = [
        "# SectorTrace evidence export",
        "",
        f"Generated {manifest['generated_at']}.",
        f"{manifest['file_count']} data files, "
        f"{manifest['bytes'] / 1_048_576:.1f} MB.",
        "",
        "## What this is",
        "",
        "Public-domain evidence on the England substance misuse treatment",
        "sector, collected with full provenance: every row in these files came",
        "from a document at a URL, fetched at a recorded time, and the exact",
        "bytes of that document were archived and hashed.",
        "",
        "## What is beside each file",
        "",
        "Every data file has a companion `.provenance.json` naming the tables",
        "it was built from, their row counts, the source systems and the",
        "retrieval window. `manifest.json` lists the pairing, with a SHA-256",
        "for each file so this bundle can be checked against it.",
        "",
    ]

    if manifest["without_provenance"]:
        lines += [
            "**Files in this bundle with no provenance companion:**",
            "",
            *(f"  - `{path}`" for path in manifest["without_provenance"]),
            "",
            "Treat those as unverified. Every file this pipeline's export layer",
            "writes gets a companion; one without is a file that arrived in the",
            "export directory some other way.",
            "",
        ]

    lines += [
        "## Before quoting any of it",
        "",
        "Read `docs/CAVEATS.md` in the SectorTrace repository. It leads with",
        "the figures that must **not** be computed from this data — no",
        "arithmetic across evidence layers, no cross-year census differencing,",
        "no total contract value. Those are not stylistic preferences; they are",
        "the reason the figures here can be defended.",
        "",
        "## Licence",
        "",
        "Not one licence. Most sources are Open Government Licence v3.0, but",
        "the workforce census is NHS Benchmarking content and council documents",
        "vary by council. Each CSV written by the portal export carries its own",
        "`# licence:` header lines; `docs/SOURCES.md` records the terms per",
        "source. Check before republishing.",
        "",
    ]
    return "\n".join(lines)


def write_bundle(base: Path) -> list[Path]:
    """Zip the export directory. Returns the one path written.

    A list of one, so it fits the shape every other export target reports in.
    """
    files = collect(base)
    if not files:
        raise BundleError(
            f"Nothing to bundle: {base} holds no export files. Run the sheets, "
            "geojson and echarts targets first — a bundle of nothing is an "
            "artefact that looks like a successful export.")

    manifest = manifest_for(base, files)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    target = base / BUNDLE_DIR / f"sectorTrace-evidence-{stamp}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)

    # Written to a neighbouring name and moved into place, so an interrupted
    # run leaves no half-zip sitting in the listing looking downloadable.
    partial = target.with_suffix(".zip.partial")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(base).as_posix())
        archive.writestr(README_NAME, readme_for(manifest))
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
    partial.replace(target)

    log.info("export.bundle_written", path=str(target),
              files=manifest["file_count"], bytes=target.stat().st_size,
              without_provenance=len(manifest["without_provenance"]))
    return [target]

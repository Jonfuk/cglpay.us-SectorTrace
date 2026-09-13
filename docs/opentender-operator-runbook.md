# OpenTender operator cross-check

The m40_opentender_registry module is the bounded implementation of JON-28's Phase A/B
recommendation. It reads one explicitly staged OpenTender UK package from the
[OCP Data Registry](https://data.open-contracting.org/en/publication/92), or
fetches one explicitly configured package URL through the shared HTTP client.
It is disabled by default and marked operator-only.

## Run boundary

Set OPENTENDER_ENABLED=true and exactly one of:

    OPENTENDER_PACKAGE_PATH=/path/to/opentender.jsonl
    OPENTENDER_PACKAGE_URL=https://...

Then run the module explicitly:

    uv run pipeline run m40_opentender_registry --limit 1000

--since filters on the package's published date. --limit bounds valid
observations, and OPENTENDER_MAX_PACKAGE_BYTES bounds the downloaded or
staged package. No real source URL belongs in CI or an offline test.

## Stored outputs

- procurement_mirror_packages records the package URL, retrieval time,
  exact package SHA-256, raw archive reference, observed period, parser
  version, licence and the fixed operator_only export disposition.
- procurement_mirror_observations records one compiled-release observation
  per source record, including native OCID, buyer/title/date/CPV/value fields,
  record hash and reconciliation disposition.
- review_queue receives every non-exact result:
  opentender_candidate_match, opentender_ambiguous_match or
  opentender_unmatched.
- parse_failures records malformed records and records that do not use the
  expected UK OpenTender OCID prefix.

The module never inserts or updates contracts, never reconstructs a
tender-to-award lifecycle, and is absent from PUBLIC_DATASETS and
ENDPOINT_MODULES. The package's advertised CC BY-NC-SA 4.0 terms require a
human decision before any reuse, promotion or public export.

## Reconciliation meaning

An exact OCID match means the two sources share a contracting-process
identifier. Buyer/title/date/CPV/value matches are only candidate pointers,
especially where the OCID differs; a person must inspect the primary source
before taking any action. The mirror is a coverage and gap-check aid, not a
second procurement evidence layer or a source for headline totals.

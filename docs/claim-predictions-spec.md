# Claim-prediction heads (034G proper) — build spec

**Status: approved (2026-08-31) and built on `beta`.** Migration `0082`,
`pipeline/nlp/claims{,_features,_train,_predict,_eval}.py`, the three CLI
commands and the offline tests are in the tree. What remains open is the
`corpus='source'` retrain and a separate go-ahead for anything that consumes
predictions beyond a CLI-inspected finding aid — see *Open* at the end.
Roadmap register: **D-09**.

## Why now

The 034G gate is green on the beta box. Per-category decided-example counts
(positives / negatives) from the model-assisted review pass:

| category | positives | negatives |
|---|---|---|
| `vacancy_pressure` | 62 | 49 |
| `agency_reliance` | 58 | 70 |
| `tupe_transfer` | 48 | 64 |

Three categories `ready`, quorum (`MIN_CATEGORIES_READY = 3`) met,
`MIN_PER_CLASS = 25` + `HELDOUT_PER_CLASS = 10`, the inter-reviewer check
advisory by owner decision (`MIN_DOUBLE_REVIEWED = 0`, single-reviewer
corpus). `cost_pressure`, `waiting_time`, `funding_reduction` stay in
`advisory` — their NEGATIVE class cannot reach the floor and no review pass
fixes that. See D-08 in `docs/upgrade-roadmap.md`.

## Decisions taken (interview, 2026-08-31)

| # | decision |
|---|---|
| Sequencing | **Full written spec first** (this document), sign-off, then build. |
| Corpus | **Train on the beta-box corpus now**, marked `corpus_status = 'experimental'` on every head, recorded here and in the roadmap. A retrain on the authoritative source warehouse is a required later milestone (`corpus_status = 'authoritative'`), not a nice-to-have. |
| Model | **Build both** — logistic regression on the existing 034A chunk embeddings, and SetFit — and **compare per category** on the same held-out set. Keep whichever clears the precision bar; **logreg wins ties**. The logreg head is **pure Python + numpy** (full-batch gradient descent, L2, class-balanced), not scikit-learn: at a few hundred vectors it is milliseconds, it runs in the default test suite with no extra, and a coefficient vector is the more transparent artifact. scikit-learn is pulled only as a SetFit dependency. |
| Precision gate | **`MIN_HEAD_PRECISION = 0.80`, configurable** via `--min-precision`; precision favoured over recall. The value applied is recorded on every head row and on the `nlp_run`. |
| Naming | **Model-neutral.** Table `document_claim_predictions`, registry `claim_head_versions`, CLI `nlp claims-train` / `claims-eval` / `claims-predict`, constant `MIN_HEAD_PRECISION`. Model type is a column, never in a name. |
| Predict population | **All live chunks that have a 034A embedding row** (labelled or not); `split` marks which were in the fit. |
| Evaluation | **Held-out only** — the deterministic 10/class the gate reserves, carved before the fit, never seen by it. No k-fold, no seed sweep. |
| Tests | **Tiny fixture corpus + a new `slow` marker** (deselected by `addopts`, alongside `integration`). A real logreg head trains in the default suite; the SetFit fine-tune is one `slow` test. |
| `model_version` | **Composite string**: `<model_type>-<category>-<corpus_cutoff>-<hash8>`, e.g. `logreg-vacancy_pressure-20260831-a1b2c3d4`. `hash8` is the first 8 chars of `config_sha256` (hyperparams + embedder id + held-out seed + corpus cutoff). |
| Bake-off record | **Both heads persisted.** Every trained head — both models, every category — gets a `claim_head_versions` row with its held-out precision/recall/F1 and a `status` of `passed` / `quarantined` / `lost-bakeoff`. `selected = 1` marks the one head per category that writes predictions. |
| Predict threshold | **Run whatever passed, even one head.** Zero selected heads → no-op with a logged warning. The gate is per-head, not per-run. |
| Spec home | This file, plus a findings-register entry (**D-09**) in `docs/upgrade-roadmap.md`. |

## What it builds

One **binary** classifier head per `ready` gate category, trained on that
category's reviewer-labelled positives and negatives (as `gate._label_for`
defines them). Two candidate models per category — logreg on the stored
MiniLM embeddings, and SetFit — are each fitted on an identical train split,
evaluated once on an identical deterministic held-out set, and recorded. Per
category the head with the highest held-out precision **that also clears
`min_precision` and the base-rate guard** is `selected`; the others are
`quarantined` or `lost-bakeoff` (cleared both, lower precision).
`claims-predict` then runs only the `selected` heads over every embedded
chunk and writes `document_claim_predictions`.

**Two guards, added after the first beta-box run** (2026-09-01) showed a head
can pass a 10-example held-out set and still fire on half the corpus:

- **Corpus negatives.** The reviewer-labelled negatives are all *rejected
  review-queue candidates* — sentences a rule already thought might be a
  claim. A head trained on those alone learns "queue-approved vs
  queue-rejected", and out of distribution on the 99%+ of chunks never queued
  it defaults to positive. So the training negative class is topped up with
  `CORPUS_NEG_PER_POS` (3) random unlabelled chunks per training positive,
  labelled 0. A sampled chunk could rarely be a real unflagged claim; at a
  base rate well under 1% that is acceptable negative-class noise, and
  `n_corpus_neg` is recorded on the head row. Held-out stays pure reviewer
  labels.
- **Base-rate quarantine.** After the fit, the head scores a random corpus
  sample (`BASE_RATE_SAMPLE`, 2000 chunks, a disjoint draw from the corpus
  negatives). If its predicted-positive rate exceeds `MAX_POSITIVE_RATE`
  (0.15, `--max-positive-rate`) it is `quarantined` regardless of held-out
  precision. `positive_rate` and `max_positive_rate` are on the head row.

## What it is NOT — the fences

Identical treatment to 034C topics and the deferred 034H BERTopic run:

- **A prediction is a finding aid, never a claim.** Its own table, its own
  registry.
- **No `graph_claims` write.** That writer is still its own held decision
  (`pipeline/nlp/decisions.py` docstring).
- **No promotion to evidence** (settled decision 4). No `promoted_by`, no
  person, no trigger path into `entity_relationships`.
- **Not exported.** Every export target in `pipeline/exports/` is opt-in — it
  names the tables it emits — so the fence is that neither table is ever
  added to one. `tests/test_nlp_claims_predict.py` pins their absence from
  every `pipeline/exports/*.py` and from `public_queries.py` /
  `public_export.py` / `server.py`.
- **Not portal-reachable.** No `/api/v1/*` route (settled decision 7) and —
  in this tranche — **no `/api/admin/*` route either**. Predictions are
  reached by CLI and direct SQL only, like the gate report. A portal or admin
  view is a later, separate decision.
- **Does not reorder the review queue.** That is 034H active learning, also
  deferred.
- **Never in CI, never on the collection path.** The SetFit fine-tune sits
  behind the `slow` marker; the logreg path is pure-Python and fast enough
  for the default suite. Nothing here fetches.

## Schema — migration `0082_document_claim_predictions.sql`

Next free number is `0082`. Two tables; `nlp_runs` is reused (new `stage`
values `claims-train` and `claims-predict`, no schema change — `stage` is free
text and `config_sha256` + `input_scope_json` already carry the run config).

### `claim_head_versions` — one row per trained head

| column | notes |
|---|---|
| `model_version` TEXT PK | `<model_type>-<category>-<corpus_cutoff>-<hash8>` |
| `category` TEXT NOT NULL | `gate.GATE_CATEGORIES` key |
| `predicate` TEXT NOT NULL | its `relations.yml` predicate, denormalised for query |
| `model_type` TEXT NOT NULL | `'logreg'` \| `'setfit'` |
| `embedder_model_key` TEXT → `nlp_model_registry` | logreg: the 034A embedder key; setfit: `NULL` (carries its own body) |
| `setfit_base_model` TEXT | setfit: HF id + resolved revision; logreg: `NULL` |
| `config_sha256` TEXT NOT NULL | hyperparams + embedder id + held-out seed + corpus cutoff |
| `corpus` TEXT NOT NULL | `'beta-box'` \| `'source'` |
| `corpus_cutoff` TEXT NOT NULL | `max(decided_at)` over the training + held-out decisions — the corpus snapshot |
| `corpus_status` TEXT NOT NULL | `'experimental'` \| `'authoritative'` |
| `heldout_candidate_ids_json` TEXT NOT NULL | JSON array of `claim_candidate_id` — the exact deterministic carve |
| `n_train_pos` / `n_train_neg` / `n_heldout_pos` / `n_heldout_neg` INTEGER NOT NULL | |
| `heldout_precision` / `heldout_recall` / `heldout_f1` REAL NOT NULL | on the held-out set |
| `min_precision` REAL NOT NULL | the bar this run applied |
| `status` TEXT NOT NULL | `'passed'` \| `'quarantined'` \| `'lost-bakeoff'` |
| `selected` INTEGER NOT NULL DEFAULT 0 | `1` = this head writes predictions for its category |
| `artifact_path` TEXT | `nlp-cache/claims/...`; `NULL` only for an inline logreg blob |
| `artifact_sha256` TEXT | verified on load by `claims_predict`; a mismatch refuses the run |
| `code_commit` TEXT | git revision at train time, or `NULL` |
| `nlp_run_id` TEXT NOT NULL → `nlp_runs` | the train run |
| `trained_at` TEXT NOT NULL | |

```sql
-- At most one live head per category. A re-run clears the prior selection
-- and sets this one; the partial unique index makes a double-selection a
-- write error, not a silent ambiguity for claims_predict.
CREATE UNIQUE INDEX idx_claim_head_selected_one_per_category
    ON claim_head_versions (category) WHERE selected = 1;
CREATE INDEX idx_claim_head_category
    ON claim_head_versions (category, trained_at);
```

### `document_claim_predictions` — one row per (chunk, category) from a selected head

| column | notes |
|---|---|
| `document_chunk_id` TEXT NOT NULL → `document_chunks` | |
| `category` TEXT NOT NULL | |
| `model_version` TEXT NOT NULL → `claim_head_versions` | the head that produced it |
| `label` INTEGER NOT NULL | `0` \| `1` (`1` = head predicts the category's claim is affirmed in this chunk) |
| `score` REAL NOT NULL | head confidence for `label = 1`, `[0, 1]` |
| `split` TEXT NOT NULL DEFAULT `'unlabelled'` | `'train'` \| `'heldout'` \| `'unlabelled'` — was this chunk in the fit? |
| `nlp_run_id` TEXT NOT NULL → `nlp_runs` | the predict run (distinct from the train run) |
| `created_at` TEXT NOT NULL | |
| PRIMARY KEY `(document_chunk_id, category, model_version)` | |

```sql
CREATE INDEX idx_claim_predictions_lookup
    ON document_claim_predictions (category, model_version, label);
```

The migration header carries the fence rules and the travelling caveat as a
comment, in the style of `0065` / `0079`.

## Modules — `pipeline/nlp/`

### `claims.py` — constants and shared vocabulary

`MIN_HEAD_PRECISION = 0.80`, with a `gate.py`-style comment: precision
favoured over recall on a thin single-reviewer corpus; changing it is a
tracked commit like the `MIN_PER_CLASS` changes, not a default to slip.
`ARTIFACT_ROOT = Path("nlp-cache/claims")`. `HELDOUT_SEED` (a fixed string
mixed into the carve hash).

### `claims_features.py` — labels, embeddings, the held-out carve

- Reuses `gate._label_for` and `gate.GATE_CATEGORIES` directly — the
  positive/negative definition is not re-implemented. Positives: `approved` +
  `AFFIRMED` for the predicate, or `corrected` to it. Negatives: `rejected`,
  `corrected` away, or `approved` but `NEGATED` / `HISTORICAL` /
  `THIRD_PARTY`.
- For each labelled candidate, resolves its `document_chunk_id` (via
  `document_claim_candidates.document_chunk_id`) and, for logreg, its stored
  vector from `document_embeddings` under the registry embedder `model_key`.
  A labelled candidate whose chunk has no embedding row is dropped from the
  logreg set with a logged count (it stays in the SetFit set, which
  re-encodes text) — the spec keeps both models scoring the *same* labelled
  population, so such a candidate is dropped from both and the count is
  recorded on the run.
- **The held-out carve** (deterministic, order-independent, reproducible):
  rank each category's positives by `sha256(HELDOUT_SEED + category + claim_candidate_id)`
  and take the last `HELDOUT_PER_CLASS` (10) as held-out; likewise negatives.
  The chosen ids are written to `heldout_candidate_ids_json` on every head row
  for that category, so "why is this chunk marked `heldout`" is a query. The
  carve does **not** depend on `decided_at` (so re-labelling order cannot move
  it) and is identical for the logreg and SetFit heads of a category.
- `corpus_cutoff` = `max(decided_at)` over the union of train + held-out
  decisions for the category, formatted `YYYYMMDD` for the `model_version`
  string (full ISO stored on the row).

### `claims_train.py` — the bake-off

1. Run `gate.check(conn)`. If `not report["ready"]`, print the `blocking`
   list and exit non-zero (same contract as `gate-034g`), unless
   `--category` is given explicitly (experimentation path — still records
   `corpus_status='experimental'`).
2. `nlp_runs` row, `stage='claims-train'`, config = `{min_precision,
   models, categories, corpus, corpus_status, heldout_seed, hyperparams}`.
3. For each `ready` category, for each model in `--model` (`both` default):
   - carve held-out (`claims_features`), fit on the remainder,
   - **logreg**: pure-Python + numpy full-batch gradient descent, L2, class
     weights `n/(2·class_count)` so a skewed corpus does not train a
     majority-class predictor. Artifact = JSON
     `{model_type, category, predicate, embedder_model_key, dim, coef, intercept}`
     at `nlp-cache/claims/<category>/<model_version>.json`.
   - **setfit**: `SetFitModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")`
     — the *same* body as the 034A embedder, so the comparison is
     body-constant — `Trainer` with `TrainingArguments`, contrastive pairs
     auto-generated from the train split. Artifact = the saved model dir at
     `nlp-cache/claims/setfit/<category>/<model_version>/`; `artifact_sha256`
     is a hash over its sorted `(relpath, bytes)`.
   - evaluate on held-out → precision / recall / F1; write a
     `claim_head_versions` row (`status` provisionally `passed` if
     `precision >= min_precision` else `quarantined`), `artifact_sha256`
     recorded.
4. Per category: among `passed` heads pick `max(heldout_precision)`, tie →
   `logreg`. Set that row `selected = 1`; demote any other `passed` head for
   the category to `lost-bakeoff`. Clear `selected` on any prior head for the
   category (the partial unique index enforces one).
5. Commit per category (SQLite discipline — a unit of work is a category's
   bake-off, not the whole run).
6. `--dry-run`: fit and evaluate, print the summary table, roll back, write no
   artifacts (or write them under a tmp dir and delete).

### `claims_predict.py` — scoring

- Load every `selected = 1` head. Verify `artifact_sha256`; a mismatch
  refuses the run (`log.error("nlp.claims_predict.artifact_mismatch")`,
  non-zero exit).
- Zero selected heads → `log.warning("nlp.claims_predict.no_heads")`, exit 0,
  write nothing.
- Predict population: live `document_chunks` with a `document_embeddings` row
  under the registry embedder `model_key`. logreg uses the stored vector;
  setfit re-encodes `document_chunks.text`.
- `nlp_runs` row `stage='claims-predict'`. For each head, write one
  `document_claim_predictions` row per chunk: `label`, `score`, and `split`
  set from the head's train / held-out candidate→chunk map (`'train'` /
  `'heldout'` / `'unlabelled'`). `nlp_run_id` = the predict run.
- Idempotent per `(chunk, category, model_version)` — a re-predict under the
  same head is an upsert. A new head (new `model_version`) leaves the old
  rows; they are distinguishable by `model_version` and prunable by a later
  `--vacuum-superseded` if wanted (out of scope here).
- Commit per head.

### `claims_eval.py` — the registry as a report

Read-only. Dumps the summary: category × model_type ×
precision/recall/F1/status/selected, plus corpus / cutoff / n_train /
n_heldout and the `model_version`. Backs `nlp claims-eval`. No writes.

## CLI — `pipeline/cli.py`, `nlp_app`

```bash
uv run pipeline nlp claims-train \
    [--model both|logreg|setfit] [--category vacancy_pressure ...] \
    [--min-precision 0.80] [--corpus-label beta-box] \
    [--corpus-status experimental] [--dry-run]

uv run pipeline nlp claims-eval            # registry summary as JSON

uv run pipeline nlp claims-predict [--dry-run]
```

`claims-train` with no `--category` runs the gate first and refuses (exit 1,
blocking list) until it is green, mirroring `gate-034g`.

## Provenance and versioning

Every `document_claim_predictions` row answers "why does this exist, under
what model, on which corpus snapshot, with what held-out set and precision" in
two joins:

```
document_claim_predictions
  → claim_head_versions  (model_version): config_sha256, corpus, corpus_cutoff,
    corpus_status, heldout_candidate_ids_json, precision/recall/f1, min_precision,
    status, code_commit, trained_at, nlp_run_id (train run)
  → nlp_runs             (document_claim_predictions.nlp_run_id): the predict run,
    its config_sha256, code_commit, started/completed
```

## Model artifacts

Under `nlp-cache/claims/` (bind-mounted, survives a warehouse sync).
`artifact_path` + `artifact_sha256` on the head row; `claims_predict` verifies
the hash on load and refuses a mismatch — a synced warehouse whose artifacts
did not come with it fails loudly rather than scoring against the wrong head.
`setfit>=1.1` and `scikit-learn>=1.4` are added to the `nlp` extra in
`pyproject.toml` (scikit-learn is a SetFit dependency; the project's own
logreg head needs only numpy, which rides in transitively via shapely and is
always present). `setfit` is imported lazily inside the fit/predict
functions, never at module load, so `import pipeline.nlp.claims_train`
without the extra still works.

## Fencing and isolation — tests

- `tests/test_nlp_claims_predict.py` — parametrised over both table names:
  asserts neither appears in any `pipeline/exports/*.py`, nor in
  `pipeline/web/public_queries.py` / `public_export.py` / `server.py`. Exports
  are opt-in, so absence from the source is the fence.
- No new `/api/v1/*` or `/api/admin/*` route, so `tests/test_portal_isolation.py`'s
  frozen route lists are unchanged — the boundary is held by adding nothing.

## Functional tests — `tests/test_nlp_claims_*.py`

Offline, fixture-backed, `tmp_path` for any writable path (the `settings`
fixture rule).

- `test_nlp_claims_features.py` — the held-out carve is deterministic across
  runs, never overlaps train, is exactly 10/class, and is independent of
  `decided_at`; `_label_for` reuse matches `gate.py` on a shared fixture.
- `test_nlp_claims_train.py` — a 50-example fixture per category trains real
  **logreg** heads in the default suite; covers the quarantine case
  (`precision < bar` → `status='quarantined'`, `selected=0`), bake-off winner
  selection via a direct `_persist_category` call with fabricated results
  (logreg wins a tie; both quarantined → no winner), the `model_version`
  composite format, the one-selected-per-category partial unique index
  (a second `selected=1` insert raises), a retrain keeping exactly one live
  head, dry-run writing nothing, and the gate refusal when `not ready`.
- `test_nlp_claims_setfit.py` — one `slow` test (`pytest.importorskip("setfit")`),
  deselected by default, that runs a real fine-tune through the bake-off.
- `test_nlp_claims_predict.py` — only `selected=1` heads write; `split` is set
  from the candidate→chunk map; zero heads → logged no-op; `artifact_sha256`
  mismatch raises `ArtifactMismatch` and writes nothing; dry-run scores but
  writes nothing.
- `tests/nlp_claims_support.py` — the shared SQL seeder (evidence → version →
  chunks → stub embeddings → candidates → decisions), separable or not by
  label.
- `tests/test_migration_equivalence.py` — its migration-count assertion and
  running commentary are updated to `82`.

## The caveat that travels

A short entry in `docs/CAVEATS.md`: any figure a `document_claim_predictions`
row ever supports carries **all** of —

1. single-reviewer corpus (`MIN_DOUBLE_REVIEWED = 0`, owner decision);
2. `MIN_PER_CLASS = 25` floor — thin, few-shot's own premise;
3. model-triage-assisted labels (`nlp suggest-decisions` ensemble);
4. **until the source retrain**: trained on the non-authoritative beta-box
   copy — `corpus_status = 'experimental'`.

## Corpus provenance — the beta-box decision

The review corpus is on the beta box, which is a copy of the source and is
not authoritative. The decision taken: **train now, on the beta-box corpus,
with `corpus_status = 'experimental'` stamped on every head and every
prediction traceable to it.** This proves the pipeline end to end and gives a
real head to inspect. A retrain is then a **required milestone before any
head's predictions support a public-facing figure**: redo `nlp relations` →
`queue-claims` → review on the source warehouse, re-run `claims-train` there,
and the new heads carry `corpus = 'source'`, `corpus_status = 'authoritative'`.
The experimental heads are not deleted — they are a dated record of the first
build.

## Landed with the code

- `pyproject.toml` — `setfit>=1.1`, `scikit-learn>=1.4` in the `nlp` extra; a
  new `slow` pytest marker, added to `addopts` deselection. `uv.lock` relocked.
- `.gitignore` — `nlp-cache/`.
- `docs/semantic-analysis.md` — the 034G tranche row rewritten (bake-off,
  fenced predictions table, gate green, beta-box experimental).
- `docs/upgrade-roadmap.md` — **D-09** register entry; D-08 closing lines
  (review pass complete on beta box, gate green at 62/49 · 58/70 · 48/64).
- `docs/CAVEATS.md` — the "Claim predictions (034G, experimental)" section.
- `docs/DATA_DICTIONARY.md` — regenerated by `./start.sh export docs` (it is
  generated from the live schema; not hand-edited here).

## Open

1. **Source retrain.** Redo `nlp relations` → `queue-claims` → review on the
   authoritative source warehouse, then `claims-train` there. The heads then
   carry `corpus = 'source'`, `corpus_status = 'authoritative'`. Required
   before any head's predictions support a public-facing figure.
2. **A go-ahead for downstream use** — like the `graph_claims` writer — for
   anything that consumes `document_claim_predictions` beyond a
   CLI-inspected finding aid.

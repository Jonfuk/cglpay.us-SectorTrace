"""Constants and shared vocabulary for the 034G claim-prediction heads.

The gate (`pipeline/nlp/gate.py`) decides *whether* a head is worth training;
this module and its siblings (`claims_features`, `claims_train`,
`claims_predict`, `claims_eval`) are what the green gate unlocks. The full
build spec is `docs/claim-predictions-spec.md`.

Nothing here imports numpy, scikit-learn or setfit -- those are `nlp`-extra
only and are imported lazily inside `claims_train` / `claims_predict`, so a
plain `import pipeline.nlp.claims` (which the CLI does at module load) never
needs the extra. The *own* logistic-regression head is pure Python + numpy
(numpy rides in transitively via shapely, so it is always present); scikit
-learn is pulled only for SetFit's classifier head.
"""
from __future__ import annotations

from pathlib import Path

# Precision favoured over recall on a thin single-reviewer corpus: a head that
# fires often but wrongly puts a reviewer's name near a claim that is not one.
# A head whose held-out precision is below this bar is trained and its metrics
# recorded, but QUARANTINED -- `selected` stays 0 and it never writes a
# prediction. Overridable per run with `--min-precision` (the value applied is
# stored on every head row and on the nlp_run). Changing the DEFAULT is a
# tracked commit, argued for -- the same discipline as the `MIN_PER_CLASS`
# changes in gate.py, not a knob to turn quietly.
MIN_HEAD_PRECISION = 0.80

# The deterministic held-out carve reserves this many positives AND this many
# negatives per category, chosen by a stable hash rather than by decision
# order, and never seen by the fit. Matches `gate.HELDOUT_PER_CLASS` -- the
# gate checks the room exists, this is the code that takes it.
HELDOUT_PER_CLASS = 10

# The reviewer-labelled negatives are all REJECTED review-queue candidates --
# sentences a rule already thought might be a claim. A head trained on those
# alone learns "queue-approved vs queue-rejected", not "affirmed claim vs the
# rest of the corpus", and out of distribution on the 99%+ of chunks that
# were never queued it defaults to positive. Measured on the beta box
# (2026-09-01): the agency head then flagged 52% of 168k chunks. So the
# training negative class is topped up with random unlabelled chunks -- this
# many per reviewed positive. A sampled chunk could in rare cases be a real
# unflagged claim; at a base rate well under 1% that is acceptable noise in
# the negative class, and it is recorded (`n_corpus_neg` on the head row).
CORPUS_NEG_PER_POS = 3

# A gate-category claim is a rare event. After the fit, the head scores a
# random sample of the corpus; if it predicts positive on more than this
# fraction it is QUARANTINED regardless of held-out precision -- a head that
# passed a 10-example held-out set can still be noise, and this is the check
# that catches it. Overridable per run with `--max-positive-rate`.
MAX_POSITIVE_RATE = 0.15
BASE_RATE_SAMPLE = 2000

# Mixed into the held-out selection hash. A fixed string, not a tunable: it
# only has to be stable so the same corpus carves the same held-out set on
# every machine and every re-run. It is recorded in the head's config hash so
# a change to it produces a visibly different `model_version`.
HELDOUT_SEED = "034g-heldout-v1"

# Fine-tuned SetFit models and serialised logreg heads live here, one dir per
# (category, model_version). Bind-mounted on the VPS so a warehouse sync does
# not orphan them; `claims_predict` verifies each artifact's SHA-256 against
# the head row before it scores, and refuses a mismatch.
ARTIFACT_ROOT = Path("nlp-cache") / "claims"

# The sentence-transformers body SetFit fine-tunes, and -- via its `embed:`
# model_key -- the source of the vectors the logreg head reads. The same body
# on both sides keeps the bake-off a comparison of the *head*, not of two
# different encoders.
DEFAULT_EMBEDDER_MODEL_KEY = "embed:all-minilm-l6-v2"
SETFIT_BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

MODEL_TYPES = ("logreg", "setfit")
HEAD_STATUSES = ("passed", "quarantined", "lost-bakeoff")
PREDICTION_SPLITS = ("train", "heldout", "unlabelled")

TRAIN_STAGE = "claims-train"
PREDICT_STAGE = "claims-predict"

"""Stable IDs and purpose notes for the validation-rule explorer (BETA-104).

The warehouse's validation rules are not one hand-kept list — they live in
three enumerable places:

  * the database schema: CHECK constraints, the provenance NOT NULL columns
    (constraint 1), and the promotion-gate triggers (constraint 4);
  * `parse_failures`: constraint 6 in action — one observed rule per
    (module, field) that has ever refused to guess a value;
  * `review_queue`: constraint 4 in action — one gate per (module, item type)
    where a person's judgement stands between a candidate and evidence.

`pipeline/web/validation.py` derives the rule set from those at request time
and gives each a stable id of the form `<kind>:<scope>`. This module adds
only the thin layer a derivation cannot: a one-line purpose for a specific
rule where the generic per-kind sentence is not enough, and the redaction
contract for the failure examples.

No rule is invented here. If an id below no longer matches anything the
derivation produces, `tests/test_web_validation.py` fails — the note is
stale and the rule it described is gone.
"""
from __future__ import annotations

# The generic purpose for each rule kind, used when RULE_NOTES has nothing
# more specific. Every rule the explorer shows carries one of these at least.
PURPOSE_BY_KIND: dict[str, str] = {
    "trigger": "A database trigger that refuses the write unless a "
               "precondition is already recorded — enforced by the engine, "
               "not by convention.",
    "check": "A CHECK constraint: the column may only hold one of a fixed "
             "set of values, rejected at write time.",
    "provenance": "Constraint 1 — every evidence row carries its source URL, "
                  "fetch time and the SHA-256 of the exact bytes, or it is "
                  "not written. These columns are NOT NULL.",
    "parse_failure": "Constraint 6 — a value that could not be parsed is "
                     "written NULL and logged here with the raw fragment, "
                     "never guessed or defaulted.",
    "review_gate": "Constraint 4 — an item needing human judgement waits "
                   "here; database triggers stop it auto-promoting to "
                   "evidence.",
}

# Specific purpose for a specific derived rule id, where the generic sentence
# above misses the point of that particular rule. Keys are the ids
# `pipeline/web/validation.py` produces.
RULE_NOTES: dict[str, str] = {
    "trigger:cdp_documents_need_a_promotion":
        "A discovered Combating Drugs Partnership document cannot enter "
        "cdp_documents without an evidence_promotions row written by a person "
        "through pipeline/promote.py (migrations/0030).",
    "trigger:committee_papers_need_a_promotion":
        "A committee paper candidate cannot enter committee_papers without a "
        "human promotion recorded first (migrations/0030).",
    "trigger:foi_requests_need_a_promotion":
        "A discovered FOI response cannot enter foi_requests without a human "
        "promotion recorded first (migrations/0030).",
    "trigger:ai_promotion_requires_provenance":
        "An AI-assisted promotion row is refused unless it carries the model, "
        "prompt hash and human approver — the machine never promotes alone.",
    "trigger:census_metric_verify_needs_a_decision":
        "A workforce-census metric cannot be marked verified without a "
        "recorded review decision behind it.",
    "trigger:census_metric_insert_needs_a_decision":
        "A workforce-census metric row needs its review decision recorded "
        "before it is written.",
    "trigger:claims_insert_needs_a_decision":
        "A campaign claim cannot be inserted without a review decision "
        "linking it to its evidence.",
    "trigger:claims_status_needs_a_decision":
        "A campaign claim's status cannot change without a recorded review "
        "decision.",
}

# The failure examples the explorer shows never carry the raw fragment
# verbatim: `raw_fragment` is free text that failed to parse and can contain
# personal data (an officer name, a claimant name in a page title). Each
# example is reduced to its *shape* — letters to `x`, digits to `9`,
# punctuation and spacing kept — plus the field, the reason, the source host
# (no path or query) and the date. Enough to recognise a recurring pattern,
# nothing readable. This constant is the contract the tests pin.
EXAMPLE_REDACTION = (
    "letters->x, digits->9, punctuation kept; raw fragment never sent, "
    "source URL reduced to host"
)

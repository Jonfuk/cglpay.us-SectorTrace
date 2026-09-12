"""The claim-head registry as a report. Read-only; trains nothing, writes
nothing. Backs `nlp claims-eval` and is the answer to "which heads exist,
which one is live per category, and on what corpus were they trained".
"""
from __future__ import annotations

_SUMMARY_SQL = """
SELECT category, model_type, model_version, status, selected,
       heldout_precision, heldout_recall, heldout_f1, min_precision,
       n_train_pos, n_train_neg, n_heldout_pos, n_heldout_neg,
       corpus, corpus_cutoff, corpus_status, embedder_model_key,
       setfit_base_model, artifact_path, nlp_run_id, trained_at
FROM claim_head_versions
ORDER BY category, trained_at DESC, model_type
"""


def summary(conn) -> dict:
    rows = [dict(r) for r in conn.execute(_SUMMARY_SQL).fetchall()]
    by_category: dict[str, list[dict]] = {}
    for r in rows:
        by_category.setdefault(r["category"], []).append(r)
    selected = {r["category"]: r["model_version"] for r in rows if r["selected"]}
    return {
        "heads": len(rows),
        "categories": sorted(by_category),
        "selected": selected,
        "by_category": by_category,
    }

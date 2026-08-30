"""Model triage for a review sheet -- an optional pre-annotation step.

`docs/CAVEATS.md`, "Model-assisted review triage", is the decision this
implements. The bounds it names are enforced here:

  * one row is triaged into ``reject`` / ``approve`` / ``correct`` / ``keep``.
    ``correct`` also names a replacement predicate, which is checked against
    ``relations.yml`` and dropped to ``keep`` if it is not a real id -- the
    model proposes, it does not get to invent an ontology term;
  * ``reject`` -> ``suggested_decision='rejected'``; ``approve`` ->
    ``'approved'``; ``correct`` -> ``'corrected'`` plus
    ``suggested_corrected_predicate``; ``keep`` writes nothing, so the row
    reaches the reviewer untouched;
  * with two or more ``--model``s the verdicts must AGREE (same verdict, and
    for ``correct`` the same predicate) before anything is written;
    a split writes no suggestion, only ``suggested_by='ensemble:split'`` and a
    note of who said what, so the reviewer sees it is contested and a re-run
    does not pay to ask again;
  * ``decide-claims-batch --accept-suggested`` still lifts only ``rejected``
    in bulk. ``approved`` and ``corrected`` suggestions are reading aids the
    reviewer confirms row by row -- a wrong bulk reject costs recall, a wrong
    bulk approve poisons the precision the gate favours;
  * a row the deterministic screen flagged, one that already carries a human
    ``decision``, or one already carrying any ``suggested_by`` is left alone;
  * one row per call per model. The sentence, the triple and the predicate
    vocabulary go out, nothing else. The key is read from
    ``OPENROUTER_API_KEY`` and never logged;
  * anything unexpected from the API -- an error, an unparseable reply --
    is ``keep``, so a network problem never auto-decides a row;
  * every run is an ``nlp_runs`` row (stage ``review_suggest``) with the model
    ids and a hash of the prompt template.

Not on the offline path, not in CI, gated on the key. `_ask` is a parameter so
tests never make a call.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from pipeline.nlp import ontology as ontology_mod
from pipeline.nlp import runs

STAGE = "review_suggest"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 30
DEFAULT_RATE = 2.0   # requests/second per model

_VERDICTS = ("reject", "approve", "correct", "keep")
_DECISION_FOR = {"reject": "rejected", "approve": "approved", "correct": "corrected"}

_INSTRUCTIONS = (
    "You are triaging machine-extracted (subject, predicate, object) claims "
    "pulled from UK local-government committee papers, to build a training "
    "set. Choose one verdict:\n"
    "- reject: unusable -- the sentence is garbled or truncated, it does not "
    "assert any of the listed predicates, or there is no real claim.\n"
    "- approve: the sentence clearly and directly asserts THE GIVEN predicate "
    "about THE GIVEN subject, as a present factual claim -- not hypothetical, "
    "not negated, not historical, not someone else's view.\n"
    "- correct: there is a real present claim but the GIVEN predicate is "
    "wrong; give the id of the predicate from the list that fits.\n"
    "- keep: anything else. When unsure, keep.\n"
    'Reply with JSON only: {"verdict": "reject|approve|correct|keep", '
    '"predicate": "<id, only when verdict is correct>", "reason": "<=12 words"}.'
)


def _relation_lines() -> str:
    relations = ontology_mod.default().relations
    return "\n".join(f"- {rid}: {rel.label}"
                     for rid, rel in sorted(relations.items()))


def system_prompt() -> str:
    return f"{_INSTRUCTIONS}\n\nValid predicates:\n{_relation_lines()}"


def prompt_hash() -> str:
    return hashlib.sha256(system_prompt().encode("utf-8")).hexdigest()[:16]


def _valid_predicates() -> frozenset[str]:
    return frozenset(ontology_mod.default().relations)


def _render(row: dict) -> str:
    return (
        f"predicate: {row.get('predicate')} ({row.get('predicate_label')})\n"
        f"assertion: {row.get('assertion_status')}\n"
        f"subject: {row.get('subject_hint') or '(unresolved)'}\n"
        f"object: {row.get('object') or '(none)'}\n"
        f"sentence: {row.get('evidence_span')}"
    )


def _parse(content: str) -> tuple[str, str, str]:
    """(verdict, reason, predicate). predicate is '' unless verdict=='correct'
    and the model named one; validity is checked by the caller."""
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            verdict = str(obj.get("verdict", "")).strip().lower()
            if verdict in _VERDICTS:
                reason = str(obj.get("reason", "")).strip()[:120]
                predicate = str(obj.get("predicate", "")).strip()
                return verdict, reason, (predicate if verdict == "correct" else "")
        except ValueError:
            pass
    lower = text.lower()
    for verdict in ("reject", "approve", "correct"):
        if verdict in lower:
            return verdict, "unstructured reply", ""
    return "keep", "unstructured reply", ""


def _ask(row: dict, *, model: str, api_key: str,
         base_url: str = DEFAULT_BASE_URL, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str, str]:
    """One triage call to one model. Returns (verdict, reason, predicate). Any
    failure -> ('keep', <why>, ''), so a network problem never auto-decides."""
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": _render(row)},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions", data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        # OpenRouter puts the useful part (bad key, unknown model, policy not
        # accepted, rate limit) in the response body, not the status line.
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except OSError:
            detail = exc.reason or ""
        return "keep", f"api error: HTTP {exc.code} {detail}".strip(), ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return "keep", f"api error: {type(exc).__name__}: {reason}", ""
    except (KeyError, IndexError, ValueError) as exc:
        return "keep", f"unreadable response: {type(exc).__name__}", ""
    return _parse(content)


def _consensus(votes: list[tuple[str, str, str, str]], valid: frozenset[str]):
    """votes = [(model, verdict, reason, predicate)]. Returns
    (verdict, reason, predicate, by) if every model agrees -- same verdict, and
    for `correct` the same *valid* predicate -- else (None, split_note, '', by).
    """
    verdicts = {v for _, v, _, _ in votes}
    models = "+".join(f"model:{m}" for m, *_ in votes)
    if len(verdicts) != 1:
        note = ", ".join(f"{m}={v}" for m, v, _, _ in votes)
        return None, f"split: {note}", "", "ensemble:split"
    verdict = verdicts.pop()
    reason = next((r for _, v, r, _ in votes if r), "")
    if verdict == "correct":
        predicates = {p for _, _, _, p in votes}
        if len(predicates) != 1 or predicates <= {""} or not (predicates <= valid):
            note = ", ".join(f"{m}={p or '?'}" for m, _, _, p in votes)
            return None, f"correct, predicate split: {note}", "", "ensemble:split"
        return verdict, reason, predicates.pop(), models
    return verdict, reason, "", models


def suggest(conn, rows: list[dict], *, models: list[str], api_key: str | None = None,
            base_url: str = DEFAULT_BASE_URL, rate: float = DEFAULT_RATE,
            limit: int | None = None, ask=_ask, source_label: str | None = None) -> dict:
    """Fill the `suggested_*` columns from the models' triage. Mutates `rows` in
    place; returns a summary. With more than one model the verdicts must agree.
    Rows already decided, screened, or carrying any `suggested_by` are skipped
    (so a re-run costs nothing for a row already seen). `ask` is injectable so
    tests never call out."""
    models = [m for m in (models or []) if m]
    if not models:
        raise RuntimeError("at least one --model is required.")
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or ""
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. See docs/CAVEATS.md, "
                           "'Model-assisted review triage'.")

    valid = _valid_predicates()
    cfg = {"models": models, "prompt_hash": prompt_hash(), "rows": len(rows),
           "limit": limit or 0, "source": source_label or ""}
    run_id = runs.start_run(conn, STAGE, config=cfg, model_key="+".join(models))
    conn.commit()

    summary = {"run_id": run_id, "rows": len(rows), "models": models, "asked": 0,
               "rejected": 0, "approved": 0, "corrected": 0, "kept": 0,
               "split": 0, "skipped_suggested": 0, "skipped_decided": 0,
               "errors": 0, "error_sample": [], "dropped_models": []}
    interval = 1.0 / rate if rate and rate > 0 else 0.0
    live = list(models)                 # models still worth calling
    fails: dict[str, int] = {}          # consecutive failures, until a success
    for row in rows:
        if summary["asked"] == (limit or -1) or not live:
            break
        if str(row.get("decision") or "").strip():
            summary["skipped_decided"] += 1
            continue
        if (str(row.get("suggested_decision") or "").strip()
                or str(row.get("suggested_by") or "").strip()
                or row.get("screen_reason")):
            summary["skipped_suggested"] += 1
            continue

        votes = []
        for model in list(live):
            verdict, reason, predicate = ask(row, model=model, api_key=api_key,
                                             base_url=base_url)
            errored = reason.startswith(("api error", "unreadable response"))
            if errored:
                summary["errors"] += 1
                if reason not in summary["error_sample"] and len(summary["error_sample"]) < 5:
                    summary["error_sample"].append(reason)
                fails[model] = fails.get(model, 0) + 1
                # A dead slug (404), a bad key (401) or a hard rate limit is
                # not per-row: stop hammering it after 3 straight failures.
                if fails[model] >= 3:
                    live.remove(model)
                    summary["dropped_models"].append(f"{model} ({reason[:80]})")
            else:
                fails[model] = 0
            votes.append((model, verdict, reason, predicate))
            if interval:
                time.sleep(interval)
        summary["asked"] += 1

        verdict, reason, predicate, by = _consensus(votes, valid)
        if verdict is None:
            row["suggested_by"] = by            # 'ensemble:split'
            row["suggested_reason"] = reason
            summary["split"] += 1
            continue
        decision = _DECISION_FOR.get(verdict)
        if not decision:
            summary["kept"] += 1
            continue
        row["suggested_decision"] = decision
        row["suggested_reason"] = reason or "model triage"
        row["suggested_by"] = by
        if verdict == "correct":
            row["suggested_corrected_predicate"] = predicate
        summary[decision] += 1   # 'rejected' | 'approved' | 'corrected'

    runs.finish_run(conn, run_id, status="ok", rows_processed=summary["asked"],
                    rows_written=summary["rejected"] + summary["approved"]
                    + summary["corrected"])
    conn.commit()
    return summary

"""Model triage for a review sheet -- an optional pre-annotation step.

`docs/CAVEATS.md`, "Model-assisted review triage", is the decision this
implements. The bounds it names are enforced here:

  * the model triages one row into ``reject`` / ``approve`` / ``keep``:
    ``reject`` -- the extraction is unusable (garbled or truncated sentence,
    not actually asserting the predicate, no real claim); ``approve`` -- the
    sentence clearly and directly asserts *this* predicate about *this*
    subject, now, as fact; ``keep`` -- anything else, including "the predicate
    is wrong but there is a claim here", which is the reviewer's to correct.
    The model never drafts a ``corrected`` predicate -- picking the right
    ontology id is the label the 034G classifier is being trained to produce,
    and a model guess feeding that back in is circular;
  * a ``reject`` writes ``suggested_decision='rejected'``, an ``approve``
    writes ``suggested_decision='approved'``, both with
    ``suggested_by='model:<id>'``; a ``keep`` writes nothing, so the row
    reaches the reviewer untouched;
  * ``decide-claims-batch --accept-suggested`` still lifts only ``rejected``
    in bulk. An ``approved`` suggestion is a reading aid the reviewer confirms
    row by row -- a wrong bulk reject costs recall, a wrong bulk approve
    poisons the precision the gate favours;
  * a row the deterministic screen already flagged, or one that already
    carries a human ``decision``, is left alone;
  * one row per call. The sentence and the triple go out, nothing else. The
    key is read from ``OPENROUTER_API_KEY`` and never logged;
  * anything unexpected from the API -- an error, an unparseable reply --
    fails safe to ``keep``, so a network problem never auto-rejects a row;
  * the run is recorded in ``nlp_runs`` (stage ``review_suggest``) with the
    model id and a hash of the prompt template.

Not on the offline path, not exercised in CI, gated on the key being set and
on being asked for by name. `_ask` is a parameter so tests never make a call.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from pipeline.nlp import runs

STAGE = "review_suggest"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT = 30
DEFAULT_RATE = 2.0   # requests/second

_SYSTEM_PROMPT = (
    "You are triaging machine-extracted (subject, predicate, object) claims "
    "pulled from UK local-government committee papers, to build a training "
    "set. Choose one verdict:\n"
    "- reject: the extraction is unusable -- the sentence is garbled or "
    "truncated, it does not assert the predicate at all, or there is no real "
    "claim in the text.\n"
    "- approve: the sentence clearly and directly asserts THIS predicate about "
    "THIS subject, as a present factual claim -- not hypothetical, not "
    "negated, not historical, not someone else's view.\n"
    "- keep: anything in between, including 'there is a claim here but the "
    "predicate looks wrong'. When unsure, keep.\n"
    "Do not propose a replacement predicate. Reply with JSON only: "
    '{"verdict": "reject" | "approve" | "keep", "reason": "<= 12 words"}.'
)
_VERDICTS = ("reject", "approve", "keep")


def prompt_hash() -> str:
    return hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16]


def _render(row: dict) -> str:
    return (
        f"predicate: {row.get('predicate')} ({row.get('predicate_label')})\n"
        f"assertion: {row.get('assertion_status')}\n"
        f"subject: {row.get('subject_hint') or '(unresolved)'}\n"
        f"object: {row.get('object') or '(none)'}\n"
        f"sentence: {row.get('evidence_span')}"
    )


def _ask(row: dict, *, model: str, api_key: str,
         base_url: str = DEFAULT_BASE_URL, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """One triage call. Returns (verdict, reason); verdict is one of
    `_VERDICTS`. Any failure -> ('keep', <why>), so a network problem never
    auto-decides a row."""
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
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
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "keep", f"api error: {type(exc).__name__}"
    except (KeyError, IndexError, ValueError) as exc:
        return "keep", f"unreadable response: {type(exc).__name__}"

    verdict, reason = _parse(content)
    return verdict, reason


def _parse(content: str) -> tuple[str, str]:
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            verdict = str(obj.get("verdict", "")).strip().lower()
            if verdict in _VERDICTS:
                return verdict, str(obj.get("reason", "")).strip()[:120]
        except ValueError:
            pass
    # A model that ignored the format but named a verdict still counts. `keep`
    # is the safe default -- it sends the row to the reviewer untouched.
    lower = text.lower()
    for verdict in ("reject", "approve"):
        if verdict in lower:
            return verdict, "unstructured reply"
    return "keep", "unstructured reply"


_DECISION_FOR = {"reject": "rejected", "approve": "approved"}


def suggest(conn, rows: list[dict], *, model: str, api_key: str | None = None,
            base_url: str = DEFAULT_BASE_URL, rate: float = DEFAULT_RATE,
            limit: int | None = None, ask=_ask, source_label: str | None = None) -> dict:
    """Fill `suggested_decision` from the model's triage (reject -> 'rejected',
    approve -> 'approved', keep -> nothing). Mutates `rows` in place; returns a
    summary. Rows already decided by a person, or already carrying a suggestion
    (the screen, or an earlier run of this command -- so a re-run costs nothing
    for a row already seen), are left untouched. `ask` is injectable so tests
    never call out."""
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or ""
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. See docs/CAVEATS.md, "
                           "'Model-assisted review triage'.")

    tag = f"model:{model}"
    cfg = {"model": model, "prompt_hash": prompt_hash(), "rows": len(rows),
           "limit": limit or 0, "source": source_label or ""}
    run_id = runs.start_run(conn, STAGE, config=cfg, model_key=model)
    conn.commit()

    summary = {"run_id": run_id, "rows": len(rows), "asked": 0, "rejected": 0,
               "approved": 0, "kept": 0, "skipped_suggested": 0,
               "skipped_decided": 0, "errors": 0}
    interval = 1.0 / rate if rate and rate > 0 else 0.0
    for row in rows:
        if summary["asked"] == (limit or -1):
            break
        if str(row.get("decision") or "").strip():
            summary["skipped_decided"] += 1
            continue
        if str(row.get("suggested_decision") or "").strip() or row.get("screen_reason"):
            summary["skipped_suggested"] += 1
            continue
        verdict, reason = ask(row, model=model, api_key=api_key, base_url=base_url)
        summary["asked"] += 1
        if reason.startswith(("api error", "unreadable response")):
            summary["errors"] += 1
        decision = _DECISION_FOR.get(verdict)
        if decision:
            row["suggested_decision"] = decision
            row["suggested_reason"] = reason or "model triage"
            row["suggested_by"] = tag
            summary["rejected" if verdict == "reject" else "approved"] += 1
        else:
            summary["kept"] += 1
        if interval:
            time.sleep(interval)

    runs.finish_run(conn, run_id, status="ok", rows_processed=summary["asked"],
                    rows_written=summary["rejected"] + summary["approved"])
    conn.commit()
    return summary

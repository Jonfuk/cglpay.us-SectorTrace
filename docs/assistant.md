# The local analyst assistant (BETA-107–113)

An **optional, experimental, off-by-default** natural-language finding aid for
the local analysis host. It answers one question by routing it to one
read-only tool and summarising that tool's result with a small local model.
It produces no evidence, no claims and no review decisions.

This is the named decision BETA-034 required before any RAG/LLM work — and
only for an operator finding aid. It does **not** authorise model-generated
claims, automated review decisions, writes to `graph_claims`, public answers,
collection-time model calls, or any paid/cloud AI dependency. SetFit and
claim publication remain blocked by `pipeline nlp gate-034g`.

## What it is made of

| Piece | Module | What it does |
|---|---|---|
| Runtime boundary | `pipeline/assistant/runtime.py`, `adapters.py` | The `[assistant]` extra (just `openai`), two OpenAI-chat-compatible local endpoints, `AssistantUnavailable` instead of import/socket errors. Imports with nothing installed. |
| Run ledger | `pipeline/assistant/ledger.py` + migration `0079` | One immutable `assistant_runs` row per turn: question, filters, model identities, prompt-template hashes, routing confidence, validated args, retrieved chunk ids, answer, citation ids, timings, outcome, error class. Append-only. No secrets or model paths. |
| Tool catalogue | `pipeline/assistant/tools.py` | Exactly five typed, side-effect-free tools wrapping existing query code. No argument is a table name, URL, path or SQL. |
| Router | `pipeline/assistant/routing.py` | Needle 2 picks at most one tool. Its name and arguments are re-validated independently; confidence must clear a frozen threshold; anything else is a clarification with no execution. Needle never sees document text. |
| Grounding | `pipeline/assistant/grounding.py` | LFM gets only the validated tool result (retrieved text delimited as untrusted data) and no executable tools. Every `[[id]]` in the answer is checked against the result's own identifiers; an unresolved citation or a missing citation suppresses the answer and returns an abstention. |
| Service | `pipeline/assistant/service.py` | One orchestration function shared by HTTP and CLI. One tool call per turn, short router timeout, 30 s overall ceiling, explicit `ok`/`abstained`/`clarified`/`timeout`/`unavailable`/`failed` outcome. |
| Evaluation & gate | `pipeline/assistant/evaluation.py` + `tests/fixtures/assistant/` | Frozen routing and grounding suites; a machine-readable gate whose `may_enable` field is the only thing that authorises enabling the feature. |

## The five tools

| Tool | Wraps | Result-local identifiers you may cite |
|---|---|---|
| `search_document_passages` | `pipeline.nlp.semantic_search` | `document_chunk_id` |
| `inspect_claim_candidates` | bounded aggregate over `document_claim_candidates` | predicate names |
| `inspect_claim_gate` | `pipeline.nlp.gate` | gate category names |
| `inspect_source_coverage` | `pipeline.web.health.coverage` (reduced to per-column totals) | column labels |
| `inspect_freshness` | `pipeline.web.health.freshness` | table names |

All five are read-only. Bad arguments raise `ToolError`, which the service
turns into a clarification, never a crash and never an execution.

## Enabling it (local host only)

1. `uv sync --extra assistant` — installs `openai` only. The model weights and
   Ollama are **not** pip-installed and **not** in the Railway image.
2. Serve `LiquidAI/LFM2.5-1.2B-Instruct` (Q4_K_M) on a local Ollama at
   `assistant_ollama_url` and a Needle 2 endpoint at `assistant_needle_url`.
   Needle telemetry must be disabled; no cloud fallback is permitted.
3. Run the gate:

   ```bash
   uv run python -m pipeline nlp assistant-eval
   ```

   It prints the routing/grounding scores and the gate. **Do not set
   `assistant_enabled = True` until `gate.may_enable` is `true`.** A
   code-complete feature is not an enabled one.
4. Only then set `assistant_enabled = True` in local settings.

## Deploying the runtime via Ansible

Both `deploy/ansible/` (self-host) and `deploy/ansible-mirror/` can stand
the model runtime up as a managed container, the same way they manage
Postgres:

* `assistant_runtime_enabled: true` renders `docker-compose.assistant.yml`
  (one Ollama service on the stack's Docker network), builds **both** the
  `app` and the documents-worker images with `--build-arg
  INSTALL_ASSISTANT=true` so `openai` is present, brings Ollama up,
  `ollama pull`s `assistant_lfm_ollama_ref` (`lfm2:1.2b`), and `ollama
  cp`s it to **both** strings the adapters send — `LFM_MODEL` and
  `NEEDLE_MODEL`. One Ollama, one endpoint, two model names:
  `ASSISTANT_OLLAMA_URL` and `ASSISTANT_NEEDLE_URL` both become
  `http://ollama:11434/v1`.
* `assistant_app_enabled: true` writes `ASSISTANT_ENABLED=true`. Keep it
  false until step 3's gate passes. On a `beta` mirror, set
  `ASSISTANT_ENABLED=true` in `.env.merge` instead so it survives the
  checkout reset.

**Which container runs it.** The CLI (`nlp assistant`, `nlp
assistant-eval`) routes to the **documents worker** — that image carries
the `nlp` extra the retrieval tool needs and the frozen eval fixtures, so
the release gate runs there on its defaults. The **app** container gets
`openai` too, for the `POST /api/admin/assistant` HTTP path; four of the
five tools work there, but `search_document_passages` degrades (no `nlp`
extra in the app image — the same limit as `/admin` semantic search).

Railway is unaffected: it builds `Dockerfile` with no build args and does
not build `Dockerfile.documents` at all, so `INSTALL_ASSISTANT` stays
`false` and neither image it produces gets `openai`.

**The `needle-2` alias.** `NEEDLE_MODEL` is served by the same LFM weights
under a second Ollama tag rather than a distinct router model — a
deployment choice, made because one Ollama is simpler to run. The run
ledger still records `needle_model = "needle-2"` as its own identity, so
swapping in a real router later is a deployment change, not a code one.
If Ollama normalises `LiquidAI/LFM2.5-1.2B-Instruct` (case, dots, the
slash) so a request for that exact string no longer matches the stored
model, lowercase `assistant_lfm_model_tag` / `assistant_needle_model_tag`
in `group_vars` **and** change the matching constant in
`pipeline/assistant/runtime.py` to agree.

**Provenance gap.** `ollama.com/library/lfm2` is LFM2; this doc and the
code pin `LFM2.5` at `Q4_K_M`. The alias bridges the name and
`assistant_runs.lfm_model` keeps recording the pinned constant — so a run
ledger says `LFM2.5` while the bytes are `lfm2:1.2b`. Point
`assistant_lfm_ollama_ref` at a real LFM2.5 GGUF if that gap matters.

## Using it

CLI:

```bash
uv run python -m pipeline nlp assistant "What do partnership papers say about keyworker recruitment?"
```

HTTP (admin only, same-origin write guard, absent when `assistant_enabled` is
false, never under `/api/v1`):

```bash
curl -s http://127.0.0.1:8000/api/admin/assistant \
  -H 'content-type: application/json' \
  -d '{"question": "How stale is the contracts table?"}'
```

`GET /api/admin/assistant` still returns the BETA-107 runtime status and
contacts nothing.

## Licence

Liquid's LFM Open License permits free commercial use only while annual
revenue is below USD 10 million; crossing that threshold requires a
commercial licence. Recheck the licence before each model upgrade.

## Out of scope (separate named decisions and gates required)

LFM embedding/ColBERT replacing the 384-dimensional pgvector path;
LFM/Needle extraction or classification; multi-turn memory; autonomous
multi-tool loops; any public assistant access.

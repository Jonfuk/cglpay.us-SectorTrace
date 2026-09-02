# The analyst assistant (BETA-107–113; inference on OpenRouter since BETA-114)

An **optional, experimental, off-by-default** natural-language finding aid for
the operator. It answers one question by routing it to one read-only tool and
summarising that tool's result with a model. It produces no evidence, no
claims and no review decisions.

This is the named decision BETA-034 required before any RAG/LLM work — and
only for an operator finding aid. It does **not** authorise model-generated
claims, automated review decisions, writes to `graph_claims`, public answers,
or collection-time model calls. SetFit and claim publication remain blocked by
`pipeline nlp gate-034g`.

**BETA-114 note.** BETA-107–113 ran both inference legs on a local Needle 2 /
LFM runtime and forbade any cloud fallback. A CPU-only VPS could not meet the
routing bars (see the table under "Deploying" below), so BETA-114 moved both
legs to [OpenRouter](https://openrouter.ai) — the same third party the review
pipeline already uses for `nlp suggest-decisions`. Only already-public
committee text and non-sensitive aggregates are sent; the router still never
sees retrieved document text. OpenRouter usage is billed per token and the
deployment owns that cost.

## What it is made of

| Piece | Module | What it does |
|---|---|---|
| Runtime boundary | `pipeline/assistant/runtime.py`, `adapters.py` | The `[assistant]` extra (just `openai`), two OpenAI-chat-compatible endpoints (OpenRouter by default; independently configured), `AssistantUnavailable` instead of import/socket errors. Imports with nothing installed. |
| Run ledger | `pipeline/assistant/ledger.py` + migration `0079` | One immutable `assistant_runs` row per turn: question, filters, model identities, prompt-template hashes, routing confidence, validated args, retrieved chunk ids, answer, citation ids, timings, outcome, error class. Append-only. No secrets or model paths. |
| Tool catalogue | `pipeline/assistant/tools.py` | Exactly five typed, side-effect-free tools wrapping existing query code. No argument is a table name, URL, path or SQL. |
| Router | `pipeline/assistant/routing.py` | The router model (`assistant_needle_model`) picks at most one tool. Its name and arguments are re-validated independently; confidence must clear a frozen threshold; anything else is a clarification with no execution. A question that tries to steer the router (set its confidence, "pick any tool regardless of fit", a URL / file path) is rejected in code before the model call. The router is sent only the question and the tool catalogue — never document text. |
| Grounding | `pipeline/assistant/grounding.py` | The answerer model (`assistant_lfm_model`) gets only the validated tool result (retrieved text delimited as untrusted data) and no executable tools. Every `[[id]]` in the answer is checked against the result's own identifiers; an unresolved citation or a missing citation suppresses the answer and returns an abstention. |
| Service | `pipeline/assistant/service.py` | One orchestration function shared by HTTP and CLI. One tool call per turn, short router timeout, 30 s overall ceiling, explicit `ok`/`abstained`/`clarified`/`timeout`/`unavailable`/`failed` outcome. |
| Evaluation & gate | `pipeline/assistant/evaluation.py` + `tests/fixtures/assistant/` | Frozen routing and grounding suites; a machine-readable gate whose `may_enable` field is the only thing that authorises enabling the feature. |

## The five tools

| Tool | Wraps | Result-local identifiers you may cite |
|---|---|---|
| `search_document_passages` | `pipeline.nlp.semantic_search` | `document_chunk_id` |
| `inspect_claim_candidates` | bounded aggregate over `document_claim_candidates` | predicate names |
| `inspect_claim_gate` | `pipeline.nlp.gate` | gate category names |
| `inspect_source_coverage` | `pipeline.web.health.coverage` (per-column covered/total + per-region authority counts) | column labels |
| `inspect_freshness` | `pipeline.web.health.freshness` | table names |

All five are read-only. Bad arguments raise `ToolError`, which the service
turns into a clarification, never a crash and never an execution.

## Enabling it

1. `uv sync --extra assistant` — installs `openai` only. It is not in the
   Railway image.
2. Set the OpenRouter key and both model slugs:

   ```bash
   ASSISTANT_API_KEY=sk-or-...        # or reuse OPENROUTER_API_KEY
   ASSISTANT_NEEDLE_MODEL=<slug>      # the router leg — a cheap/fast model
   ASSISTANT_LFM_MODEL=<slug>         # the answerer leg — a stronger model
   ASSISTANT_NEEDLE_FALLBACK_MODELS=<slug>,<slug>
   ASSISTANT_LFM_FALLBACK_MODELS=<slug>,<slug>
   ASSISTANT_PROVIDER_SORT=latency
   ASSISTANT_MAX_CONCURRENCY=8
   ASSISTANT_MAX_RETRIES=2
   ```

   Fallback values are comma- or newline-separated OpenRouter model slugs.
   The primary model is tried first; OpenRouter then tries the fallbacks on
   rate limiting, provider downtime, moderation refusal or another model
   error. The fallback chain is captured in each new analysis release manifest
   so a release remains reproducible. Existing deployments with only the two
   primary variables continue to work unchanged.

   `ASSISTANT_PROVIDER_SORT=latency` asks OpenRouter to prefer the lowest
   observed provider latency while retaining provider fallback. Leave it blank
   to retain OpenRouter's normal price/uptime balancing. `ASSISTANT_MAX_CONCURRENCY`
   caps in-flight requests per worker process; retries use exponential backoff
   and honour `Retry-After`. Repeated transient failures open a short local
   circuit so a failing endpoint is not hammered.

   For unattended analysis batches, model/provider exhaustion pauses the
   unfinished domain instead of marking it complete. The worker automatically
   retries after `ANALYSIS_RETRY_COOLDOWN_SECONDS`; a stale worker heartbeat is
   recovered in the same way. `ANALYSIS_MAX_AUTOMATIC_RETRIES` caps retries so
   a persistent outage becomes a visible failed run rather than an endless
   loop. `resume_run` remains available for a deliberate manual retry.

   For analysis releases that use dedicated `CLAIM_SIGNAL_*_MODEL` settings,
   use the matching `CLAIM_SIGNAL_SCOUT_FALLBACK_MODELS`,
   `CLAIM_SIGNAL_EXTRACTOR_FALLBACK_MODELS` and
   `CLAIM_SIGNAL_REFLECTION_FALLBACK_MODELS` variables. When the scout returns
   no candidate, the extractor call is skipped; accepted candidates still
   require the original independent extractor agreement.

   `assistant_ollama_url` / `assistant_needle_url` already default to
   `https://openrouter.ai/api/v1`; point them at a self-hosted
   OpenAI-compatible endpoint to run inference locally instead (the key may
   then be blank). An unset slug fails closed — the adapter raises
   `AssistantUnavailable`, "no model configured", rather than sending a stale
   default to OpenRouter.
3. Run the gate:

   ```bash
   uv run python -m pipeline nlp assistant-eval
   ```

   It prints the routing/grounding scores and the gate. **Do not set
   `assistant_enabled = True` until `gate.may_enable` is `true`.** A
   code-complete feature is not an enabled one.

   Two things to know about this step:
   - **The router is stochastic.** A hosted model on OpenRouter is not
     deterministic even at temperature 0 (provider load-balancing), so
     routing precision wobbles ±2 prompts between runs. Run `assistant-eval`
     three times; treat the *worst* run as the result. A single sub-0.95 run
     is a prompt to investigate which prompts flipped, not proof of failure —
     but a run that clears the bar once and fails twice has not passed.
   - **The bars themselves are fixed.** `HELD_OUT_PRECISION_FLOOR` (0.95, in
     `evaluation.py`) and `FROZEN_ROUTING_THRESHOLD` (0.60, in `routing.py`)
     are not knobs to turn down to get a green. If a capable router cannot
     clear them, the fix is a better router or a cleaner fixture, not a lower
     bar. `FROZEN_ROUTING_THRESHOLD` was calibrated against the retired
     Needle 2 confidence head; you *may* re-freeze it against your router
     model if its self-reported confidence sits systematically differently —
     that is a re-calibration, recorded, not a pass-to-fit tweak.
4. Only then set `assistant_enabled = True`.

## Deploying via Ansible

Both `deploy/ansible/` (self-host) and `deploy/ansible-mirror/` build the
`[assistant]` extra into the app and documents-worker images on an explicit
opt-in and write the OpenRouter configuration:

* `assistant_app_enabled: true` builds **both** images with `--build-arg
  INSTALL_ASSISTANT=true` so `openai` is present, and writes
  `ASSISTANT_API_KEY`, `ASSISTANT_NEEDLE_MODEL`, `ASSISTANT_LFM_MODEL` and
  `ASSISTANT_ENABLED=true`. Keep `assistant_enabled` behind step 3's gate —
  on a `beta` mirror set `ASSISTANT_ENABLED=true` in `.env.merge` so it
  survives the checkout reset.
* `assistant_runtime_enabled: true` is the self-host escape hatch: it renders
  `docker-compose.assistant.yml` (one Ollama service on the stack's Docker
  network), `ollama pull`s `assistant_lfm_ollama_ref`, and points
  `ASSISTANT_OLLAMA_URL` / `ASSISTANT_NEEDLE_URL` at `http://ollama:11434/v1`
  instead of OpenRouter. Everything in `vars.yml` about Ollama versions, GGUF
  quirks, context length and the CPU timeouts applies only on this path.

**Which container runs it.** The CLI (`nlp assistant`, `nlp
assistant-eval`) routes to the **documents worker** — that image carries
the `nlp` extra the retrieval tool needs and the frozen eval fixtures, so
the release gate runs there on its defaults. The **app** container gets
`openai` too, for the `POST /api/admin/assistant` HTTP path; four of the
five tools work there, but `search_document_passages` degrades (no `nlp`
extra in the app image — the same limit as `/admin` semantic search).

Railway is unaffected: it builds `Dockerfile` with no build args and does
not build `Dockerfile.documents` at all, so `INSTALL_ASSISTANT` stays
`false` and neither image it produces gets `openai` or a key.

**Model identity.** There is no pinned default (BETA-114): `LFM_MODEL` /
`LFM_QUANT` / `NEEDLE_MODEL` in `pipeline/assistant/runtime.py` are now empty
constants. `assistant_lfm_model` / `assistant_needle_model` are the OpenRouter
slugs the adapters send and `assistant_runs` records; `assistant_lfm_quant`
is a free-text ledger annotation only (OpenRouter serves its own
quantisation).

**The timeouts.** `ROUTER_TIMEOUT_SECONDS` (8) and `OVERALL_TIMEOUT_SECONDS`
(30) are the code defaults. OpenRouter's first-token latency on a cold or
busy model can exceed 8 s; if `assistant-eval` shows a router timeout rate,
relax `assistant_router_timeout_seconds` / `assistant_overall_timeout_seconds`
(0 → the defaults).

**Why the switch (historical).** BETA-107–113 served both legs from a local
Needle 2 / LFM runtime. On the eval suite on a CPU-only VPS (Ollama 0.33.2,
timeouts relaxed to 30 / 90) no model that fit the box passed the routing
bars:

| model | routing precision | wrong executions | verdict |
|---|---|---|---|
| `LFM2.5-350M-GGUF` | 0.014 | 1 | cannot emit the routing JSON at all |
| `lfm2.5-1.2b-instruct` | 0.057 | 13 (incl. injection/forbidden) | emits JSON, parrots `confidence: 0.95`, routes adversarial prompts |
| `LFM2.5-2.6B-GGUF` | *the smallest with a real shot at the bars* | | still needed the relaxed timeouts to fit CPU |

BETA-114 moved both legs to OpenRouter so the model is no longer bounded by
the deployment host.

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

## Cost and terms

OpenRouter meters and bills per token; the deployment picks the router and
answerer slugs and owns that cost. Check the terms of the specific models you
route to — some providers on OpenRouter train on prompts unless a paid or
zero-retention tier is used. Only already-public committee text and
non-sensitive aggregates are ever sent (see `docs/CAVEATS.md`), so this is a
terms/cost question, not a disclosure one. The retired local path used
Liquid's LFM Open License; that no longer applies while no LFM weights are
served.

## Out of scope (separate named decisions and gates required)

LFM embedding/ColBERT replacing the 384-dimensional pgvector path;
model-driven extraction or classification; multi-turn memory; autonomous
multi-tool loops; any public assistant access.

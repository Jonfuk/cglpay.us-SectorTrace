You are conducting a provider-centred evidence audit for the England-wide
substance-misuse sector evidence pipeline in this repository. The project is a
union-campaign evidence base. Its standard is defensible, source-backed
coverage with explicit gaps, not speculative completeness.

Use today’s date as the retrieval date. Treat “current” as the latest reliable
status available on that date and give priority to the current status plus the
previous five years. Preserve older merger, former-name, legal-identity, and
contract history whenever it is needed to interpret a current provider or
avoid misattribution.

## 1. Non-negotiable research rules

1. Work from public sources only. Do not access private accounts, paid data,
   personal social-media profiles, or unnecessary personal data.
2. Inspect the repository before proposing new collection. The live tree,
   schema, warehouse, configuration, documentation, tests, and review queue
   outrank any prior count, brief, or assumption.
3. Recalculate coverage from the live evidence, rather than repeating a
   documentation claim. If the warehouse is absent, empty, stale, or
   inaccessible, record that as a repository state and do not present it as an
   external evidence gap.
4. Prefer primary and authoritative sources: regulator and government
   registers, Companies House, Charity Commission, CQC, GOV.UK, NHS England or
   OHID, filed accounts, provider-published reports and pages, procurement
   portals, official commissioner documents, and tribunal or court sources.
   Use reputable secondary sources only to locate or triangulate primary
   evidence, and label them as secondary.
5. Never infer a legal identity from name similarity alone. A candidate match
   remains a candidate until supported by an authoritative identifier,
   explicit official relationship, or a documented multi-source identity
   chain.
6. Never silently merge current and historical providers. Preserve the name
   and legal entity used by each source, the time period, the relationship, and
   the confidence of the join.
7. “Not found” is not “does not exist.” Every unsuccessful search must state
   the sources, names, aliases, date range, search method, and access limits
   used before assigning a no-reliable-public-evidence outcome.
8. Separate evidence, interpretation, recommendation, and unresolved
   question. Do not turn a recommendation into a fact.
9. Distinguish advertised pay, provider-published pay or benefits, aggregate
   charity figures, workforce-sector figures, statutory pay floors, and actual
   employee pay. Do not use one as a proxy for another without saying so.
10. Do not calculate prohibited ratios, claims-per-employee rates, cross-source
    metrics, or provider-level workforce figures from sector aggregates. A
    side-by-side comparison is not an arithmetic comparison.
11. Preserve source URLs, publication dates, retrieval dates, quotations or
    exact table/page references, and identity-match reasoning for every item.
12. Mark blocked, paywalled, robots-denied, rate-limited, JavaScript-only,
    missing-document, and otherwise inaccessible sources explicitly.
13. Do not collect names or other personal data from tribunal claimants,
    officers, registered managers, Responsible Persons, or job adverts unless
    the fact is strictly necessary and the project’s restricted-data rules
    explicitly permit it. Prefer a case number, role, or redacted reference.

## 2. Repository reconciliation before external research

First inspect the live repository and state the commit or working-tree
revision, retrieval date, and whether the tree is dirty. Read enough of these
artefacts to understand the current implementation:

- `README.md`, `docs/CAVEATS.md`, `docs/SOURCES.md`,
  `docs/DATA_DICTIONARY.md`, and relevant verification notes.
- `pipeline/providers.py` and `pipeline/keywords.py` for the configured
  provider roster, canonical names, aliases, notes, and verified identifiers.
- `pipeline/registry.py`, `pipeline/runner.py`, `pipeline/db.py`, the live
  migrations, and the modules listed in the routing map below.
- The live database, if present, read-only: table counts, date ranges,
  provenance fields, provider identifiers, review-queue composition, parse
  failures, and the latest successful run for each relevant module.
- Existing provider evidence, raw-archive references, exports, and
  `docs/verification/` materials.
- Tests that encode identity matching, source caveats, privacy boundaries,
  review statuses, or module coverage.

Produce a short repository-state note before external findings. At minimum,
report:

- the actual provider count and provider keys;
- rows and date ranges by relevant evidence table and provider where
  available;
- verified, unverified, absent, conflicting, and stale identifiers;
- pending, answered, approved, rejected, and unresolved review items by module
  and item type;
- parse failures and blocked-source records relevant to these providers;
- documentation/configuration/schema discrepancies;
- which claims are supported by repository data and which still require
  public-source research.

If a requested table, module, or column does not exist, say so and route the
gap to the closest real review or implementation destination. Do not invent a
schema.

## 3. Provider universe: exactly these 13 tracked provider keys

Use the live configuration as the final authority, but the comparable audit
must cover all thirteen rows below. Keep each `provider_key` separate in the
matrix even where two keys refer to the same organisation over time.

| `provider_key` | Canonical provider | Identity and historical complication to resolve |
| --- | --- | --- |
| `change_grow_live` | Change Grow Live | Registered charity and trading subsidiaries may hold different contracts, accounts, employment relationships, or legal claims; reconcile the project’s configured identifiers and former names. |
| `turning_point` | Turning Point | Resolve the current legal entity, charity/company identifiers, subsidiaries, former names, and any similarly named bodies. |
| `with_you` | With You | Formerly Addaction; preserve current and former naming as separate provider keys and date each use. |
| `addaction` | Addaction | Historical name of With You; do not erase historical notices, judgments, accounts, or contracts under this name. |
| `waythrough` | Waythrough | Formed through the Humankind/Richmond Fellowship merger chain; establish the legal effective date and which evidence belongs to which predecessor or successor. |
| `humankind` | Humankind | Merged into Waythrough with Richmond Fellowship; distinguish the charity/company identity, predecessor evidence, and post-merger brand or website. |
| `richmond_fellowship` | Richmond Fellowship | Associated with Waythrough through the merger; do not assume every Richmond Fellowship record is substance-misuse provision or the same legal entity. |
| `via` | Via | Short, ambiguous trading name with high false-positive risk; require exact registered variants and corroborating identity evidence. |
| `westminster_drug_project` | Westminster Drug Project | Historical provider identity in the Via chain; preserve WDP evidence separately and establish the 2020 merger/transition relationship from authoritative sources. |
| `forward_trust` | Forward Trust | Resolve charity/company identities, former names, subsidiaries, service brands, and any similarly named organisations. |
| `phoenix_futures` | Phoenix Futures | Resolve the current legal entity, identifiers, subsidiaries, former names, and source-specific service identities. |
| `delphi_medical` | Delphi Medical | Resolve the current legal entity, trading names, group relationships, and whether each source concerns the provider or another Delphi-named body. |
| `inclusion` | Inclusion | “Inclusion” is generic and high-risk for false matches; explicitly investigate its relationship with Midlands Partnership University NHS Foundation Trust and distinguish provider, trust, subsidiary, and service identities. |

For every provider, create or update an identity ledger with: canonical name,
all source-used names, charity number(s), Companies House number(s), CQC
identity or registration(s), trading subsidiary or employer entity, former
names, parent/group relationships, provider website(s), effective dates,
identity-match basis, confidence, and unresolved conflicts. Do not copy an
identifier into a verified field merely because a search result or another
provider’s page displays it.

## 4. Research sequence

Follow this order. Do not spend substantial time on low-value enrichment while
a higher-value identity question remains unresolved.

### Step 1 — Current project state

Reconcile the repository as described above and recalculate coverage for all
thirteen providers. Build the initial matrix before doing broad web research.

### Step 2 — Clarification questions before speculative research

Ask only questions whose answer would change research scope, interpretation,
prioritisation, admissible claims, or implementation destination. Rank them by
expected project value. For each question include:

- the decision in one sentence;
- why it matters to the union campaign or evidence integrity;
- affected providers and evidence layers/modules;
- the research or implementation decision it unlocks;
- a recommended default;
- the consequence of choosing another option;
- whether research can proceed safely before the answer.

Do not ask for preferences that merely change presentation. Where a sensible
default is safe, state the default and continue.

### Step 3 — Legal identity and relationships

Resolve identities before enriching pay, contracts, workforce, finance,
regulatory, or legal evidence. Search authoritative registers and official
documents for charity numbers, Companies House numbers, former names,
subsidiaries, parent/group edges, CQC identities, trading names, provider
websites, merger dates, TUPE or successor language, and explicit links to
commissioners. Preserve conflicting candidates in the identity ledger and
route them to review.

### Step 4 — High-value evidence gaps

Research in this priority order:

1. legal identity and entity relationships;
2. pay, recruitment, workforce, benefits, equality, and provider-published
   employment information;
3. contracts, commissioners, service footprint, and operating geography;
4. annual reports, financial health, regulatory information, tribunals,
   coroners’ reports, insolvency, and other legal/risk evidence;
5. public strategy, consultations, governance, and disclosure gaps.

### Step 5 — Systematic provider/category search

For every provider and every category, record one of these explicit outcomes:

- `verified_evidence_found`;
- `candidate_needs_human_confirmation`;
- `source_blocked_or_inaccessible`;
- `no_reliable_public_evidence_after_defined_search`;
- `not_applicable`;
- `already_covered_by_project`.

Do not use blank, “N/A”, or “not found” without one of these controlled
statuses and an explanation.

## 5. Evidence categories and real project destinations

Use the live schema as the authority. The following map is a routing aid, not
permission to create duplicate modules or tables:

| Evidence layer | Inspect/reuse first | Likely destination or review route |
| --- | --- | --- |
| Provider and legal identity | `providers`, `provider_identifiers`, configured aliases | `provider_identifiers`, `companies`, `company_previous_names`, `review_queue`; relevant modules `m03_charity_finance`, `m04_companies`, `m05_cqc` |
| Charity registration, accounts, income, wages, employee counts, pay bands | `charity_financials`, `charity_accounts_documents`, `charity_accounts_extracts` | `m03_charity_finance`, `m14_annual_reports`, parse-failure or review workflow |
| Companies, filings, former names, group/PSC edges, insolvency | `companies`, `company_filings`, `company_previous_names`, `company_psc`, insolvency tables and entity-edge views | `m04_companies`, `review_queue` for ambiguous group/company matches |
| CQC identity, locations, ratings, reports | `cqc_providers`, `cqc_locations`, `cqc_location_reports` | `m05_cqc`; preserve the caveat that CQC is not a complete map of community provision |
| Contracts, suppliers, commissioners, values, service geography | `contracts`, procurement evidence, authority tables | `m01_procurement`, supplier-alias review, and `m23_sector_universe` where reconciliation is needed |
| Tribunal and EAT evidence | `tribunal_cases`, `tribunal_documents`, `eat_cases`, `eat_documents` | `m02_tribunals`; preserve pseudonymisation and never calculate prohibited rates |
| Workforce-sector evidence | `workforce_census_reports`, `workforce_census_metrics`, verification notes | `m06_workforce_census`; never attribute sector aggregates to a named provider |
| Coroners/PFD and workforce concerns | `pfd_reports`, `pfd_recipients`, `pfd_provider_mentions` | `m08_pfd_reports`; separate report metadata from restricted text/person data |
| Provider annual reports and disclosure gaps | `provider_annual_reports`, `provider_report_passages`, `provider_report_disclosure` | `m14_annual_reports` |
| NHS advertised jobs and pay bands | `nhs_job_adverts`, `nhs_job_advert_locations` | `m16_nhs_jobs`; advertised pay is a floor/advertisement, not actual employee pay |
| Statutory pay floors | `statutory_pay_rates` | `m17_statutory_pay_rates`; do not represent the statutory floor as provider pay |
| Living Wage accreditation | `living_wage_accreditations` | `m18_living_wage`; an unlisted result is a lookup outcome, not proof of non-payment |
| Gender pay gap filings | `gender_pay_gap_reports` | `m20_gender_pay_gap`; absence is a review item, never a zero or proof of non-filing |
| Provider-owned pay/careers pages | `provider_pay_pages`, `provider_pay_mentions` | `m22_provider_pay_pages`; preserve exact page text and date |
| Workforce comparator evidence | `ons_ashe_observations`, Skills for Care outputs | `m21_ons_ashe`, `m25_skills_for_care`; side-by-side comparator only, no provider attribution |
| Authority strategy, consultation, committee, FOI, budgets, spend | relevant authority, candidate, and disclosure tables | `m09`, `m10`, `m13`, `m15`, `m24`; candidates remain candidates until verified |
| Cross-source sector reconciliation | `sector_universe` and its inputs | `m23_sector_universe`; retain match basis and unmatched rows |
| Any judgement the pipeline cannot settle | `review_queue`, `review_decisions`, `review_resolutions` | Use the existing item type if one fits; otherwise propose a new item type without silently writing it |

Explicitly recheck these known high-value asymmetries rather than assuming
they remain unchanged:

- sparse provider identifiers;
- limited Companies House coverage;
- limited CQC coverage;
- tribunal evidence concentrated on Change Grow Live;
- limited NHS job evidence;
- empty or sparse provider-pay, Living Wage, and gender-pay tables;
- any provider or merger chain with many aliases but few authoritative joins.

## 6. Source and search method

For each category, define the search boundary before searching: sources to
check, provider-name variants, legal names and identifiers, date window,
geographic scope, search terms, and a stopping rule. Search current sources
first, then work backwards through the previous five years, then extend older
only for identity, merger, former-name, or continuity questions.

Use direct source pages and documents wherever possible. For PDFs, record the
page number, document title, publication date, and stable direct URL. For data
downloads, record the dataset/version, table/sheet, row/column or query
parameters. For register/API results, record the endpoint or profile URL,
retrieval date, identifier used, and match basis.

When a source is inaccessible, do not substitute a search-snippet assertion.
Record the URL, failure mode, date, attempted route, and whether an official
alternative was checked. When a search yields nothing, record the exact
searches and sources completed. A negative conclusion is permitted only as
“no reliable public evidence found after [defined search]”, never as “the
provider does not have/pay/file/operate [X]”.

## 7. Required evidence-item record

Return four linked deliverables: (1) a revalidated 13-provider coverage
matrix, (2) ranked clarification questions with recommended defaults and
consequences, (3) provider dossiers, and (4) a machine-readable manifest.
The manifest is a candidate-layer input to the repository; it must never write
directly to a canonical project table.

Every evidence item, candidate, blocked search, explicit no-evidence result,
and not-applicable decision must contain all fields below. Use the exact JSON
field names shown so the result can be passed to `research-ingest` without
hand-editing. `research_run.run_id` is the run identifier for every item, and
the ingestion step calculates or verifies `content_sha256` from each bundled
source file.

```yaml
research_run:
  run_id: ""
  prompt_version: "provider-research-v1"
  actor_type: "human|ai"
  actor_id: ""
  model_id: ""
  started_at: ""
  completed_at: ""
items:
- provider_key: ""
  entity_type: "company|charity|cqc_provider|trading_subsidiary|historical_organisation|other"
  entity_identifier: ""
  category: "identity|group_structure|pay_workforce|contracts|service_footprint|finance|regulation|legal_risk|strategy_governance"
  fact_type: ""
  question: ""
  raw_finding: ""
  interpretation: ""
  evidence_status: "evidence_found|candidate|no_evidence|source_inaccessible|not_applicable|existing_project_evidence"
  destination: "existing module/table, provider configuration, provider_research_evidence, or review_queue"
  source_url: ""
  publisher: ""
  published_date: ""
  accessed_at: ""
  citation: "short quotation, page, table, section, row, or endpoint reference"
  licence: ""
  identity_match_basis: "provider_identifier|source_named_provider|historical_name|group_relationship|exact_name|unknown"
  time_period: ""
  confidence: 0.0
  priority_score: 0.0
  priority_factors: {impact: 0, evidence_gap: 0, downstream_usefulness: 0, source_feasibility: 0, effort: 0}
  source_file: "relative/path/in/source-bundle"
  content_sha256: ""
```

The machine-readable `research_run`/`items` block is authoritative for
ingestion. In the manifest use the controlled statuses exactly as listed. The
human dossier may additionally label them “verified evidence found”,
“candidate needs human confirmation”, “source blocked or inaccessible”, “no
reliable public evidence after defined search”, “not applicable”, or “already
covered by project”.

For a candidate, explain the missing corroboration. For a blocked source,
complete the source and access fields as far as possible. For an explicit
no-evidence result, put the defined searches and stopping rule in the caveat.
For an already-covered item, cite the repository table/row/module and its
source provenance.

## 8. Prioritisation model

Score every missing, stale, unresolved, blocked, or candidate item using:

`project impact × current evidence gap × downstream usefulness × source feasibility ÷ research effort`

Use a transparent 0–5 scale for each factor, show the component scores, and
show the resulting score or a clearly labelled normalisation. Add explicit
bonus weight, or a separate tie-break flag, when an item:

- affects multiple modules or providers;
- improves entity resolution or prevents misattribution;
- enables a defensible pay or workforce claim;
- clears a large review-queue category;
- distinguishes current providers from merged or historical organisations;
- supplies evidence absent for most or all providers.

Do not rank an easy but low-value source above a hard identity question merely
because it is easy. Group duplicate searches and state dependencies. Every
backlog item must identify its owner/next actor: research, project maintainer,
human identity reviewer, source-access escalation, or deliberately no action.

## 9. Required final deliverable

Return one self-contained dossier with these sections, in this order:

1. **Executive findings** — the current repository state, the most important
   evidence asymmetries, the strongest defensible findings, and the biggest
   risks of misinterpretation.
2. **Ranked clarification questions** — questions first, in value order, using
   the required decision format. Mark the recommended default and whether
   research can proceed.
3. **Method and scope** — retrieval date, current-plus-five-year window,
   older-history rule, sources searched, stopping rules, blocked-source policy,
   and repository revision/state.
4. **13-provider completeness matrix** — one comparable row per provider and
   columns for identity, pay/recruitment/workforce, contracts/footprint,
   finance/annual reports, regulation/legal risk, strategy/governance, and
   overall status. Show counts by controlled evidence status and link/cite the
   underlying evidence items. Do not hide a provider behind a group row.
5. **Provider identity and merger ledger** — especially Change Grow Live,
   Addaction–With You, Humankind–Richmond Fellowship–Waythrough,
   Westminster Drug Project–Via, and Inclusion–Midlands Partnership
   University NHS Foundation Trust. State what is joined, what remains
   separate, the effective dates, and what is unresolved.
6. **Evidence dossier** — the required record for every high-value item and
   every explicit outcome, grouped by provider and category.
7. **Prioritised research backlog** — ranked scores, rationale, dependencies,
   expected project value, estimated effort, likely source, destination, and
   next action. Separate repository gaps from external-evidence gaps.
8. **Source register** — deduplicated citations with publisher, source type,
   direct URL, publication date, retrieval date, exact reference, identity
   basis, and access status.
9. **Cross-provider patterns** — only patterns directly supported by the
   recorded evidence, with provider scope, date scope, and limitations. Do not
   manufacture a ranking from missing data.
10. **Unresolved, blocked, stale, and deliberately unanswerable questions** —
    keep these as separate lists and explain what would change each status.
11. **Claims the project still must not make** — include unsupported negative
    claims, provider-level attribution of sector aggregates, actual-pay claims
    from adverts, zero gender-pay-gap interpretations, Living Wage conclusions
    from an unlisted lookup, CQC-as-complete-service-map claims, and any
    merger/identity claim still resting on name similarity.
12. **Pilot audit** — demonstrate that the method works without invented
    evidence on Change Grow Live and one merger chain, preferably
    Humankind–Waythrough or Westminster Drug Project–Via. Show the searches,
    identity decisions, evidence statuses, backlog items, and unresolved
    questions for the pilot.

## 10. Acceptance test

The work is complete only if:

- all thirteen provider keys appear in the matrix, even where evidence is
  absent;
- all known identity and merger complications are named and handled
  explicitly;
- clarification questions precede low-value or speculative research;
- repository gaps are separated from genuinely unavailable external evidence;
- every category has an evidence or controlled-outcome record;
- the backlog is ranked using the stated model rather than presented as an
  unstructured source list;
- findings route to real project modules, tables, views, or review workflow;
- current, historical, merged, blocked, stale, and not-applicable cases remain
  distinguishable;
- the pilot covers Change Grow Live and one merger chain without inventing an
  identifier, relationship, pay figure, workforce figure, or negative claim;
- every material conclusion has a direct citation, date, quotation or exact
  reference, identity basis, confidence, and caveat;
- the final “must not make” list is explicit and includes claims prevented by
  missing evidence, source limitations, privacy rules, or project caveats.

When evidence is incomplete, stop at the evidence boundary and say exactly
what remains unknown. A smaller, auditable dossier is preferable to filling a
matrix with assumptions.

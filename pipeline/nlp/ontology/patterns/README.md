# Ontology patterns

Weak-supervision seeds: regular-expression cues that a passage is *about* a
concept or asserts a predicate. Consumed downstream, not here —

* **034C** (`pipeline/nlp/label.py`) uses `concept` patterns as labelling
  functions that write provisional `document_topics` rows with
  `match_method = 'ontology_v1'`.
* **034F** (`pipeline/nlp/relations.py`) uses `predicate` patterns, together
  with span proximity and 034E assertion status, to assemble claim
  candidates. A pattern match is never a claim on its own.

The loader (`pipeline/nlp/ontology.py`) reads every `*.yml` file in this
directory, keys the result by filename stem, and checks that each `concept:`
resolves to a concept id and each `predicate:` to a relation id. It does not
compile or run the regexes — that is the consuming stage's job, so it can
choose its own flags and its own text unit.

## File format

```yaml
schema_version: "1"
patterns:
  - id: recruitment.struggling
    kind: concept              # concept | predicate
    concept: workforce.recruitment_difficulty
    regex: '\b(struggl\w+|difficult\w*|unable|hard) to recruit\b'
    notes: optional scope reminder
  - id: recruitment.pressure_predicate
    kind: predicate
    predicate: workforce.has_recruitment_pressure
    regex: '\brecruit(ment)?\s+(and\s+retention\s+)?(pressure|difficult\w+|challenge\w*)\b'
```

`id` is unique within the file. `regex` is a Python `re` pattern as a
string; keep it conservative — a pattern set that over-fires buries the
review queue, the same lesson as the m14/m15 keyword work.

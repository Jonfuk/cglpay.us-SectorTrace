"""pipeline/nlp/ontology.py — the SectorTrace ontology loader and matcher."""
from __future__ import annotations

import pytest

from pipeline.nlp import ontology

# --- the bundled ontology loads and is internally consistent ----------------

def test_bundled_ontology_loads():
    onto = ontology.load()
    assert onto.schema_version == "1"
    assert len(onto.concepts) >= 50
    assert len(onto.relations) >= 15
    assert onto.version.startswith("onto-")


def test_every_related_reference_resolves():
    onto = ontology.load()
    for concept in onto.concepts.values():
        for ref in concept.related:
            assert ref in onto.concepts, f"{concept.id} relates to unknown {ref}"


def test_every_concept_category_is_declared():
    onto = ontology.load()
    for concept in onto.concepts.values():
        for category in concept.categories:
            assert category in onto.categories, f"{concept.id}: undeclared {category}"


def test_relation_objects_reference_known_categories_and_literals():
    onto = ontology.load()
    for relation in onto.relations.values():
        assert relation.subject in ontology._SUBJECTS
        cat = relation.object_concept_category
        if cat is not None:
            assert cat in onto.categories, f"{relation.id}: object category {cat}"
        lit = relation.object_literal_type
        if lit is not None:
            assert lit in ontology._LITERALS


def test_every_pattern_target_resolves():
    onto = ontology.load()
    for group in onto.patterns.values():
        for pattern in group:
            if pattern.kind == "concept":
                assert pattern.target in onto.concepts
            else:
                assert pattern.target in onto.relations


def test_default_is_cached_and_version_helper_agrees():
    assert ontology.default() is ontology.default()
    assert ontology.version() == ontology.default().version


# --- matching --------------------------------------------------------------

def test_match_is_whole_token_not_substring():
    onto = ontology.load()
    # "ostensibly" contains "ost" but the OST alias must not fire inside it,
    # and "ost" is on the unsafe list anyway.
    hits = {m.concept_id for m in onto.match("this was ostensibly a success")}
    assert "treatment.ost" not in hits
    # the spelled-out form does match
    assert any(m.concept_id == "treatment.ost"
               for m in onto.match("opioid substitution treatment was offered"))


def test_match_folds_simple_plurals():
    onto = ontology.load()
    hits = {m.concept_id for m in onto.match(
        "recovery workers reported high caseloads and unfilled posts")}
    assert "role.recovery_worker" in hits
    assert "workforce.caseload" in hits
    assert "workforce.vacancy" in hits


def test_match_counts_returns_span_counts():
    onto = ontology.load()
    counts = onto.match_counts(
        "methadone and buprenorphine are both opioid substitution treatment options; "
        "buprenorphine again here")
    assert counts["medication.methadone"] == 1
    assert counts["medication.buprenorphine"] == 2
    assert counts["treatment.ost"] == 1


def test_match_on_empty_text_is_empty():
    assert ontology.load().match("") == []
    assert ontology.load().match_counts("   ") == {}
    assert ontology.load().match_spans("") == []


def test_match_spans_returns_character_offsets():
    onto = ontology.load()
    text = "The team relies on agency staff and reports high caseloads."
    spans = {s.concept_id: s for s in onto.match_spans(text)}
    assert "workforce.agency_reliance" in spans
    hit = spans["workforce.caseload"]
    assert text[hit.char_start:hit.char_end].lower() == "high caseloads"


def test_pressure_concepts_are_flagged():
    onto = ontology.load()
    ids = {c.id for c in onto.pressure_concepts()}
    assert "workforce.recruitment_difficulty" in ids
    assert "finance.funding_reduction" in ids
    # a plain vocabulary concept is not a pressure concept
    assert "medication.methadone" not in ids


# --- validation rejects a broken ontology ---------------------------------

_NO_RELATIONS = 'schema_version: "1"\nrelations: []\n'


def _write_ontology(tmp_path, concepts_yml, relations_yml=_NO_RELATIONS):
    root = tmp_path / "onto"
    root.mkdir()
    (root / "concepts.yml").write_text(concepts_yml, encoding="utf-8")
    (root / "relations.yml").write_text(relations_yml, encoding="utf-8")
    return root


_MIN_CONCEPTS = (
    'schema_version: "1"\n'
    "categories: [workforce, pressure]\n"
    "concepts:\n"
    "  - id: workforce.vacancy\n"
    "    label: vacancies\n"
    "    categories: [workforce, pressure]\n"
    "    aliases: [vacancy, vacant posts]\n"
)


def test_load_is_stable_and_changes_with_content(tmp_path):
    root = _write_ontology(tmp_path, _MIN_CONCEPTS)
    first = ontology.load(root).version
    assert ontology.load(root).version == first

    (root / "concepts.yml").write_text(
        _MIN_CONCEPTS.replace("[vacancy, vacant posts]",
                              "[vacancy, vacant posts, unfilled posts]"),
        encoding="utf-8")
    assert ontology.load(root).version != first


def test_undeclared_category_is_rejected(tmp_path):
    root = _write_ontology(tmp_path, _MIN_CONCEPTS.replace(
        "categories: [workforce, pressure]\nconcepts:",
        "categories: [workforce]\nconcepts:"))
    with pytest.raises(ontology.OntologyError):
        ontology.load(root)


def test_unknown_related_reference_is_rejected(tmp_path):
    root = _write_ontology(tmp_path, _MIN_CONCEPTS + "    related: [workforce.nonesuch]\n")
    with pytest.raises(ontology.OntologyError):
        ontology.load(root)


def test_duplicate_concept_id_is_rejected(tmp_path):
    root = _write_ontology(tmp_path, _MIN_CONCEPTS +
                           "  - id: workforce.vacancy\n"
                           "    label: dup\n"
                           "    categories: [workforce]\n"
                           "    aliases: [something else]\n")
    with pytest.raises(ontology.OntologyError):
        ontology.load(root)


def test_concept_with_only_unsafe_aliases_is_rejected(tmp_path):
    root = _write_ontology(tmp_path,
                           'schema_version: "1"\n'
                           "categories: [treatment]\n"
                           "concepts:\n"
                           "  - id: treatment.ost\n"
                           "    label: OST\n"
                           "    categories: [treatment]\n"
                           "    aliases: [ost, oat]\n")
    with pytest.raises(ontology.OntologyError):
        ontology.load(root)


def test_bad_relation_object_is_rejected(tmp_path):
    root = _write_ontology(
        tmp_path, _MIN_CONCEPTS,
        relations_yml='schema_version: "1"\n'
        "relations:\n"
        "  - id: workforce.has_thing\n"
        "    label: has thing\n"
        "    subject: workforce\n"
        "    object: concept:not_a_category\n")
    with pytest.raises(ontology.OntologyError):
        ontology.load(root)

"""Optional Mojo boundary for deterministic ontology/context kernels.

The ABI is deliberately primitive: one packed UTF-8 byte buffer plus text
offsets in, packed integer concept/span/count/ordinal columns out. Python
continues to own ontology loading, sentence boundaries, provenance,
orchestration, and persistence. An extension is optional on every platform.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

_FALLBACK_REPORTED = False


class MojoIncompatible(RuntimeError):
    pass


@dataclass(frozen=True)
class PackedTexts:
    utf8: bytes
    offsets: tuple[int, ...]


@dataclass(frozen=True)
class PackedMatches:
    concept_ids: tuple[int, ...]
    starts: tuple[int, ...]
    ends: tuple[int, ...]
    counts: tuple[int, ...]
    ordinals: tuple[int, ...]


def pack_texts(texts) -> PackedTexts:
    data = bytearray()
    offsets = [0]
    for text in texts:
        data.extend((text or "").encode("utf-8"))
        offsets.append(len(data))
    return PackedTexts(bytes(data), tuple(offsets))


def pack_ontology(ontology):
    """Flatten the authoritative Python trie for the packed Mojo boundary.

    Ontology loading and versioning stay in Python.  The optional extension
    receives only the already-normalised alias rows, so it cannot silently
    load a different vocabulary from disk; its native work is token scanning
    and packed result construction.
    """
    concept_ids = sorted(ontology.concepts)
    rows = []
    for concept_ordinal, concept_id in enumerate(concept_ids):
        for _alias, alias_tokens in ontology.concepts[concept_id].alias_tokens:
            rows.append((concept_ordinal, " ".join(alias_tokens)))
    return tuple(rows)


def select(mode: str):
    """Return the optional extension, or None for the authoritative Python path."""
    global _FALLBACK_REPORTED
    if mode not in {"auto", "python", "mojo"}:
        raise ValueError("NLP_ACCELERATOR must be auto, python, or mojo")
    if mode == "python":
        return None
    try:
        if not sys.platform.startswith("linux"):
            raise MojoIncompatible(f"Mojo NLP extension is Linux-only; platform is {sys.platform}")
        from pipeline.nlp import _mojo_nlp  # type: ignore
        abi_version = getattr(_mojo_nlp, "ABI_VERSION", None)
        if abi_version is None and callable(getattr(_mojo_nlp, "abi_version", None)):
            abi_version = _mojo_nlp.abi_version()
        if abi_version != 1:
            raise MojoIncompatible("Mojo NLP extension ABI is not version 1")
        approved = getattr(_mojo_nlp, "PARITY_APPROVED", None)
        if approved is None and callable(getattr(_mojo_nlp, "parity_approved", None)):
            approved = _mojo_nlp.parity_approved()
        if approved is not True:
            raise MojoIncompatible("Mojo NLP extension has not passed exact ontology parity")
        if not callable(getattr(_mojo_nlp, "match_ontology", None)):
            raise MojoIncompatible("Mojo NLP extension lacks match_ontology ABI v1")
        return _mojo_nlp
    except (ImportError, OSError, MojoIncompatible) as exc:
        if mode == "mojo":
            raise MojoIncompatible(
                f"NLP_ACCELERATOR=mojo but the compatible Linux extension is unavailable: {exc}"
            ) from exc
        if not _FALLBACK_REPORTED:
            logging.getLogger(__name__).warning(
                "NLP_ACCELERATOR=auto: Mojo unavailable (%s); using deterministic Python", exc)
            _FALLBACK_REPORTED = True
        return None


def ontology_matches(ontology, texts, *, mode: str = "auto"):
    """Run the packed extension when installed, otherwise the trie exactly."""
    texts = list(texts)
    extension = select(mode)
    if extension is None:
        return ontology.match_batch(texts)
    packed = pack_texts(texts)
    # The compiled module receives the ontology version and its Python-owned,
    # normalised alias rows. The build gate proves the native result against
    # the authoritative matcher before the extension is allowed to activate.
    result = extension.match_ontology(
        packed.utf8, packed.offsets, ontology.version, pack_ontology(ontology))
    if not isinstance(result, tuple) or len(result) != 5:
        raise MojoIncompatible("Mojo ontology result does not match packed ABI v1")
    return _unpack_matches(ontology, texts, result)


def context_select(candidates, *, mode: str = "auto") -> int | None:
    """Select a cue candidate through the optional packed Mojo reducer."""
    extension = select(mode)
    if extension is None:
        return None
    index = int(extension.select_context(tuple(candidates)))
    if index < 0 or index >= len(candidates):
        raise MojoIncompatible("Mojo context result selected an invalid candidate")
    return index


def _unpack_matches(ontology, texts: list[str], packed_result):
    """Convert ABI-v1 columns into the same row shape as ``match_batch``.

    Concept ordinals are indexes into the ontology's sorted concept IDs. The
    extension does not return the display alias because persistence consumes
    only concept identity and token offsets; recover the deterministic alias
    from the authoritative Python ontology so callers still receive ``Match``
    objects on both accelerator paths.
    """
    from pipeline.nlp.ontology import Match, _fold_tokens, _normalise

    concept_ordinals, starts, ends, counts, text_ordinals = packed_result
    columns = tuple(map(tuple, (concept_ordinals, starts, ends, counts, text_ordinals)))
    if len({len(column) for column in columns}) != 1:
        raise MojoIncompatible("Mojo ontology result columns have inconsistent lengths")
    if any(int(count) != 1 for count in columns[3]):
        raise MojoIncompatible("Mojo ontology ABI v1 requires one packed row per match")
    concept_ids = sorted(ontology.concepts)
    output = [[] for _ in texts]
    token_rows = [_fold_tokens(_normalise(text or "").split()) for text in texts]
    for concept_ordinal, start, end, _count, text_ordinal in zip(*columns, strict=True):
        concept_ordinal = int(concept_ordinal)
        start, end, text_ordinal = int(start), int(end), int(text_ordinal)
        if not (0 <= concept_ordinal < len(concept_ids)):
            raise MojoIncompatible("Mojo ontology result contains an unknown concept ordinal")
        if not (0 <= text_ordinal < len(texts)) or not (0 <= start < end):
            raise MojoIncompatible("Mojo ontology result contains invalid text or span offsets")
        tokens = token_rows[text_ordinal]
        if end > len(tokens):
            raise MojoIncompatible("Mojo ontology result span exceeds its input text")
        concept_id = concept_ids[concept_ordinal]
        matched_tokens = tokens[start:end]
        aliases = [alias for alias, alias_tokens in ontology.concepts[concept_id].alias_tokens
                   if alias_tokens == matched_tokens]
        if not aliases:
            raise MojoIncompatible("Mojo ontology result is not an ontology alias match")
        output[text_ordinal].append(Match(concept_id, aliases[0], start, end))
    for matches in output:
        matches.sort(key=lambda match: (match.start_token, match.end_token, match.concept_id))
    return output

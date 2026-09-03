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
    extension = select(mode)
    if extension is None:
        return ontology.match_batch(texts)
    packed = pack_texts(texts)
    # The compiled module receives the ontology's versioned packed trie. A
    # future extension must expose this exact function and pass row-for-row
    # parity before deployment.
    result = extension.match_ontology(packed.utf8, packed.offsets, ontology.version)
    if not isinstance(result, tuple) or len(result) != 5:
        raise MojoIncompatible("Mojo ontology result does not match packed ABI v1")
    return result

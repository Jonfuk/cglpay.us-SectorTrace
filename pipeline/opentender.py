"""Bounded parsing and matching helpers for the OpenTender UK snapshot.

The OCP Registry's OpenTender publication is a compiled/latest-value mirror,
not the original release stream.  These helpers therefore expose only
source-shaped observations and never turn a mirror row into a contract.
"""
from __future__ import annotations

import gzip
import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Iterator

DEFAULT_OCID_PREFIX = "ocds-70d2nz"
PARSER_VERSION = "m40-opentender-v1"


@dataclass(frozen=True)
class ParseFailure:
    line_number: int
    field_name: str
    raw_fragment: str
    reason: str


@dataclass(frozen=True)
class Observation:
    source_record_id: str
    ocid: str
    buyer_name: str | None
    title: str | None
    cpv_codes: tuple[str, ...]
    value_amount: float | None
    value_currency: str | None
    date_published: str | None
    record_sha256: str


@dataclass
class ParseSummary:
    observations: int = 0
    objects: int = 0
    failures: list[ParseFailure] = field(default_factory=list)


class _ZipMember:
    def __init__(self, archive: zipfile.ZipFile, member):
        self._archive = archive
        self._member = member

    def __iter__(self):
        return iter(self._member)

    def read(self, *args):
        return self._member.read(*args)

    def close(self):
        try:
            self._member.close()
        finally:
            self._archive.close()


def _open_json_member(path: Path) -> BinaryIO:
    """Open a plain, gzip, or single-member ZIP JSON package.

    The returned handle is owned by the caller.  Registry downloads have been
    offered in more than one container format over time, while the records
    inside remain JSON or JSONL.  Refusing ambiguous ZIPs is safer than
    selecting a README or a second data file by accident.
    """
    stream = path.open("rb")
    magic = stream.read(4)
    stream.seek(0)
    if magic.startswith(b"\x1f\x8b\x08"):
        stream.close()
        return gzip.open(path, "rb")
    if magic == b"PK\x03\x04":
        stream.close()
        archive = zipfile.ZipFile(path)
        members = [info for info in archive.infolist()
                   if not info.is_dir() and info.filename.lower().endswith((".json", ".jsonl"))]
        if len(members) != 1:
            archive.close()
            raise ValueError("OpenTender ZIP must contain exactly one JSON/JSONL member")
        # Keep the ZipFile alive through the returned member handle.
        return _ZipMember(archive, archive.open(members[0], "r"))  # type: ignore[return-value]
    return stream


def _objects_from_value(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                compiled = item.get("compiledRelease")
                yield compiled if isinstance(compiled, dict) else item
        return
    if not isinstance(value, dict):
        return
    compiled = value.get("compiledRelease")
    if isinstance(compiled, dict):
        yield compiled
        return
    for key in ("releases", "records", "compiledReleases", "compiled_records"):
        items = value.get(key)
        if isinstance(items, list):
            yield from _objects_from_value(items)
            return
    yield value


def iter_json_objects(path: Path) -> Iterator[tuple[int, bytes, dict[str, Any]]]:
    """Yield ``(line number, exact line bytes, object)`` from a package."""
    stream = _open_json_member(Path(path))
    try:
        for line_number, raw in enumerate(stream, start=1):
            raw = raw.rstrip(b"\r\n")
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                yield line_number, raw, {"__parse_error__": "invalid JSON"}
                continue
            for item in _objects_from_value(value):
                yield line_number, raw, item
    finally:
        stream.close()


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _buyer(release: dict[str, Any]) -> str | None:
    buyer = release.get("buyer")
    buyer_name = buyer.get("name") if isinstance(buyer, dict) else None
    if buyer_name:
        return _first_text(buyer_name)
    for party in release.get("parties") or []:
        if isinstance(party, dict) and "buyer" in (party.get("roles") or []):
            return _first_text(party.get("name"))
    return None


def _cpv_codes(release: dict[str, Any]) -> tuple[str, ...]:
    tender = release.get("tender") or {}
    found: set[str] = set()
    for item in tender.get("items") or []:
        if not isinstance(item, dict):
            continue
        classification = item.get("classification") or {}
        code = classification.get("id") if isinstance(classification, dict) else None
        if isinstance(code, str) and re.fullmatch(r"\d{5,8}(?:-\d)?", code.strip()):
            found.add(code.strip())
    classifications = tender.get("classification")
    for classification in classifications if isinstance(classifications, list) else []:
        if isinstance(classification, dict) and isinstance(classification.get("id"), str):
            code = classification["id"].strip()
            if re.fullmatch(r"\d{5,8}(?:-\d)?", code):
                found.add(code)
    return tuple(sorted(found))


def _value(release: dict[str, Any]) -> tuple[float | None, str | None]:
    value = (release.get("tender") or {}).get("value") or {}
    if not isinstance(value, dict):
        return None, None
    amount = value.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    if amount is not None and not math.isfinite(amount):
        amount = None
    currency = value.get("currency")
    return amount, currency.strip() if isinstance(currency, str) and currency.strip() else None


def parse_object(raw: bytes, release: dict[str, Any], *, ocid_prefix: str = DEFAULT_OCID_PREFIX) -> Observation:
    """Convert one compiled release to a nullable, source-shaped observation."""
    if "__parse_error__" in release:
        raise ValueError("invalid JSON")
    source_record_id = _first_text(release.get("id"))
    if not source_record_id:
        raise ValueError("compiled release missing id")
    ocid = _first_text(release.get("ocid"))
    if not ocid:
        raise ValueError("compiled release missing ocid")
    if not ocid.startswith(ocid_prefix + "-"):
        raise ValueError(f"ocid does not use expected OpenTender prefix {ocid_prefix!r}")
    amount, currency = _value(release)
    tender = release.get("tender") or {}
    return Observation(
        source_record_id=source_record_id,
        ocid=ocid,
        buyer_name=_buyer(release),
        title=_first_text(tender.get("title")) if isinstance(tender, dict) else None,
        cpv_codes=_cpv_codes(release),
        value_amount=amount,
        value_currency=currency,
        date_published=_first_text(release.get("date")),
        record_sha256=__import__("hashlib").sha256(raw).hexdigest(),
    )


def iter_observations(path: Path, *, ocid_prefix: str = DEFAULT_OCID_PREFIX,
                      since: str | None = None, limit: int | None = None,
                      summary: ParseSummary | None = None) -> Iterator[Observation]:
    """Yield valid UK OpenTender observations and retain parse failures.

    A malformed line is quarantined while sibling records continue.  A date
    that cannot be parsed is retained rather than silently filtered out.
    """
    result = summary or ParseSummary()
    for line_number, raw, release in iter_json_objects(Path(path)):
        result.objects += 1
        try:
            observation = parse_object(raw, release, ocid_prefix=ocid_prefix)
        except ValueError as exc:
            result.failures.append(ParseFailure(line_number, "release", raw[:500].decode("utf-8", "replace"), str(exc)))
            continue
        if since and observation.date_published:
            try:
                if date.fromisoformat(observation.date_published[:10]) < date.fromisoformat(since):
                    continue
            except (TypeError, ValueError):
                pass
        if limit is not None and result.observations >= limit:
            break
        result.observations += 1
        yield observation


def normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _date(value: str | None) -> str:
    return (value or "")[:10]


def reconcile(observation: Observation, contracts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return a conservative reconciliation disposition.

    Exact OCID is an observation of shared source identity.  Other matches are
    only candidates: they remain mirror data and require a person to inspect.
    """
    rows = list(contracts)
    exact = [row for row in rows if row.get("ocid") == observation.ocid]
    if exact:
        return {"status": "exact_ocid", "matched_ocid": observation.ocid,
                "candidate_count": len(exact), "basis": "ocid"}

    buyer = normalize(observation.buyer_name)
    title = normalize(observation.title)
    date = _date(observation.date_published)
    candidates = [row for row in rows
                  if buyer and title and date
                  and normalize(row.get("buyer_name")) == buyer
                  and normalize(row.get("title")) == title
                  and _date(row.get("date_published")) == date]
    if observation.value_amount is not None:
        candidates = [row for row in candidates
                      if row.get("value_core") is not None
                      and row.get("currency") == observation.value_currency
                      and math.isclose(float(row["value_core"]), observation.value_amount,
                                       rel_tol=0.0, abs_tol=0.01)]
    if observation.cpv_codes:
        cpv = set(observation.cpv_codes)
        candidates = [row for row in candidates
                      if cpv.intersection(code.strip() for code in
                                           str(row.get("cpv_codes") or "").split(","))]

    if len(candidates) == 1:
        return {"status": "candidate_match", "matched_ocid": candidates[0].get("ocid"),
                "candidate_count": 1, "basis": "buyer_title_date_value_cpv"}
    if candidates:
        return {"status": "ambiguous_match", "matched_ocid": None,
                "candidate_count": len(candidates), "basis": "buyer_title_date_value_cpv"}
    return {"status": "unmatched", "matched_ocid": None,
            "candidate_count": 0, "basis": None}

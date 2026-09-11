"""Bounded local Parquet reading for the Open Jobs shadow source.

PyArrow is intentionally imported only inside ``_pyarrow``.  The ordinary
pipeline can therefore start and discover its modules without the optional
wheel.  This reader accepts local paths only; passing an HTTP URL cannot
silently bypass the shared network and archive controls.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from .contract import (
    DEFAULT_CONTRACT,
    OpenJobsContract,
    ResourceLimitError,
    SchemaError,
    row_size_bytes,
)


class DependencyUnavailable(RuntimeError):
    """The optional Parquet decoder is not installed for this process."""


class ReaderError(ValueError):
    """The local input is not a readable Open Jobs Parquet artifact."""


@dataclass(frozen=True)
class ReaderLimits:
    """Explicit local-reader ceilings; no limit is implied by Arrow defaults."""

    max_artifact_bytes: int = 128 * 1024 * 1024
    max_record_bytes: int = 16 * 1024 * 1024
    decode_batch_rows: int = 256

    def __post_init__(self) -> None:
        for name in ("max_artifact_bytes", "max_record_bytes", "decode_batch_rows"):
            value = getattr(self, name)
            if isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


def _pyarrow() -> Any:
    try:
        pa = importlib.import_module("pyarrow")
        # Import the parquet submodule lazily with the package.  Some Arrow
        # wheels do not expose ``pa.parquet`` until this explicit import.
        importlib.import_module("pyarrow.parquet")
        return pa
    except (ImportError, ModuleNotFoundError) as exc:
        raise DependencyUnavailable(
            "Open Jobs Parquet reading requires the optional 'pyarrow' package"
        ) from exc


def _local_path(path: str | Path) -> Path:
    if isinstance(path, Path):
        local = path
    elif isinstance(path, str):
        if "://" in path:
            raise ReaderError("Open Jobs reader accepts a local path, not a URL")
        local = Path(path)
    else:
        raise TypeError("Parquet path must be a local str or Path")
    if not local.is_file():
        raise ReaderError(f"Parquet artifact is not a regular local file: {local}")
    return local


def _parquet_file(path: Path, limits: ReaderLimits) -> Any:
    actual_size = path.stat().st_size
    if actual_size > limits.max_artifact_bytes:
        raise ResourceLimitError(
            f"Parquet artifact is {actual_size} bytes, over "
            f"{limits.max_artifact_bytes}-byte limit"
        )
    pa = _pyarrow()
    try:
        return pa.parquet.ParquetFile(path)
    except Exception as exc:  # Arrow's exception types vary by supported wheel.
        raise ReaderError(f"cannot open Parquet artifact {path}") from exc


def _schema_names(parquet_file: Any) -> tuple[str, ...]:
    try:
        return tuple(parquet_file.schema_arrow.names)
    except Exception as exc:
        raise ReaderError("Parquet artifact has no readable schema") from exc


def iter_batches(path: str | Path, *, columns: Iterable[str] | None = None,
                 limits: ReaderLimits | None = None,
                 contract: OpenJobsContract = DEFAULT_CONTRACT) -> Iterator[Any]:
    """Yield bounded ``pyarrow.RecordBatch`` objects from a local artifact."""
    limits = limits or ReaderLimits()
    local = _local_path(path)
    parquet_file = _parquet_file(local, limits)
    names = _schema_names(parquet_file)
    try:
        contract.validate_arrow_schema(parquet_file.schema_arrow)
    except AttributeError:
        # A tiny schema stub is useful for offline unit tests; real Arrow
        # ParquetFile instances always expose schema_arrow.
        contract.validate_columns(names)
    selected = None if columns is None else tuple(columns)
    if selected is not None:
        unknown = sorted(set(selected).difference(names))
        if unknown:
            raise SchemaError("requested columns are absent: " + ", ".join(unknown))
        if not selected:
            raise SchemaError("at least one Parquet column must be selected")
    # A projected result still has to validate the identity and lifecycle
    # columns.  Read those columns alongside the caller's projection, then
    # return only what was requested; otherwise selecting ``title`` could hide
    # a malformed ``id`` and make an invalid release look usable.
    read_columns = selected
    if selected is not None:
        required_for_validation = set(contract.required_columns)
        if contract.require_operation:
            required_for_validation.add("op")
        read_columns = tuple(dict.fromkeys((*selected, *required_for_validation)))
    try:
        batches = parquet_file.iter_batches(
            batch_size=limits.decode_batch_rows,
            columns=read_columns,
        )
        for batch in batches:
            # ``to_pylist`` is bounded by decode_batch_rows and allows the
            # contract to reject malformed identity/operation values before a
            # caller can treat them as a successful empty or partial release.
            rows = batch.to_pylist()
            for number, row in enumerate(rows, 1):
                # Projection may intentionally omit identity columns after the
                # complete Parquet schema has already been checked above.
                # Validate the row-level contract whenever the projection
                # carries the required fields; otherwise retain the projected
                # values and enforce only the size ceiling.
                if contract.required_columns.issubset(row) and (
                    not contract.require_operation or "op" in row
                ):
                    contract.validate_row(row, row_number=number)
                if row_size_bytes(row) > limits.max_record_bytes:
                    raise ResourceLimitError(
                        f"record exceeds {limits.max_record_bytes}-byte limit"
                    )
            if selected is not None:
                yield batch.select(selected)
            else:
                yield batch
    except (ResourceLimitError, SchemaError):
        raise
    except Exception as exc:
        raise ReaderError(f"failed while reading Parquet artifact {local}") from exc


def iter_records(path: str | Path, *, columns: Iterable[str] | None = None,
                 limits: ReaderLimits | None = None,
                 contract: OpenJobsContract = DEFAULT_CONTRACT) -> Iterator[dict[str, Any]]:
    """Yield plain dictionaries, retaining Arrow's nulls as ``None``."""
    for batch in iter_batches(path, columns=columns, limits=limits, contract=contract):
        for row in batch.to_pylist():
            yield row


def read_rows(path: str | Path, *, columns: Iterable[str] | None = None,
              limits: ReaderLimits | None = None,
              contract: OpenJobsContract = DEFAULT_CONTRACT) -> list[dict[str, Any]]:
    """Materialise a bounded fixture or caller-selected result set."""
    return list(iter_records(path, columns=columns, limits=limits, contract=contract))


def read_parquet(path: str | Path, **kwargs: Any) -> list[dict[str, Any]]:
    """Compatibility spelling for callers that explicitly request rows."""
    return read_rows(path, **kwargs)

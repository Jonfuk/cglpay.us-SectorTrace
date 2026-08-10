"""Shared pydantic v2 base models. Domain-specific record models are added
alongside each module (pipeline/modules/mNN_*.py) as they're built; this
file holds only what's common to every one of them: the provenance contract
required by constraint 1, plus a couple of enums reused across modules.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ProvenancedRecord(BaseModel):
    """Every extracted record must carry these five fields (constraint 1).
    Domain models subclass this rather than repeating the columns.
    """

    model_config = ConfigDict(extra="forbid")

    source_url: str
    retrieved_at: datetime
    http_status: int
    source_system: str
    payload_sha256: str


class EmployeesBasis(str, Enum):
    """Whether a headcount figure is FTE or raw headcount — must be captured
    explicitly (Module 3), never assumed.
    """

    HEADCOUNT = "headcount"
    FTE = "fte"
    UNKNOWN = "unknown"


class ExtractionConfidence(str, Enum):
    """Field-level confidence flag for values derived from a lower-fidelity
    source than the primary one (e.g. PDF text vs. page metadata in Module 2).
    """

    HIGH = "high"
    LOW = "low"


class VerificationStatus(str, Enum):
    """Status of a discovered-but-unconfirmed document candidate (Modules 9, 10).
    Only VERIFIED rows may be promoted into a canonical table.
    """

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

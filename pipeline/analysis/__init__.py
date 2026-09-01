"""Shared contracts and deterministic services for SectorTrace analysis.

The analysis package is deliberately downstream of collection.  It consumes
archived rows and document elements and writes versioned, admin-only signals;
it never changes canonical facts or human Evidence Graph claims.
"""

from pipeline.analysis.domains import AnalysisDomainSpec, domain_registry, get_domain
from pipeline.analysis.signals import Signal, SignalValidationError

__all__ = [
    "AnalysisDomainSpec",
    "Signal",
    "SignalValidationError",
    "domain_registry",
    "get_domain",
]

"""Analysis domain specifications and the built-in SectorTrace registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class AnalysisDomainSpec:
    """The complete adapter contract for one analysis domain."""

    domain_id: str
    source_tables: tuple[str, ...]
    analysis_unit: str
    canonical_subject_keys: tuple[str, ...]
    population_query: str
    taxonomy_namespace: str
    discovery_policy: Mapping[str, Any] = field(default_factory=dict)
    extractor_or_detector: str = "deterministic"
    verification_policy: Mapping[str, Any] = field(default_factory=dict)
    consolidation_key: tuple[str, ...] = ()
    cross_source_rules: tuple[str, ...] = ()
    reporting_views: tuple[str, ...] = ()
    quality_contract: Mapping[str, Any] = field(default_factory=dict)
    text_builder: Callable | None = None
    feature_builder: Callable | None = None

    def validate(self) -> None:
        if not self.domain_id or not self.taxonomy_namespace:
            raise ValueError("analysis domains need domain_id and taxonomy_namespace")
        if not self.source_tables:
            raise ValueError(f"{self.domain_id}: source_tables cannot be empty")
        if not self.analysis_unit or not self.canonical_subject_keys:
            raise ValueError(f"{self.domain_id}: subject contract is incomplete")
        if not self.population_query.strip():
            raise ValueError(f"{self.domain_id}: population_query cannot be empty")
        if not self.consolidation_key:
            raise ValueError(f"{self.domain_id}: consolidation_key cannot be empty")


def _narrative(domain_id: str, namespace: str, tables: tuple[str, ...], subject: str,
               rules: tuple[str, ...]) -> AnalysisDomainSpec:
    return AnalysisDomainSpec(
        domain_id=domain_id,
        source_tables=tables,
        analysis_unit="document_window",
        canonical_subject_keys=(subject,),
        population_query="SELECT document_element_id, document_version_id FROM document_elements",
        taxonomy_namespace=namespace,
        discovery_policy={"preserve_outliers": True, "open_set": True},
        extractor_or_detector="dual_model_narrative",
        verification_policy={"dual_model_agreement": True, "exact_quotes": True,
                              "minicheck": True, "alignscore": True},
        consolidation_key=("domain_id", "subject_id", "taxonomy_namespace", "signal_type"),
        cross_source_rules=rules + ("narrative_structured_alignment", "temporal_context"),
        reporting_views=("signals", "topics", "themes", "coverage"),
        quality_contract={"human_verified": False, "planned_excluded_from_occurrences": True},
    )


_DOMAINS: tuple[AnalysisDomainSpec, ...] = (
    _narrative("da", "da", ("committee_papers", "cdp_documents"), "authority_id",
                ("commissioning_narrative", "funding_pressure", "workforce_pressure")),
    _narrative("provider", "provider", ("provider_annual_reports", "provider_pay_pages", "nhs_job_adverts"),
                "provider_id", ("provider_change", "workforce_pressure")),
    _narrative("commissioning", "commissioning",
                ("committee_papers", "icb_board_papers", "foi_requests"), "authority_id",
                ("commissioning_procurement", "funding_pressure")),
    _narrative("quality_safety", "quality_safety",
                ("pfd_reports", "sar_documents", "hse_enforcement_notices"),
                "authority_id", ("safety_event", "regulatory_event")),
    _narrative("legal_employment", "legal_employment", ("tribunal_cases",), "provider_id",
                ("provider_change",)),
    _narrative("housing", "housing",
                ("rough_sleeping_snapshot", "statutory_homelessness_snapshot",
                 "temporary_accommodation_snapshot"), "authority_id", ("housing_pressure",)),
    AnalysisDomainSpec(
        domain_id="procurement", source_tables=("contracts", "council_spend"),
        analysis_unit="subject_period_metric", canonical_subject_keys=("buyer_id", "provider_id"),
        population_query="SELECT * FROM contracts", taxonomy_namespace="procurement",
        discovery_policy={"open_set": False}, extractor_or_detector="structured_comparison",
        verification_policy={"canonical_numbers": True}, consolidation_key=("subject_id", "period_end", "metric"),
        cross_source_rules=("contract_event", "narrative_structured_alignment", "temporal_context"), reporting_views=("structured", "links"),
        quality_contract={"min_comparable_observations": 5}),
    AnalysisDomainSpec(
        domain_id="provider_finance", source_tables=("charity_financials", "charity_accounts_extracts"),
        analysis_unit="subject_period_metric", canonical_subject_keys=("provider_id",),
        population_query="SELECT * FROM charity_accounts", taxonomy_namespace="provider",
        extractor_or_detector="structured_comparison", verification_policy={"canonical_numbers": True},
        consolidation_key=("subject_id", "period_end", "metric"),
        cross_source_rules=("financial_context", "narrative_structured_alignment", "temporal_context"),
        reporting_views=("structured", "links"), quality_contract={"min_comparable_observations": 5}),
    AnalysisDomainSpec(
        domain_id="workforce_pay", source_tables=("workforce_census_metrics", "nhs_job_adverts", "provider_pay_mentions"),
        analysis_unit="subject_period_metric", canonical_subject_keys=("provider_id", "authority_id"),
        population_query="SELECT * FROM workforce_census", taxonomy_namespace="workforce",
        extractor_or_detector="structured_comparison", verification_policy={"canonical_numbers": True},
        consolidation_key=("subject_id", "period_end", "metric"),
        cross_source_rules=("workforce_context", "narrative_structured_alignment", "temporal_context"),
        reporting_views=("structured", "links"), quality_contract={"min_comparable_observations": 5}),
    AnalysisDomainSpec(
        domain_id="treatment_public_health", source_tables=("ndtms_la_statistics", "ndtms_monthly_statistics", "fingertips_la_values", "la_revenue_budgets"),
        analysis_unit="subject_period_metric", canonical_subject_keys=("authority_id",),
        population_query="SELECT * FROM ndtms_annual", taxonomy_namespace="public_health",
        extractor_or_detector="structured_comparison", verification_policy={"canonical_numbers": True},
        consolidation_key=("subject_id", "period_end", "metric"),
        cross_source_rules=("access_context", "narrative_structured_alignment", "temporal_context"),
        reporting_views=("structured", "links"), quality_contract={"min_comparable_observations": 5}),
    AnalysisDomainSpec(
        domain_id="regulation_enforcement", source_tables=("cqc_locations", "hse_enforcement_notices"),
        analysis_unit="subject_period_metric", canonical_subject_keys=("provider_id", "authority_id"),
        population_query="SELECT * FROM cqc_location_reports", taxonomy_namespace="regulation",
        extractor_or_detector="structured_comparison", verification_policy={"canonical_numbers": True},
        consolidation_key=("subject_id", "period_end", "metric"),
        cross_source_rules=("safety_event", "narrative_structured_alignment", "temporal_context"),
        reporting_views=("structured", "links"), quality_contract={"min_comparable_observations": 5}),
    AnalysisDomainSpec(
        domain_id="housing_pressure",
        source_tables=("rough_sleeping_snapshot", "statutory_homelessness_snapshot",
                       "temporary_accommodation_snapshot"),
        analysis_unit="subject_period_metric", canonical_subject_keys=("authority_id",),
        population_query="SELECT * FROM rough_sleeping_snapshot",
        taxonomy_namespace="housing", discovery_policy={"open_set": False},
        extractor_or_detector="structured_comparison",
        verification_policy={"canonical_numbers": True},
        consolidation_key=("subject_id", "period_end", "metric"),
        cross_source_rules=("housing_context", "narrative_structured_alignment", "temporal_context"),
        reporting_views=("structured", "links"),
        quality_contract={"min_comparable_observations": 5}),
)


def domain_registry(extra: list[AnalysisDomainSpec] | None = None) -> dict[str, AnalysisDomainSpec]:
    registry = {spec.domain_id: spec for spec in _DOMAINS}
    for spec in extra or []:
        spec.validate()
        if spec.domain_id in registry:
            raise ValueError(f"duplicate analysis domain {spec.domain_id!r}")
        registry[spec.domain_id] = spec
    for spec in registry.values():
        spec.validate()
    return registry


def get_domain(domain_id: str) -> AnalysisDomainSpec:
    try:
        return domain_registry()[domain_id]
    except KeyError as exc:
        raise KeyError(f"unknown analysis domain {domain_id!r}") from exc

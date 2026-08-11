"""Which OHID Fingertips indicators Module 12 collects, and why.

Chosen to fill the local-authority gap Module 7 exposed: the GOV.UK NDTMS
data tables publish numbers in treatment, waiting times and successful
completions nationally, but only one sheet at local-authority level. These
indicators carry the same measures per authority, with ONS area codes.

Indicator IDs are stable in Fingertips and are listed explicitly rather than
discovered by keyword search, because a search would silently change the
collected set whenever OHID adds or renames an indicator — and a series that
quietly gains or loses a measure between runs is not defensible evidence.

ON UNMET NEED: the brief asks for unmet need estimates. Fingertips does not
publish unmet need as an indicator. It publishes *prevalence* (91117) and
*numbers in treatment* (92454, 91182) separately, and unmet need is
conventionally the gap between them. This module stores each as published and
does NOT compute the difference: the two come from different estimation
methods with different populations and confidence intervals, and subtracting
one from the other here would manufacture a figure the source does not state.
"""
from __future__ import annotations

# Fingertips area type for upper-tier local authorities. Fingertips versions
# these by local government reorganisation period:
#   202 = 4/19-3/20, 302 = 4/20-3/21, 402 = 4/21-3/23, 502 = post 4/23
# 502 is the current geography and the default.
DEFAULT_AREA_TYPE_IDS: list[int] = [502]

# Area type is set PER INDICATOR rather than globally, because a discontinued
# indicator has no data under the current geography and a live one would be
# fetched twice (producing two rows for the same authority-period under
# different geography vintages, which naive aggregation would double-count).
# Only indicators that need a non-default vintage are listed here.
AREA_TYPE_OVERRIDES: dict[int, list[int]] = {
    # Both were discontinued before the post-4/23 geography, so they return
    # nothing under 502 and their series ends at 2022/23. Worth knowing: this
    # means LA-level alcohol waiting-time data is no longer published at all.
    91123: [402],
    91182: [402],
}


def area_type_ids_for(indicator_id: int) -> list[int]:
    return AREA_TYPE_OVERRIDES.get(indicator_id, DEFAULT_AREA_TYPE_IDS)

# Parent area type used to group results (Government Office Region).
PARENT_AREA_TYPE_ID = 6

# indicator_id -> short slug and the brief requirement it serves.
INDICATORS: dict[int, dict[str, str]] = {
    92454: {"slug": "adults_in_drug_treatment_rate",
             "topic": "numbers_in_treatment", "substance": "drug"},
    92455: {"slug": "adults_in_alcohol_treatment_rate",
             "topic": "numbers_in_treatment", "substance": "alcohol"},
    91182: {"slug": "number_in_alcohol_treatment",
             "topic": "numbers_in_treatment", "substance": "alcohol"},
    90244: {"slug": "successful_completion_drug_opiate",
             "topic": "successful_completions", "substance": "drug"},
    90245: {"slug": "successful_completion_drug_non_opiate",
             "topic": "successful_completions", "substance": "drug"},
    92447: {"slug": "successful_completion_alcohol",
             "topic": "successful_completions", "substance": "alcohol"},
    91123: {"slug": "waiting_over_3_weeks_alcohol",
             "topic": "waiting_times", "substance": "alcohol"},
    # Prevalence, NOT unmet need — see module docstring.
    91117: {"slug": "prevalence_opiate_crack",
             "topic": "prevalence", "substance": "drug"},
    92544: {"slug": "treatment_need_engaged_community",
             "topic": "treatment_need", "substance": "substance_misuse"},
    90808: {"slug": "hospital_admissions_substance_misuse_15_24",
             "topic": "harm", "substance": "substance_misuse"},
}

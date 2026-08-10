"""Per-charity accounts-extraction config (Module 3).

Charity accounts are free-form documents: every organisation lays out its
staff-costs note differently and labels the lines differently, so there is
no single parser that works across all of them. The brief requires a
per-charity config for exactly this reason, with anything that doesn't
parse cleanly routed to review_queue rather than approximated.

DEFAULT_PROFILE covers the common SORP phrasing. Add a per-charity entry
only when a charity's own wording differs — and add it after reading that
charity's accounts, not by guessing what it might say.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AccountsProfile:
    """Label patterns for one charity's staff-costs note.

    Each entry is a list of alternative labels tried in order; the first
    that matches wins. Matching is case-insensitive and anchored to the
    start of a line, so a label cannot accidentally match mid-sentence.
    """

    # Page is located by requiring ALL of one of these keyword groups.
    locator_keywords: list[list[str]] = field(default_factory=lambda: [
        ["wages and salar"],
        ["staff costs"],
        ["average number of employees"],
    ])

    wages_and_salaries: list[str] = field(default_factory=lambda: [
        "wages and salary costs",
        "wages and salaries",
    ])
    social_security_costs: list[str] = field(default_factory=lambda: [
        "social security costs",
        "national insurance costs",
    ])
    pension_costs: list[str] = field(default_factory=lambda: [
        "pension costs for defined contribution pension schemes",
        "pension costs",
    ])
    agency_and_third_party: list[str] = field(default_factory=lambda: [
        # CGL hyphenates "third-party" from 2024 onward but not before, so
        # both forms are needed to get a continuous series.
        "agency and third-party organisations",
        "agency and third party organisations",
        "agency staff costs",
        "agency costs",
    ])
    redundancy_costs: list[str] = field(default_factory=lambda: [
        "redundancy costs",
        "termination costs",
    ])
    average_employees: list[str] = field(default_factory=lambda: [
        "average number of employees",
        "average headcount",
    ])
    average_employees_fte: list[str] = field(default_factory=lambda: [
        "average number of full time equivalents",
        "average number of full-time equivalents",
        "average number of employees (full time equivalent)",
    ])
    staff_costs_total: list[str] = field(default_factory=lambda: [
        "total",
    ])

    # What `average_employees` means for this charity. 'unknown' is a valid
    # and honest answer — it must never be silently defaulted to headcount.
    employees_basis: str = "headcount"


DEFAULT_PROFILE = AccountsProfile()

# charity_number -> profile override. Empty until a charity is observed to
# need one; unparseable accounts go to review_queue in the meantime.
PROFILES: dict[str, AccountsProfile] = {}


def profile_for(charity_number: str) -> AccountsProfile:
    return PROFILES.get(charity_number, DEFAULT_PROFILE)

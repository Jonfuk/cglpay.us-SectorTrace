"""Explicit buyer-name -> ons_code overrides for procurement notices whose
buyer name deterministic normalisation (see m01_procurement._normalise_authority_name)
can't resolve against pipeline.db's authorities table.

Add entries here as they're discovered via review_queue (item_type =
'unmatched_buyer_name') — a human decision, never a fuzzy match. Keys may
be either the raw buyer name as it appears in a notice, or its normalised
form (lowercase, punctuation stripped, common council suffixes removed).
"""

BUYER_NAME_OVERRIDES: dict[str, str] = {
    # "Some Oddly-Named Council Entity": "E06000001",
}

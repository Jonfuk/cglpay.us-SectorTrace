# Autonomous evidence-promotion policy

The ordinary promotion path remains available to named human reviewers. The
autonomous path is deliberately narrower and records a different actor type;
an AI model is never written into `review_decisions.decided_by` or presented
as a human reviewer.

An autonomous recommendation must come from an official or already-sanctioned
source, identify the authority/provider exactly, state the document type and
date, have an archived payload and hash, contain no conflicting signals, and
carry two independent research-agent reviews. `pipeline.ai_promotion` checks
these predicates before calling the normal fetch-and-archive promotion path.

The resulting `evidence_promotions` row records `actor_type = 'ai'`, the actor
batch, model, policy version, evidence-manifest hash, review count, confidence,
and QA state. This gives AI-promoted evidence the same eligibility as human
evidence while keeping its method visible and reproducible.

Fuzzy entity matches, provider/group membership, census context, gender-pay
absence decisions, shared-officer identity, contradictory sources, and any
consequential negative assertion remain human-routed. Autonomous decisions are
sampled at 10%; every conflict is reviewed. A false promotion pauses the
policy and quarantines the affected batch for full review.

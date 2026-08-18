"""Confidence and the abstention policy.

Abstention is a first-class outcome here, not a degraded pass. Two things send a
rule to a human: the two passes disagreeing, and confidence falling below the
configured floor.
"""

from __future__ import annotations

from .adversary import PassB
from .models import NEEDS_HUMAN
from .verifier import PassA

RETRIEVAL_REFERENCE = 0.6  # the stage-1 score at which retrieval stops adding doubt


def confidence_of(pass_a: PassA, pass_b: PassB, stage1_top_score: float) -> float:
    agreement_bonus = 0.0 if pass_b.overturned else 1.0
    retrieval = min(stage1_top_score / RETRIEVAL_REFERENCE, 1.0) if stage1_top_score else 0.0
    return round(
        0.5 * pass_a.confidence + 0.3 * agreement_bonus + 0.2 * retrieval,
        4,
    )


def decide(
    pass_a: PassA, pass_b: PassB, stage1_top_score: float, abstain_below: float
) -> tuple[str, float, str | None]:
    """Return (final verdict, confidence, abstention reason)."""
    confidence = confidence_of(pass_a, pass_b, stage1_top_score)

    if pass_b.overturned:
        return NEEDS_HUMAN, confidence, "the two passes disagreed"
    if pass_a.verdict == NEEDS_HUMAN:
        return NEEDS_HUMAN, confidence, "the first pass declined to decide"
    if confidence < abstain_below:
        return NEEDS_HUMAN, confidence, f"confidence {confidence:.2f} is below {abstain_below:.2f}"
    return pass_a.verdict, confidence, None

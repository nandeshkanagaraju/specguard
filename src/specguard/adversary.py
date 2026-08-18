"""Pass B - the opposing brief.

The base paper (Jin & Chen 2026) shows that asking an LLM to explain and fix
inflates false rejection: a single confident pass over-corrects. Requiring the
claim to survive an argument against it converts most of those over-corrections
into honest abstentions instead of false alarms.
"""

from __future__ import annotations

from dataclasses import dataclass

from .adapters.base import ModelAdapter, ModelError, parse_json_response
from .models import ALIGNED, DRIFTED, Candidate, Rule
from .prompts import PASS_B_SYSTEM, pass_b_user

MAX_TOKENS = 500


@dataclass
class PassB:
    ran: bool
    overturned: bool
    argument: str
    confidence: float
    error: str | None = None


def challenge(
    rule: Rule,
    candidates: list[Candidate],
    verdict: str,
    reasoning: str,
    adapter: ModelAdapter,
) -> PassB:
    """Only decided verdicts get challenged; there is nothing to argue against an abstention."""
    if verdict not in (ALIGNED, DRIFTED):
        return PassB(ran=False, overturned=False, argument="", confidence=0.0)

    user = pass_b_user(rule, candidates, verdict, reasoning)
    try:
        raw = adapter.complete(PASS_B_SYSTEM, user, max_tokens=MAX_TOKENS)
        payload = parse_json_response(raw)
    except (ValueError, ModelError) as exc:
        # A second pass that cannot run must not silently confirm the first one.
        return PassB(
            ran=True,
            overturned=False,
            argument=f"The second pass did not return a usable argument ({exc}).",
            confidence=0.0,
            error=str(exc),
        )

    overturned = bool(payload.get("overturned", False))
    argument = str(payload.get("argument", "")).strip()
    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    if overturned and not argument:
        # An overturn with no argument is not an overturn.
        overturned = False
        argument = "The second pass claimed an overturn without stating one."

    return PassB(ran=True, overturned=overturned, argument=argument, confidence=confidence)

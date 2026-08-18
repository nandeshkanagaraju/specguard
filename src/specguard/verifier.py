"""Stage 2 - semantic verification (Pass A).

The validation in here is the substance of the "every verdict cites code" claim.
A response that cites a line it was never shown, or claims drift without citing
anything, is discarded — not down-weighted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .adapters.base import ModelAdapter, ModelError, parse_json_response
from .models import ALIGNED, DRIFTED, DRIFT_CATEGORIES, NEEDS_HUMAN, Candidate, Evidence, Rule
from .prompts import PASS_A_SYSTEM, pass_a_user

MAX_TOKENS = 900


@dataclass
class PassA:
    verdict: str
    category: str | None
    confidence: float
    evidence: list[Evidence]
    reasoning: str
    rejected: str | None = None  # why a response was thrown away, for the report


class EvidenceRejected(ValueError):
    pass


def _clamp(value: object, default: float = 0.0) -> float:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, f))


def validate_evidence(
    raw: list[dict], candidates: list[Candidate]
) -> list[Evidence]:
    """Every cited span must sit inside a chunk this call actually supplied."""
    spans = {c.chunk.path: [] for c in candidates}
    for c in candidates:
        spans[c.chunk.path].append((c.chunk.line_start, c.chunk.line_end, c.chunk))

    out: list[Evidence] = []
    for item in raw or []:
        if not isinstance(item, dict):
            raise EvidenceRejected("evidence item was not an object")
        path = str(item.get("path", "")).strip()
        try:
            start = int(item.get("line_start"))
            end = int(item.get("line_end"))
        except (TypeError, ValueError):
            raise EvidenceRejected(f"evidence for {path!r} had non-integer lines")
        if end < start:
            raise EvidenceRejected(f"evidence for {path!r} had end before start")
        if path not in spans:
            raise EvidenceRejected(f"cited {path!r}, which was not supplied")
        holder = next(
            (chunk for lo, hi, chunk in spans[path] if lo <= start and end <= hi), None
        )
        if holder is None:
            raise EvidenceRejected(
                f"cited {path}:{start}-{end}, outside every supplied chunk"
            )
        offset = start - holder.line_start
        snippet = "\n".join(holder.source.splitlines()[offset : offset + (end - start + 1)])
        out.append(Evidence(path=path, line_start=start, line_end=end, snippet=snippet))
    return out


def _interpret(payload: dict, candidates: list[Candidate]) -> PassA:
    verdict = str(payload.get("verdict", "")).strip().upper()
    if verdict not in (ALIGNED, DRIFTED, NEEDS_HUMAN):
        raise EvidenceRejected(f"unknown verdict {verdict!r}")

    category = payload.get("category")
    if isinstance(category, str):
        category = category.strip().upper()
    if category in ("", "NULL", "NONE"):
        category = None
    if category is not None and category not in DRIFT_CATEGORIES:
        category = None

    evidence = validate_evidence(payload.get("evidence") or [], candidates)

    if verdict in (ALIGNED, DRIFTED) and not evidence:
        # A decided verdict with no cited line is not a decided verdict. This
        # applies to ALIGNED as much as to DRIFTED: "the code does the right
        # thing" is a claim about specific lines, and an uncited claim cannot be
        # audited. Weak models produce these constantly — the correct response
        # is to abstain, not to record an unverifiable pass.
        raise EvidenceRejected(f"{verdict} with no evidence")
    if verdict == DRIFTED and category is None:
        category = "D2"

    return PassA(
        verdict=verdict,
        category=category if verdict == DRIFTED else None,
        confidence=_clamp(payload.get("confidence"), 0.5),
        evidence=evidence,
        reasoning=str(payload.get("reasoning", "")).strip(),
    )


def verify(rule: Rule, candidates: list[Candidate], adapter: ModelAdapter) -> PassA:
    """One rule, one request, one validated verdict. Retries once, then abstains."""
    user = pass_a_user(rule, candidates)
    last_error = ""

    for attempt in (1, 2):
        try:
            raw = adapter.complete(PASS_A_SYSTEM, user, max_tokens=MAX_TOKENS)
            return _interpret(parse_json_response(raw), candidates)
        except (ValueError, ModelError) as exc:
            last_error = str(exc)
            if attempt == 2:
                break

    return PassA(
        verdict=NEEDS_HUMAN,
        category=None,
        confidence=0.0,
        evidence=[],
        reasoning=(
            "The checker could not produce a usable, evidence-backed verdict for this "
            "rule, so it is being routed to a human."
        ),
        rejected=last_error,
    )

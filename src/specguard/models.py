"""Core data models. Everything that crosses a layer boundary is defined here."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------- verdicts

ALIGNED = "ALIGNED"
DRIFTED = "DRIFTED"
NEEDS_HUMAN = "NEEDS_HUMAN"
UNMAPPED = "UNMAPPED"

VERDICTS = (ALIGNED, DRIFTED, NEEDS_HUMAN, UNMAPPED)

DRIFT_CATEGORIES = {
    "D1": "BOUNDARY_SHIFT",
    "D2": "DROPPED_RULE",
    "D3": "SCOPE_CREEP",
    "D4": "COMMENT_DECOY",
    "D5": "SEQUENCE_VIOLATION",
    "D6": "VALUE_CHANGE",
    "D7": "ERROR_HANDLING_DIVERGENCE",
    "D8": "OPERATOR_INVERSION",
    "D9": "SIDE_EFFECT_DRIFT",
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- spec side


@dataclass(frozen=True)
class Rule:
    id: str
    text: str
    section: str
    hash: str
    unverifiable: bool = False
    reason: str | None = None


# ---------------------------------------------------------------- code side


@dataclass(frozen=True)
class Chunk:
    id: str
    path: str
    line_start: int
    line_end: int
    kind: str  # function | method | class | constants
    name: str
    signature: str
    docstring: str | None
    source: str
    identifiers: tuple[str, ...]
    hash: str

    def numbered_source(self) -> str:
        """Source rendered with absolute line numbers so citations are checkable."""
        out = []
        for offset, line in enumerate(self.source.splitlines()):
            out.append(f"{self.line_start + offset:>4} | {line}")
        return "\n".join(out)


@dataclass(frozen=True)
class Candidate:
    chunk: Chunk
    score: float


# ---------------------------------------------------------------- results


@dataclass
class Evidence:
    path: str
    line_start: int
    line_end: int
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageInfo:
    duration_ms: int = 0
    top_score: float | None = None
    candidates: list[str] = field(default_factory=list)

    def to_dict(self, *, with_retrieval: bool) -> dict[str, Any]:
        d: dict[str, Any] = {"duration_ms": self.duration_ms}
        if with_retrieval:
            d["top_score"] = self.top_score
            d["candidates"] = self.candidates
        return d


@dataclass
class AdversaryInfo:
    ran: bool = False
    overturned: bool = False
    argument: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verdict:
    rule_id: str
    rule_text: str
    section: str
    verdict: str
    category: str | None = None
    confidence: float = 0.0
    cached: bool = False
    stage1: StageInfo = field(default_factory=StageInfo)
    stage2: StageInfo = field(default_factory=StageInfo)
    evidence: list[Evidence] = field(default_factory=list)
    reasoning: str = ""
    adversary: AdversaryInfo = field(default_factory=AdversaryInfo)
    pass_a_verdict: str | None = None
    pass_a_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_text": self.rule_text,
            "section": self.section,
            "verdict": self.verdict,
            "category": self.category,
            "category_name": DRIFT_CATEGORIES.get(self.category or ""),
            "confidence": round(self.confidence, 2),
            "cached": self.cached,
            "stage1": self.stage1.to_dict(with_retrieval=True),
            "stage2": self.stage2.to_dict(with_retrieval=False),
            "evidence": [e.to_dict() for e in self.evidence],
            "reasoning": self.reasoning,
            "adversary": self.adversary.to_dict(),
            "pass_a_verdict": self.pass_a_verdict,
            "pass_a_confidence": round(self.pass_a_confidence, 2),
        }

    # --- what the cache stores / restores -------------------------------

    def cacheable(self) -> dict[str, Any]:
        """Everything except run-local timings, which must not be cached."""
        d = self.to_dict()
        d["stage1"].pop("duration_ms", None)
        d["stage2"].pop("duration_ms", None)
        d.pop("cached", None)
        return d

    @classmethod
    def from_cache(cls, d: dict[str, Any]) -> "Verdict":
        v = cls(
            rule_id=d["rule_id"],
            rule_text=d["rule_text"],
            section=d["section"],
            verdict=d["verdict"],
            category=d.get("category"),
            confidence=d.get("confidence", 0.0),
            cached=True,
            reasoning=d.get("reasoning", ""),
            pass_a_verdict=d.get("pass_a_verdict"),
            pass_a_confidence=d.get("pass_a_confidence", 0.0),
        )
        v.stage1 = StageInfo(
            top_score=d.get("stage1", {}).get("top_score"),
            candidates=d.get("stage1", {}).get("candidates", []),
        )
        v.stage2 = StageInfo()
        v.evidence = [Evidence(**e) for e in d.get("evidence", [])]
        v.adversary = AdversaryInfo(**d.get("adversary", {}))
        return v

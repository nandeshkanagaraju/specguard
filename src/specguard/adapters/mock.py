"""MockProvider — the offline demo path.

This is not a stub that returns nonsense. It replays recorded model responses
keyed to the fixture, re-anchoring every citation against the prompt it is
actually answering. Anything it has not seen returns a conservative
NEEDS_HUMAN, because guessing is the failure mode this whole project is about.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..oracle import ORACLE_FILENAME, PromptView, entry_key, load_oracle, read_prompt

# A little latency so the dashboard's progressive repaint is visible on stage.
MIN_DELAY_S = 0.25
MAX_DELAY_S = 0.60

UNKNOWN_A = {
    "verdict": "NEEDS_HUMAN",
    "category": None,
    "confidence": 0.30,
    "evidence": [],
    "reasoning": (
        "No recorded judgement covers this rule against the code as it now stands. "
        "Routing to a human rather than guessing."
    ),
}

UNKNOWN_B = {
    "overturned": False,
    "argument": "No recorded counter-argument covers this rule and code.",
    "confidence": 0.30,
}


def _stable_delay(key: str) -> float:
    """Deterministic per-call delay: the demo must look alive but stay reproducible."""
    span = MAX_DELAY_S - MIN_DELAY_S
    bucket = int(key[:8], 16) / 0xFFFFFFFF
    return MIN_DELAY_S + span * bucket


class MockProvider:
    model_id = "mock-v1"

    def __init__(self, repo_root: Path, *, delay: bool = True) -> None:
        self.repo_root = Path(repo_root)
        # The synthetic latency is a demo affordance; CI and tests turn it off.
        self.delay = delay and os.environ.get("SPECGUARD_MOCK_DELAY", "1") != "0"
        self._data = load_oracle(self.repo_root / ORACLE_FILENAME)
        self._entries: list[dict[str, Any]] = self._data.get("entries", [])
        self._by_key = {e["key"]: e for e in self._entries if e.get("key")}
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------

    def complete(self, system: str, user: str, *, max_tokens: int = 900) -> str:
        view = read_prompt(user)
        key = entry_key(view.pass_name, user)

        if self.delay:
            time.sleep(_stable_delay(key))

        entry = self._by_key.get(key) or self._match_by_anchor(view, user)
        if entry is None:
            self.misses += 1
            return json.dumps(UNKNOWN_A if view.pass_name == "A" else UNKNOWN_B)

        materialised = self._materialise(entry, view)
        if materialised is None:
            self.misses += 1
            return json.dumps(UNKNOWN_A if view.pass_name == "A" else UNKNOWN_B)

        self.hits += 1
        return json.dumps(materialised)

    # ------------------------------------------------------------------

    def _match_by_anchor(self, view: PromptView, user: str) -> dict[str, Any] | None:
        """Fall back to a recorded response whose discriminators still hold.

        Two variants of the same file produce two recordings for the same rule;
        the discriminator — the line that differs between them — is what tells
        them apart when line numbers have shifted.
        """
        source = view.plain_source()
        best: dict[str, Any] | None = None
        best_specificity = -1
        for e in self._entries:
            if e.get("rule_id") != view.rule_id or e.get("pass") != view.pass_name:
                continue
            present = e.get("discriminators") or []
            absent = e.get("discriminators_absent") or []
            if not present and not absent:
                continue
            if not all(d in source for d in present):
                continue
            if any(d in source for d in absent):
                continue
            specificity = len(present) + len(absent)
            if specificity > best_specificity:
                best, best_specificity = e, specificity
        return best

    def _materialise(self, entry: dict[str, Any], view: PromptView) -> dict[str, Any] | None:
        """Re-resolve anchors into line numbers valid for this exact prompt."""
        response = json.loads(json.dumps(entry["response"]))  # deep copy
        if view.pass_name == "B":
            return response

        resolved = []
        for ev in response.get("evidence", []):
            path = ev.get("path", "")
            anchor = ev.get("anchor")
            if anchor is None:
                # A recording that already carries line numbers must still be
                # inside what this prompt shows.
                if view.covers(path, int(ev.get("line_start", 0)), int(ev.get("line_end", 0))):
                    resolved.append(ev)
                    continue
                return None
            span = view.resolve_anchor(path, anchor)
            if span is None:
                return None
            resolved.append({"path": path, "line_start": span[0], "line_end": span[1]})

        if response.get("verdict") == "DRIFTED" and not resolved:
            return None
        response["evidence"] = resolved
        return response

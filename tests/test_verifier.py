"""The guards that make a verdict trustworthy: evidence validation and retry."""

from __future__ import annotations

import json

import pytest

from specguard.adapters.base import parse_json_response
from specguard.indexer import index_repo
from specguard.models import DRIFTED, NEEDS_HUMAN, Candidate
from specguard.spec_parser import parse_spec
from specguard.verifier import EvidenceRejected, validate_evidence, verify


class ScriptedAdapter:
    """Returns canned replies in order, so a bad reply can be forced."""

    model_id = "scripted-v0"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system, user, *, max_tokens=900):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


@pytest.fixture
def r004(fixture_repo):
    root = fixture_repo("drifted")
    rule = next(r for r in parse_spec(root / "SPEC.md") if r.id == "R-004")
    chunk = next(c for c in index_repo(root) if c.name == "shipping_fee")
    return rule, [Candidate(chunk=chunk, score=0.57)]


def reply(**kw):
    payload = {
        "verdict": "DRIFTED", "category": "D1", "confidence": 0.9,
        "evidence": [{"path": "orderflow/shipping.py", "line_start": 13, "line_end": 14}],
        "reasoning": "…",
    }
    payload.update(kw)
    return json.dumps(payload)


# ------------------------------------------------------------ line validation


def test_evidence_outside_the_supplied_chunk_is_rejected(r004):
    rule, candidates = r004
    with pytest.raises(EvidenceRejected, match="outside every supplied chunk"):
        validate_evidence(
            [{"path": "orderflow/shipping.py", "line_start": 1, "line_end": 2}], candidates
        )


def test_evidence_for_an_unsupplied_file_is_rejected(r004):
    rule, candidates = r004
    with pytest.raises(EvidenceRejected, match="not supplied"):
        validate_evidence(
            [{"path": "orderflow/pricing.py", "line_start": 13, "line_end": 14}], candidates
        )


def test_evidence_inside_the_chunk_is_accepted_with_a_snippet(r004):
    rule, candidates = r004
    out = validate_evidence(
        [{"path": "orderflow/shipping.py", "line_start": 13, "line_end": 14}], candidates
    )
    assert len(out) == 1
    assert "subtotal > FREE_SHIPPING_THRESHOLD" in out[0].snippet


def test_a_hallucinated_citation_costs_the_whole_verdict(r004):
    """A model that cites a line it never saw gets one retry, then an abstention."""
    rule, candidates = r004
    adapter = ScriptedAdapter(
        reply(evidence=[{"path": "orderflow/shipping.py", "line_start": 900, "line_end": 901}])
    )
    result = verify(rule, candidates, adapter)
    assert adapter.calls == 2                     # retried once
    assert result.verdict == NEEDS_HUMAN
    assert "outside every supplied chunk" in (result.rejected or "")


def test_drift_without_evidence_is_not_a_drift_claim(r004):
    rule, candidates = r004
    adapter = ScriptedAdapter(reply(evidence=[]))
    result = verify(rule, candidates, adapter)
    assert result.verdict == NEEDS_HUMAN
    assert "DRIFTED with no evidence" in (result.rejected or "")


# ------------------------------------------------------------------- parsing


def test_retry_recovers_from_one_bad_reply(r004):
    rule, candidates = r004
    adapter = ScriptedAdapter("I think it looks fine, honestly.", reply())
    result = verify(rule, candidates, adapter)
    assert adapter.calls == 2
    assert result.verdict == DRIFTED
    assert result.category == "D1"


def test_unparseable_output_ends_in_abstention(r004):
    rule, candidates = r004
    adapter = ScriptedAdapter("no json here", "still no json")
    result = verify(rule, candidates, adapter)
    assert result.verdict == NEEDS_HUMAN
    assert result.confidence == 0.0


def test_code_fences_are_tolerated():
    assert parse_json_response('```json\n{"verdict":"ALIGNED"}\n```')["verdict"] == "ALIGNED"


def test_leading_prose_is_tolerated():
    assert parse_json_response('Here you go:\n{"verdict":"ALIGNED"}')["verdict"] == "ALIGNED"


def test_unknown_verdict_is_rejected(r004):
    rule, candidates = r004
    adapter = ScriptedAdapter(reply(verdict="PROBABLY_FINE"))
    assert verify(rule, candidates, adapter).verdict == NEEDS_HUMAN


def test_unknown_category_is_dropped_not_invented(r004):
    rule, candidates = r004
    adapter = ScriptedAdapter(reply(category="D42"))
    result = verify(rule, candidates, adapter)
    assert result.verdict == DRIFTED
    assert result.category == "D2"   # falls back to a real category, never "D42"


# ----------------------------------------------------------------- adversary


def test_adversary_does_not_run_on_an_abstention(fixture_repo, r004):
    from specguard.adversary import challenge

    rule, candidates = r004
    adapter = ScriptedAdapter('{"overturned":true,"argument":"x","confidence":0.9}')
    result = challenge(rule, candidates, NEEDS_HUMAN, "", adapter)
    assert result.ran is False
    assert adapter.calls == 0


def test_overturn_without_an_argument_is_not_an_overturn(r004):
    from specguard.adversary import challenge

    rule, candidates = r004
    adapter = ScriptedAdapter('{"overturned":true,"argument":"","confidence":0.9}')
    result = challenge(rule, candidates, DRIFTED, "", adapter)
    assert result.overturned is False


def test_a_broken_second_pass_does_not_silently_confirm(r004):
    from specguard.adversary import challenge

    rule, candidates = r004
    adapter = ScriptedAdapter("not json")
    result = challenge(rule, candidates, DRIFTED, "", adapter)
    assert result.ran is True
    assert result.overturned is False
    assert result.error
    assert result.confidence == 0.0

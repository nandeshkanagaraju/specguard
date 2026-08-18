"""Prompt templates. PROMPT_VERSION participates in the cache key: change a prompt,
invalidate every cached verdict."""

from __future__ import annotations

from .models import Candidate, Rule

PROMPT_VERSION = "pv1"

PASS_A_SYSTEM = """\
You are a specification-conformance checker. You decide whether a single
specification rule is satisfied by the code shown to you.

Rules of engagement:
- Judge ONLY the rule given. Ignore style, performance, naming, and any
  concern the rule does not state.
- Do not invent requirements. If the rule does not say it, it is not required.
- A claim of non-conformance MUST cite specific line numbers from the code
  provided. If you cannot cite lines, you do not have a finding.
- Comments and docstrings are not implementation. Judge executable code.
- If the code provided is insufficient to decide, say so with verdict
  NEEDS_HUMAN rather than guessing.

Reply with JSON only, no prose, no code fences:
{"verdict":"ALIGNED|DRIFTED|NEEDS_HUMAN",
 "category":"D1|D2|D3|D4|D5|D6|D7|D8|D9|null",
 "confidence":0.0-1.0,
 "evidence":[{"path":"...","line_start":int,"line_end":int}],
 "reasoning":"two sentences maximum"}"""

PASS_B_SYSTEM = """\
You are reviewing another checker's conformance verdict. Your job is to build
the strongest honest case that the verdict is WRONG, using only the rule and
the code provided.

If the verdict was DRIFTED, argue the code does satisfy the rule.
If the verdict was ALIGNED, argue the code does not satisfy the rule.

You must not invent requirements or speculate about code you cannot see.
If no honest counter-argument exists, say so - overturned: false. Failing to
overturn a correct verdict is a success, not a failure.

Reply with JSON only:
{"overturned":true|false,"argument":"two sentences maximum","confidence":0.0-1.0}"""


def _candidate_block(candidates: list[Candidate]) -> str:
    parts = []
    for c in candidates:
        ch = c.chunk
        parts.append(
            f"--- {ch.path} (lines {ch.line_start}-{ch.line_end}) ---\n"
            f"{ch.numbered_source()}\n"
            f"--- end ---"
        )
    return "\n".join(parts)


def pass_a_user(rule: Rule, candidates: list[Candidate]) -> str:
    return (
        f"RULE {rule.id} (section: {rule.section}):\n"
        f"{rule.text}\n\n"
        f"CANDIDATE CODE:\n"
        f"{_candidate_block(candidates)}\n"
    )


def pass_b_user(rule: Rule, candidates: list[Candidate], verdict: str, reasoning: str) -> str:
    return (
        f"RULE {rule.id} (section: {rule.section}):\n"
        f"{rule.text}\n\n"
        f"CANDIDATE CODE:\n"
        f"{_candidate_block(candidates)}\n\n"
        f"PRIOR VERDICT: {verdict}\n"
        f"PRIOR REASONING: {reasoning}\n"
    )

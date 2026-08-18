"""Stage 1 - retrieval.

The scorer is deliberately lexical: deterministic, explainable, and zero-dependency.
`Retriever` is the seam an embedding backend drops into for the Phase-2 ablation.
"""

from __future__ import annotations

import re
from typing import Protocol

from .models import Candidate, Chunk, Rule

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "below", "but", "by", "can",
    "contain", "containing", "does", "each", "every", "for", "from", "has", "have",
    "if", "in", "into", "is", "it", "its", "must", "no", "not", "of", "on", "one",
    "only", "or", "should", "so", "that", "the", "their", "then", "there", "these",
    "they", "this", "to", "under", "until", "up", "was", "were", "when", "which",
    "with", "within", "would", "any", "all", "shall", "will", "may", "after",
}

TOKEN_RE = re.compile(r"[A-Za-z]+|\d+(?:\.\d+)?")
CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def word_variants(word: str) -> set[str]:
    """The word plus a crude, deterministic stem.

    Deliberately not a Porter stemmer: a spec says "reserved" where the code says
    "reserve", and "qualifies" where the code says "qualify". Emitting both the
    surface form and one stem lets those meet without pulling in a dependency or
    an English model. Over-stemming is bounded because both sides are expanded
    the same way.
    """
    out = {word}
    if word.isdigit() or len(word) < 4:
        return out
    for suffix, rebuilds in (
        ("ies", ("y",)),
        ("sses", ("ss",)),
        ("ing", ("", "e")),
        ("ed", ("", "e")),
        ("es", ("", "e")),
        ("s", ("",)),
    ):
        if not word.endswith(suffix):
            continue
        base = word[: -len(suffix)]
        if len(base) < 3:
            break
        for tail in rebuilds:
            out.add(base + tail)
        break
    return out


def tokenize(text: str) -> set[str]:
    """Lowercased, stopword-stripped, snake/camel-split tokens plus stem variants."""
    if not text:
        return set()
    split = CAMEL_RE.sub(" ", text).replace("_", " ").replace(".", " ")
    out: set[str] = set()
    for raw in TOKEN_RE.findall(split):
        w = raw.lower()
        if w in STOPWORDS or len(w) < 2:
            continue
        out |= word_variants(w)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def numbers_in(text: str) -> set[str]:
    """Normalised numeric literals: 500, 500.0 and 500.00 are the same number."""
    out = set()
    for m in NUMBER_RE.findall(text):
        try:
            out.add(repr(float(m)))
        except ValueError:
            continue
    return out


def section_affinity(section: str, target: str) -> float:
    """How much the rule's section name shows up in the chunk's path and name."""
    s = tokenize(section)
    t = tokenize(target)
    if not s:
        return 0.0
    return len(s & t) / len(s)


def score_pair(rule: Rule, chunk: Chunk) -> float:
    rule_terms = tokenize(rule.text)

    ident_terms: set[str] = set()
    for ident in chunk.identifiers:
        ident_terms |= tokenize(ident)
    ident_terms |= tokenize(chunk.name)
    ident_terms |= tokenize(chunk.signature)

    doc_terms = tokenize(chunk.docstring or "")

    rule_nums = numbers_in(rule.text)
    chunk_nums = numbers_in(chunk.source)
    numeric = 1.0 if (rule_nums and rule_nums & chunk_nums) else 0.0

    return (
        0.45 * jaccard(rule_terms, ident_terms)
        + 0.25 * jaccard(rule_terms, doc_terms)
        + 0.20 * section_affinity(rule.section, f"{chunk.path} {chunk.name}")
        + 0.10 * numeric
    )


class Retriever(Protocol):
    def rank(self, rule: Rule, chunks: list[Chunk]) -> list[Candidate]: ...


class LexicalRetriever:
    def __init__(self, top_k: int = 3, floor: float = 0.15) -> None:
        self.top_k = top_k
        self.floor = floor

    def rank(self, rule: Rule, chunks: list[Chunk]) -> list[Candidate]:
        scored = [Candidate(chunk=c, score=round(score_pair(rule, c), 4)) for c in chunks]
        # Sort by score desc, then chunk id asc — ties must break deterministically.
        scored.sort(key=lambda c: (-c.score, c.chunk.id))
        return [c for c in scored[: self.top_k] if c.score >= self.floor]

    def top_score(self, rule: Rule, chunks: list[Chunk]) -> float:
        if not chunks:
            return 0.0
        return round(max(score_pair(rule, c) for c in chunks), 4)

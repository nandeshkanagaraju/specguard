"""Markdown spec -> numbered atomic rules.

Rules are authored as list items under `## <Section>` headings. IDs are assigned in
document order and are stable as long as rules are appended, not reordered.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Rule, sha256

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")

# Words that promise something without saying what would falsify it.
VAGUE_TERMS = (
    "fast",
    "user-friendly",
    "user friendly",
    "robust",
    "scalable",
    "as needed",
    "appropriate",
    "etc.",
)

COMPARISON_RE = re.compile(r"(>=|<=|==|!=|>|<|\bat least\b|\bat most\b|\bno more than\b|\bmore than\b|\bfewer than\b)")
NUMERAL_RE = re.compile(r"\d")
# A named identifier: snake_case, CamelCase, dotted path, or `backticked` token.
IDENTIFIER_RE = re.compile(r"`[^`]+`|\b[a-z]+_[a-z_]+\b|\b[A-Z][a-z]+[A-Z]\w*\b|\b\w+\.\w+\(\)")


def normalise(text: str) -> str:
    """Whitespace- and case-insensitive form used for the rule hash."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _vagueness_check(text: str) -> str | None:
    """Return a rejection reason, or None if the rule is verifiable.

    A rule is rejected only if it is vague AND carries no measurable predicate:
    no comparison operator, no numeral, and no named identifier.
    """
    low = text.lower()
    hits = [t for t in VAGUE_TERMS if t in low]
    if not hits:
        return None
    has_predicate = bool(
        COMPARISON_RE.search(low) or NUMERAL_RE.search(text) or IDENTIFIER_RE.search(text)
    )
    if has_predicate:
        return None
    return f"no measurable predicate; vague term(s): {', '.join(hits)}"


def parse_spec(spec_path: Path) -> list[Rule]:
    text = Path(spec_path).read_text(encoding="utf-8")
    rules: list[Rule] = []
    section = "General"
    in_rules_block = False
    fenced = False

    for raw in text.splitlines():
        if raw.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue

        m = HEADING_RE.match(raw)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if level <= 2:
                # `## Rules` switches collection on; any other h1/h2 names the section.
                if title.lower() == "rules":
                    in_rules_block = True
                else:
                    in_rules_block = False
                    section = title
            else:
                section = title
            continue

        item = LIST_ITEM_RE.match(raw)
        if not item:
            continue
        # Only collect list items that sit under a Rules block or a named section
        # that itself lives under one.
        body = item.group(1).strip()
        if not body or not _looks_like_rule(body):
            continue
        if not in_rules_block and section == "General":
            continue

        rid = f"R-{len(rules) + 1:03d}"
        reason = _vagueness_check(body)
        rules.append(
            Rule(
                id=rid,
                text=body,
                section=section,
                hash=sha256(normalise(body)),
                unverifiable=reason is not None,
                reason=reason,
            )
        )
    return rules


def _looks_like_rule(body: str) -> bool:
    """Filter out list items that are obviously not rules (links, TODOs, headers)."""
    if body.startswith("[") and body.endswith(")"):
        return False
    return len(body.split()) >= 3

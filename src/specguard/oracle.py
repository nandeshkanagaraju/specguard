"""Prompt introspection and the recorded-response oracle format.

The oracle is a cache of real model responses, not a hand-written fake. Its one
piece of cleverness is that evidence is stored as an *anchor* — the verbatim
source text the model cited — instead of a line number. Line numbers move when
an unrelated function above them changes; the cited text does not. On replay the
anchor is re-resolved against the prompt actually being answered, so a recorded
response is only ever reused when its citation is still checkable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import sha256

ORACLE_FILENAME = ".specguard_oracle.json"

RULE_RE = re.compile(r"^RULE (R-\d+)", re.MULTILINE)
BLOCK_RE = re.compile(r"^--- (?P<path>.+?) \(lines (?P<start>\d+)-(?P<end>\d+)\) ---$")
NUMBERED_RE = re.compile(r"^ *(\d+) \|(.*)$")


@dataclass
class PromptView:
    """What a prompt actually shows the model, indexed for lookup."""

    rule_id: str
    pass_name: str  # "A" | "B"
    files: dict[str, list[tuple[int, str]]]

    def plain_source(self) -> str:
        out = []
        for path in sorted(self.files):
            out.extend(text for _, text in self.files[path])
        return "\n".join(out)

    def line_range(self, path: str) -> tuple[int, int] | None:
        lines = self.files.get(path)
        if not lines:
            return None
        return lines[0][0], lines[-1][0]

    def covers(self, path: str, line_start: int, line_end: int) -> bool:
        lines = self.files.get(path)
        if not lines:
            return False
        shown = {n for n, _ in lines}
        return line_start in shown and line_end in shown and line_start <= line_end

    def resolve_anchor(self, path: str, anchor: str) -> tuple[int, int] | None:
        """Find the verbatim anchor text in the shown source; return its line span."""
        lines = self.files.get(path)
        if not lines:
            return None
        wanted = [w.rstrip() for w in anchor.rstrip("\n").split("\n")]
        if not wanted:
            return None
        have = [(n, t.rstrip()) for n, t in lines]
        for i in range(len(have) - len(wanted) + 1):
            if all(have[i + j][1] == wanted[j] for j in range(len(wanted))):
                return have[i][0], have[i + len(wanted) - 1][0]
        return None

    def snippet(self, path: str, line_start: int, line_end: int) -> str:
        lines = self.files.get(path, [])
        return "\n".join(t for n, t in lines if line_start <= n <= line_end)


def read_prompt(user: str) -> PromptView:
    """Reconstruct the code the prompt shows, from the prompt text itself.

    The adapters only ever receive strings, so the mock has to read the prompt
    the same way the model does. That is deliberate: it keeps MockProvider a
    genuine drop-in for a network backend rather than a privileged back door.
    """
    m = RULE_RE.search(user)
    rule_id = m.group(1) if m else "R-000"
    pass_name = "B" if "PRIOR VERDICT:" in user else "A"

    files: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    for raw in user.splitlines():
        block = BLOCK_RE.match(raw)
        if block:
            current = block.group("path")
            files.setdefault(current, [])
            continue
        if raw.startswith("--- end ---"):
            current = None
            continue
        if current is None:
            continue
        num = NUMBERED_RE.match(raw)
        if num:
            text = num.group(2)
            if text.startswith(" "):
                text = text[1:]
            files[current].append((int(num.group(1)), text))
    return PromptView(rule_id=rule_id, pass_name=pass_name, files=files)


def entry_key(pass_name: str, user: str) -> str:
    return sha256(f"{pass_name}|{user}")


# ------------------------------------------------------------------ storage


def load_oracle(path: Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"prompt_version": None, "entries": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_oracle(path: Path, data: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def to_anchored_evidence(view: PromptView, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn model-returned line numbers into replay-safe anchors."""
    out = []
    for e in evidence:
        path = e.get("path", "")
        start, end = int(e.get("line_start", 0)), int(e.get("line_end", 0))
        text = view.snippet(path, start, end)
        if not text:
            continue
        out.append({"path": path, "anchor": text})
    return out

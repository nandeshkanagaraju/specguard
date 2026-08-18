"""Content-addressed verdict cache — the determinism guarantee.

The key covers everything that can change an answer: the rule text, the exact
code that was shown, the model, and the prompt version. Nothing else. Timings
are stripped before storage so a cache hit and a cold run differ only in speed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Candidate, Rule, Verdict, sha256
from .prompts import PROMPT_VERSION


def cache_key(rule: Rule, candidates: list[Candidate], model_id: str) -> str:
    chunk_hashes = sorted(c.chunk.hash for c in candidates)
    return sha256(
        rule.hash + "|" + "|".join(chunk_hashes) + "|" + model_id + "|" + PROMPT_VERSION
    )


class VerdictCache:
    def __init__(self, directory: Path, enabled: bool = True) -> None:
        self.directory = Path(directory)
        self.enabled = enabled
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Verdict | None:
        if not self.enabled:
            return None
        path = self.directory / f"{key}.json"
        if not path.exists():
            self.misses += 1
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.misses += 1
            return None
        self.hits += 1
        return Verdict.from_cache(data)

    def put(self, key: str, verdict: Verdict) -> None:
        if not self.enabled:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{key}.json"
        path.write_text(
            json.dumps(verdict.cacheable(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

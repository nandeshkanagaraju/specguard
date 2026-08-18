"""The one interface every model backend implements."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol


class ModelError(RuntimeError):
    """The backend could not produce a completion."""


class ModelAdapter(Protocol):
    model_id: str

    def complete(self, system: str, user: str, *, max_tokens: int = 900) -> str: ...


FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def parse_json_response(text: str) -> dict[str, Any]:
    """Parse a model reply that is supposed to be a bare JSON object.

    Tolerates code fences and leading prose, because real models add them; raises
    ValueError if there is no object at all, which the Verifier turns into a retry.
    """
    cleaned = FENCE_RE.sub("", text).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in model response")
        obj = json.loads(cleaned[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("model response was not a JSON object")
    return obj

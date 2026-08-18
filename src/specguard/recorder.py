"""`specguard record-oracle` — turn a live model run into the offline oracle.

Every prompt and reply is captured, and the reply's line citations are rewritten
as verbatim source anchors before storage. That is what lets the recording
survive an unrelated edit above the cited code, and what lets the mock refuse to
replay a citation that no longer points at anything.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .adapters import build_adapter
from .adapters.base import ModelAdapter, parse_json_response
from .config import Config
from .oracle import ORACLE_FILENAME, entry_key, load_oracle, read_prompt, save_oracle, to_anchored_evidence
from .prompts import PROMPT_VERSION


class RecordingAdapter:
    """Wraps a real adapter and keeps every (prompt, reply) pair."""

    def __init__(self, inner: ModelAdapter) -> None:
        self.inner = inner
        self.model_id = inner.model_id
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, max_tokens: int = 900) -> str:
        reply = self.inner.complete(system, user, max_tokens=max_tokens)
        self.calls.append((user, reply))
        return reply


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    return out.stdout.strip()


def _entries_from_calls(calls: list[tuple[str, str]], variant: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for user, reply in calls:
        view = read_prompt(user)
        try:
            payload = parse_json_response(reply)
        except ValueError:
            continue

        if view.pass_name == "A":
            payload["evidence"] = to_anchored_evidence(view, payload.get("evidence") or [])
            discriminators = [
                e["anchor"].splitlines()[0]
                for e in payload["evidence"]
                if e.get("anchor")
            ]
        else:
            discriminators = []

        entries.append(
            {
                "key": entry_key(view.pass_name, user),
                "rule_id": view.rule_id,
                "pass": view.pass_name,
                "variant": variant,
                "discriminators": discriminators,
                "discriminators_absent": [],
                "response": payload,
            }
        )
    return entries


def record(
    cfg: Config,
    *,
    provider: str = "anthropic",
    tags: list[str] | None = None,
    console=None,
) -> Path:
    """Run the pipeline live (optionally across several git tags) and store the replies."""
    from .engine import run_check

    def say(msg: str) -> None:
        if console is not None:
            console.print(msg)

    out_path = cfg.root / ORACLE_FILENAME
    existing = load_oracle(out_path)
    by_key = {e["key"]: e for e in existing.get("entries", []) if e.get("key")}

    original_ref = None
    if tags:
        original_ref = _git(cfg.root, "rev-parse", "--abbrev-ref", "HEAD")
        if original_ref == "HEAD":
            original_ref = _git(cfg.root, "rev-parse", "HEAD")

    model_id = "unknown"
    try:
        for variant in tags or ["current"]:
            if tags:
                say(f"  recording [cyan]{variant}[/cyan]…")
                subprocess.run(
                    ["git", "-C", str(cfg.root), "checkout", "--quiet", variant],
                    check=True,
                )
            adapter = RecordingAdapter(build_adapter(cfg, provider))
            model_id = adapter.model_id
            run_check(cfg, provider=provider, use_cache=False, adapter=adapter)
            for entry in _entries_from_calls(adapter.calls, variant):
                by_key[entry["key"]] = entry
            say(f"    {len(adapter.calls)} model calls captured")
    finally:
        if original_ref:
            subprocess.run(
                ["git", "-C", str(cfg.root), "checkout", "--quiet", original_ref],
                check=False,
            )

    save_oracle(
        out_path,
        {
            "prompt_version": PROMPT_VERSION,
            "model_id": model_id,
            "source": f"recorded:{provider}",
            "note": (
                "Model replies captured from a live provider. Evidence is stored as "
                "verbatim source anchors and re-resolved at replay time."
            ),
            "entries": sorted(by_key.values(), key=lambda e: (e["rule_id"], e["pass"], e["variant"])),
        },
    )
    return out_path

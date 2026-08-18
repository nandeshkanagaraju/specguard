"""ReportBuilder — report.json, the summary table, and the exit code."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ALIGNED, DRIFTED, NEEDS_HUMAN, UNMAPPED, Rule, Verdict

SCHEMA_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_state(path: Path) -> dict[str, str]:
    def run(*args: str) -> str:
        try:
            out = subprocess.run(
                ["git", "-C", str(path), *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        # Detached — which is what `demo.sh` leaves us in. Prefer the tag name.
        branch = run("describe", "--tags", "--exact-match") or "detached"
    return {"commit": run("rev-parse", "--short", "HEAD"), "branch": branch}


def drift_score(summary: dict[str, int], verifiable: int) -> float:
    if verifiable <= 0:
        return 0.0
    raw = (summary["drifted"] + 0.5 * summary["needs_human"]) / verifiable
    return round(raw, 2)


def summarise(verdicts: list[Verdict]) -> dict[str, int]:
    return {
        "aligned": sum(1 for v in verdicts if v.verdict == ALIGNED),
        "drifted": sum(1 for v in verdicts if v.verdict == DRIFTED),
        "needs_human": sum(1 for v in verdicts if v.verdict == NEEDS_HUMAN),
        "unmapped": sum(1 for v in verdicts if v.verdict == UNMAPPED),
    }


def build_report(
    *,
    run_id: str,
    started_at: datetime,
    duration_ms: int,
    repo_path: Path,
    spec_path: str,
    rules: list[Rule],
    verdicts: list[Verdict],
    provider: str,
    model_id: str,
    prompt_version: str,
) -> dict[str, Any]:
    unverifiable = [r for r in rules if r.unverifiable]
    summary = summarise(verdicts)
    summary["drift_score"] = drift_score(summary, len(rules) - len(unverifiable))

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": iso(started_at),
        "duration_ms": duration_ms,
        "repo": {"path": str(repo_path), **git_state(repo_path)},
        "spec": {
            "path": spec_path,
            "rule_count": len(rules),
            "unverifiable_count": len(unverifiable),
        },
        "model": {
            "provider": provider,
            "model_id": model_id,
            "prompt_version": prompt_version,
        },
        "summary": summary,
        "unverifiable_rules": [
            {"id": r.id, "text": r.text, "section": r.section, "reason": r.reason}
            for r in unverifiable
        ],
        "verdicts": [v.to_dict() for v in verdicts],
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def exit_code(report: dict[str, Any], strict: bool = False) -> int:
    """Only real drift fails by default. --strict also fails on warnings."""
    s = report["summary"]
    if s["drifted"] > 0:
        return 1
    if strict and (s["needs_human"] > 0 or s["unmapped"] > 0):
        return 1
    return 0

"""Step-level instrumentation for the eight-step pipeline.

Report Figure 3 names eight steps. This module makes each of them observable
while a run is in flight, so a failure can be attributed to a step instead of
just surfacing as a bad verdict. The tracker is the single source of truth for
both the live SSE `step` events and the `pipeline` block stored in report.json,
which is why the dashboard can draw the same timeline from a finished report as
it does from a live run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

# status values, in order of severity
PENDING = "pending"
RUNNING = "running"
OK = "ok"
WARN = "warn"
FAILED = "failed"

STEP_DEFS: list[tuple[int, str, str, str]] = [
    (1, "parse", "Parse spec", "Markdown into numbered atomic rules"),
    (2, "index", "Index code", "AST chunks: functions, methods, classes, constants"),
    (3, "retrieve", "Retrieve candidates", "Stage 1 — rule to code, top-k above the floor"),
    (4, "cache", "Cache lookup", "Content-addressed verdicts from earlier runs"),
    (5, "verify", "Verify · pass A", "Stage 2 — evidence-citing conformance judgement"),
    (6, "adversary", "Adversary · pass B", "The opposing brief against pass A"),
    (7, "score", "Score & abstain", "Confidence, disagreement, NEEDS_HUMAN"),
    (8, "report", "Build report", "report.json, summary table, exit code"),
]


@dataclass
class Step:
    n: int
    key: str
    label: str
    hint: str
    status: str = PENDING
    done: int = 0
    total: int = 0
    duration_ms: int = 0
    detail: str = ""
    failures: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "key": self.key,
            "label": self.label,
            "hint": self.hint,
            "status": self.status,
            "done": self.done,
            "total": self.total,
            "duration_ms": self.duration_ms,
            "detail": self.detail,
            "failures": self.failures,
        }


class StepTracker:
    """Accumulates per-step state and pushes it out as it changes.

    Steps 3-7 run once per rule, so their timers accumulate rather than span a
    single interval; `done/total` is what makes progress legible while they do.
    """

    def __init__(self, emit: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self.steps: dict[str, Step] = {
            key: Step(n=n, key=key, label=label, hint=hint)
            for n, key, label, hint in STEP_DEFS
        }
        self._emit = emit or (lambda event, data: None)
        self._marks: dict[str, float] = {}

    # ---------------------------------------------------------------- API

    def begin(self, key: str, total: int = 0, detail: str = "") -> None:
        step = self.steps[key]
        if step.status == PENDING:
            step.status = RUNNING
        if total:
            step.total = total
        if detail:
            step.detail = detail
        self._marks[key] = time.perf_counter()
        self.push(key)

    def mark(self, key: str) -> None:
        """Start the stopwatch for one slice of an accumulating step."""
        self._marks[key] = time.perf_counter()
        step = self.steps[key]
        if step.status == PENDING:
            step.status = RUNNING
            self.push(key)

    def stop(self, key: str) -> int:
        started = self._marks.pop(key, None)
        if started is None:
            return 0
        elapsed = int((time.perf_counter() - started) * 1000)
        self.steps[key].duration_ms += elapsed
        return elapsed

    def tick(self, key: str, *, detail: str = "", push: bool = True) -> None:
        step = self.steps[key]
        step.done += 1
        if detail:
            step.detail = detail
        if push:
            self.push(key)

    def warn(self, key: str, rule_id: str, message: str) -> None:
        step = self.steps[key]
        step.failures.append({"rule_id": rule_id, "message": message, "level": "warn"})
        if step.status != FAILED:
            step.status = WARN
        self.push(key)

    def fail(self, key: str, rule_id: str, message: str) -> None:
        step = self.steps[key]
        step.failures.append({"rule_id": rule_id, "message": message, "level": "error"})
        step.status = FAILED
        self.push(key)

    def finish(self, key: str, detail: str = "") -> None:
        step = self.steps[key]
        if detail:
            step.detail = detail
        if step.status in (PENDING, RUNNING):
            step.status = OK
        self.push(key)

    def finish_all(self) -> None:
        for step in self.steps.values():
            if step.status in (PENDING, RUNNING):
                step.status = OK
            self.push(step.key)

    # -------------------------------------------------------------- output

    def push(self, key: str) -> None:
        self._emit("step", self.steps[key].to_dict())

    def to_list(self) -> list[dict[str, Any]]:
        return [self.steps[key].to_dict() for _, key, _, _ in STEP_DEFS]

    @property
    def failed_step(self) -> Step | None:
        for _, key, _, _ in STEP_DEFS:
            if self.steps[key].status == FAILED:
                return self.steps[key]
        return None

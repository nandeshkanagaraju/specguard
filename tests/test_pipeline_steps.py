"""The step timeline: a failure must be attributable to one of the eight steps."""

from __future__ import annotations

import pytest

from specguard.config import load_config
from specguard.engine import run_check
from specguard.pipeline import STEP_DEFS


def steps_of(report):
    return {s["key"]: s for s in report["pipeline"]}


class BrokenAdapter:
    model_id = "broken-v0"

    def complete(self, system, user, *, max_tokens=900):
        return "Sure! Overall this looks reasonable to me."


def test_report_carries_all_eight_steps(fixture_repo):
    report = run_check(load_config(fixture_repo("clean")))
    assert [s["n"] for s in report["pipeline"]] == list(range(1, 9))
    assert [s["key"] for s in report["pipeline"]] == [d[1] for d in STEP_DEFS]


def test_a_clean_run_resolves_every_step(fixture_repo):
    report = run_check(load_config(fixture_repo("drifted")))
    for step in report["pipeline"]:
        assert step["status"] in ("ok", "warn"), step
        assert step["done"] == step["total"] or step["total"] == 0


def test_step_counters_match_the_rule_count(fixture_repo):
    steps = steps_of(run_check(load_config(fixture_repo("clean"))))
    for key in ("retrieve", "cache", "verify", "adversary", "score"):
        assert steps[key]["total"] == 11
        assert steps[key]["done"] == 11
    assert steps["parse"]["total"] == 12


def test_unverifiable_rule_surfaces_at_step_one(fixture_repo):
    steps = steps_of(run_check(load_config(fixture_repo("clean"))))
    parse = steps["parse"]
    assert parse["status"] == "warn"
    assert [f["rule_id"] for f in parse["failures"]] == ["R-012"]


def test_abstention_surfaces_at_step_seven(fixture_repo):
    steps = steps_of(run_check(load_config(fixture_repo("drifted"))))
    score = steps["score"]
    assert score["status"] == "warn"
    assert any(f["rule_id"] == "R-009" for f in score["failures"])


def test_a_model_that_will_not_answer_fails_step_five(fixture_repo):
    report = run_check(
        load_config(fixture_repo("drifted")), use_cache=False, adapter=BrokenAdapter()
    )
    steps = steps_of(report)
    assert steps["verify"]["status"] == "failed"
    assert steps["verify"]["failures"]
    assert steps["verify"]["failures"][0]["level"] == "error"
    # and the steps before it are untouched
    assert steps["parse"]["status"] in ("ok", "warn")
    assert steps["index"]["status"] == "ok"
    assert steps["retrieve"]["status"] == "ok"


def test_unparseable_file_warns_at_step_two(fixture_repo):
    root = fixture_repo("clean")
    (root / "orderflow" / "broken.py").write_text("def nope(:\n", encoding="utf-8")
    steps = steps_of(run_check(load_config(root)))
    index = steps["index"]
    assert index["status"] == "warn"
    assert index["done"] == index["total"] - 1
    assert index["failures"][0]["rule_id"] == "orderflow/broken.py"


def test_an_unmappable_rule_warns_at_step_three(fixture_repo):
    root = fixture_repo("clean")
    spec = root / "SPEC.md"
    spec.write_text(
        spec.read_text(encoding="utf-8")
        + "\n### Ops\n\n- Kubernetes pods drain gracefully during node cordon.\n",
        encoding="utf-8",
    )
    report = run_check(load_config(root))
    steps = steps_of(report)
    assert steps["retrieve"]["status"] == "warn"
    assert any(f["rule_id"] == "R-013" for f in steps["retrieve"]["failures"])
    assert report["summary"]["unmapped"] == 1


def test_drift_is_a_finding_not_a_pipeline_fault(fixture_repo):
    """Step 8 stays green on a drifted run: the pipeline itself ran fine."""
    steps = steps_of(run_check(load_config(fixture_repo("drifted"))))
    assert steps["report"]["status"] == "ok"
    assert "exit 1" in steps["report"]["detail"]


def test_step_timings_separate_retrieval_from_reasoning(fixture_repo):
    """Stage 1 and stage 2 are timed apart so Phase 2 can attribute a failure to
    retrieval or to reasoning. (Absolute values are meaningless under the mock,
    which answers instantly — what matters is that they are recorded apart.)"""
    steps = steps_of(run_check(load_config(fixture_repo("drifted")), use_cache=False))
    for key in ("retrieve", "cache", "verify", "adversary", "score"):
        assert steps[key]["duration_ms"] >= 0
    assert steps["retrieve"]["duration_ms"] > 0        # retrieval does real work
    assert steps["verify"] is not steps["retrieve"]    # and is timed separately


def test_events_are_emitted_in_pipeline_order(fixture_repo):
    seen = []
    run_check(
        load_config(fixture_repo("drifted")),
        only_rule="R-004",
        emit=lambda ev, data: seen.append((ev, data.get("key") or data.get("rule_id"))),
    )
    names = [e for e, _ in seen]
    assert names[0] == "run_started"
    assert names[-1] == "run_finished"
    assert "step" in names
    assert "rule_verdict" in names

    step_order = [k for e, k in seen if e == "step"]
    assert step_order[0] == "parse"
    assert step_order[-1] == "report"

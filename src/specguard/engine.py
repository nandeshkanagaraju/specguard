"""The eight-step pipeline. This is the only place the stages are wired together.

Each step reports into a StepTracker as it runs, so a failure is attributable to
a step rather than just showing up as a bad verdict at the end.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .adapters import ModelAdapter, build_adapter
from .adversary import PassB, challenge
from .cache import VerdictCache, cache_key
from .config import Config
from .indexer import index_repo_verbose
from .models import (
    DRIFTED,
    NEEDS_HUMAN,
    UNMAPPED,
    Candidate,
    Chunk,
    Rule,
    StageInfo,
    Verdict,
    sha256,
)
from .pipeline import StepTracker
from .prompts import PROMPT_VERSION
from .report import build_report, iso, utc_now
from .retriever import LexicalRetriever
from .scoring import decide
from .spec_parser import parse_spec
from .verifier import PassA, verify

Emit = Callable[[str, dict[str, Any]], None]


def _noop(event: str, data: dict[str, Any]) -> None:  # pragma: no cover - default
    pass


def make_run_id(started) -> str:
    stamp = iso(started)
    return f"{stamp}-{sha256(stamp)[:4]}"


def _unmapped_verdict(rule: Rule, top_score: float, stage1_ms: int) -> Verdict:
    v = Verdict(
        rule_id=rule.id,
        rule_text=rule.text,
        section=rule.section,
        verdict=UNMAPPED,
        confidence=0.0,
        reasoning=(
            "No code chunk scored above the retrieval floor for this rule, so no "
            "verification was attempted. Either the behaviour is not implemented or "
            "the rule's wording shares no vocabulary with the code."
        ),
    )
    v.stage1 = StageInfo(duration_ms=stage1_ms, top_score=top_score, candidates=[])
    return v


def check_rule(
    rule: Rule,
    chunks: list[Chunk],
    retriever: LexicalRetriever,
    adapter: ModelAdapter,
    cache: VerdictCache,
    cfg: Config,
    steps: StepTracker,
) -> Verdict:
    """Steps 3-7 for a single rule."""
    # --- 3. retrieve ------------------------------------------------------
    steps.mark("retrieve")
    candidates: list[Candidate] = retriever.rank(rule, chunks)
    top_score = retriever.top_score(rule, chunks)
    stage1_ms = steps.stop("retrieve")
    steps.tick("retrieve", detail=f"{rule.id} → {len(candidates)} candidates")

    if not candidates:
        steps.warn("retrieve", rule.id, f"no chunk cleared the retrieval floor (best {top_score:.3f})")
        for key in ("cache", "verify", "adversary", "score"):
            steps.tick(key, detail=f"{rule.id} skipped — nothing retrieved")
        return _unmapped_verdict(rule, top_score, stage1_ms)

    stage1 = StageInfo(
        duration_ms=stage1_ms,
        top_score=candidates[0].score,
        candidates=[c.chunk.id for c in candidates],
    )

    # --- 4. cache ---------------------------------------------------------
    steps.mark("cache")
    key = cache_key(rule, candidates, adapter.model_id)
    cached = cache.get(key)
    steps.stop("cache")
    steps.tick(
        "cache",
        detail=f"{cache.hits} hit{'' if cache.hits == 1 else 's'}, {cache.misses} miss"
        f"{'' if cache.misses == 1 else 'es'}",
    )
    if cached is not None:
        cached.stage1.duration_ms = stage1_ms
        for k in ("verify", "adversary", "score"):
            steps.tick(k, detail=f"{rule.id} served from cache")
        return cached

    # --- 5. verify (pass A) ----------------------------------------------
    steps.mark("verify")
    pass_a: PassA = verify(rule, candidates, adapter)
    steps.stop("verify")
    if pass_a.rejected:
        steps.fail("verify", rule.id, f"no usable verdict after a retry — {pass_a.rejected}")
    steps.tick("verify", detail=f"{rule.id} → {pass_a.verdict}")

    # --- 6. adversary (pass B) -------------------------------------------
    steps.mark("adversary")
    pass_b: PassB = challenge(rule, candidates, pass_a.verdict, pass_a.reasoning, adapter)
    stage2_ms = steps.stop("adversary")
    if pass_b.error:
        steps.fail("adversary", rule.id, f"second pass unusable — {pass_b.error}")
    steps.tick(
        "adversary",
        detail=f"{rule.id} → {'overturned' if pass_b.overturned else 'not overturned'}"
        if pass_b.ran
        else f"{rule.id} → not applicable",
    )

    # --- 7. score & abstain ----------------------------------------------
    steps.mark("score")
    final, confidence, abstain_reason = decide(
        pass_a, pass_b, stage1.top_score or 0.0, cfg.abstain_below
    )
    steps.stop("score")
    if final == NEEDS_HUMAN:
        steps.warn("score", rule.id, abstain_reason or "routed to a human")
    steps.tick("score", detail=f"{rule.id} → {final} @ {confidence:.2f}")

    reasoning = pass_a.reasoning
    if final == NEEDS_HUMAN and abstain_reason:
        reasoning = f"{reasoning} Routed to a human because {abstain_reason}.".strip()

    verdict = Verdict(
        rule_id=rule.id,
        rule_text=rule.text,
        section=rule.section,
        verdict=final,
        category=pass_a.category if final == pass_a.verdict else None,
        confidence=confidence,
        cached=False,
        evidence=pass_a.evidence,
        reasoning=reasoning,
        pass_a_verdict=pass_a.verdict,
        pass_a_confidence=pass_a.confidence,
    )
    verdict.stage1 = stage1
    verdict.stage2 = StageInfo(duration_ms=stage2_ms)
    verdict.adversary.ran = pass_b.ran
    verdict.adversary.overturned = pass_b.overturned
    verdict.adversary.argument = pass_b.argument
    verdict.adversary.confidence = pass_b.confidence

    cache.put(key, verdict)
    return verdict


def run_check(
    cfg: Config,
    *,
    provider: str | None = None,
    use_cache: bool = True,
    only_rule: str | None = None,
    emit: Emit = _noop,
    adapter: ModelAdapter | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run the whole pipeline and return the report dict."""
    started = utc_now()
    t_start = time.perf_counter()
    rid = run_id or make_run_id(started)
    steps = StepTracker(emit)

    emit("run_started", {"run_id": rid, "steps": steps.to_list()})

    # --- 1. parse the spec ------------------------------------------------
    steps.begin("parse")
    spec_file = cfg.root / cfg.spec_path
    try:
        rules = parse_spec(spec_file)
    except OSError as exc:
        steps.fail("parse", "", f"could not read {cfg.spec_path}: {exc}")
        raise
    if only_rule:
        wanted = {r.strip().upper() for r in only_rule.split(",")}
        rules = [r for r in rules if r.id in wanted]
    steps.stop("parse")

    unverifiable = [r for r in rules if r.unverifiable]
    checkable = [r for r in rules if not r.unverifiable]
    steps.steps["parse"].total = len(rules)
    steps.steps["parse"].done = len(rules)
    for r in unverifiable:
        steps.warn("parse", r.id, r.reason or "not verifiable")
    if not rules:
        steps.fail("parse", "", f"no rules found in {cfg.spec_path}")
    steps.finish(
        "parse",
        f"{len(rules)} rule{'' if len(rules) == 1 else 's'}"
        + (f", {len(unverifiable)} unverifiable" if unverifiable else ""),
    )

    # --- 2. index the code ------------------------------------------------
    steps.begin("index")
    chunks, unreadable, file_count = index_repo_verbose(cfg.root)
    steps.stop("index")
    steps.steps["index"].total = file_count
    steps.steps["index"].done = file_count - len(unreadable)
    for path in unreadable:
        steps.warn("index", path, "could not be parsed; its code was not considered")
    if not chunks:
        steps.fail("index", "", "no Python code was indexed — check .specguardignore")
    steps.finish("index", f"{len(chunks)} chunks across {file_count} files")

    retriever = LexicalRetriever(top_k=cfg.top_k, floor=cfg.floor)
    model = adapter or build_adapter(cfg, provider)
    cache = VerdictCache(cfg.cache_dir, enabled=use_cache)

    for key in ("retrieve", "cache", "verify", "adversary", "score"):
        steps.steps[key].total = len(checkable)
        steps.push(key)

    emit(
        "run_ready",
        {
            "run_id": rid,
            "rule_count": len(checkable),
            "total_rules": len(rules),
            "chunk_count": len(chunks),
        },
    )

    # --- 3-7. per rule ----------------------------------------------------
    verdicts: list[Verdict] = []
    for rule in checkable:
        emit("rule_started", {"rule_id": rule.id, "rule_text": rule.text})
        verdict = check_rule(rule, chunks, retriever, model, cache, cfg, steps)
        verdicts.append(verdict)
        emit("rule_verdict", verdict.to_dict())

    for key in ("retrieve", "cache", "verify", "adversary", "score"):
        steps.finish(key)
    if not use_cache:
        steps.steps["cache"].detail = "bypassed with --no-cache"
        steps.push("cache")

    # --- 8. build the report ----------------------------------------------
    steps.begin("report")
    duration_ms = int((time.perf_counter() - t_start) * 1000)
    report = build_report(
        run_id=rid,
        started_at=started,
        duration_ms=duration_ms,
        repo_path=cfg.root,
        spec_path=cfg.spec_path,
        rules=rules,
        verdicts=verdicts,
        provider=(provider or cfg.model.provider),
        model_id=model.model_id,
        prompt_version=PROMPT_VERSION,
    )
    report["cache"] = {"hits": cache.hits, "misses": cache.misses, "enabled": use_cache}
    steps.stop("report")
    # Drift is a finding, not a pipeline fault: the timeline reports on how the
    # run executed, and a clean execution that found drift is still a clean run.
    s = report["summary"]
    steps.finish("report", f"drift score {s['drift_score']:.2f} · exit {1 if s['drifted'] else 0}")

    report["pipeline"] = steps.to_list()
    emit("run_finished", {"run_id": rid, **s, "duration_ms": duration_ms, "steps": report["pipeline"]})
    return report

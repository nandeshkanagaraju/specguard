/* SpecGuard dashboard.
   No framework, no build step: one file that reads /api and repaints. */

(() => {
  "use strict";

  const LABEL = {
    ALIGNED: "Aligned",
    DRIFTED: "Drifted",
    NEEDS_HUMAN: "Needs human",
    UNMAPPED: "Unmapped",
    UNVERIFIABLE: "Unverifiable",
    PENDING: "Waiting",
    RUNNING: "Checking",
  };

  const CATEGORY = {
    D1: "Boundary shift", D2: "Dropped rule", D3: "Scope creep",
    D4: "Comment decoy", D5: "Sequence violation", D6: "Value change",
    D7: "Error handling divergence", D8: "Operator inversion",
    D9: "Side effect drift",
  };

  /* The eight steps of report Figure 3, in order. The server sends the same
     list — this is only the fallback shape before the first run. */
  const STEP_DEFS = [
    ["parse", "Parse spec", "Markdown into numbered atomic rules"],
    ["index", "Index code", "AST chunks: functions, methods, classes, constants"],
    ["retrieve", "Retrieve candidates", "Stage 1 — rule to code, top-k above the floor"],
    ["cache", "Cache lookup", "Content-addressed verdicts from earlier runs"],
    ["verify", "Verify · pass A", "Stage 2 — evidence-citing conformance judgement"],
    ["adversary", "Adversary · pass B", "The opposing brief against pass A"],
    ["score", "Score & abstain", "Confidence, disagreement, NEEDS_HUMAN"],
    ["report", "Build report", "report.json, summary table, exit code"],
  ];

  const GLYPH = { ok: "✓", warn: "!", failed: "✕" };

  const el = (id) => document.getElementById(id);
  const $ribbon = el("ribbon"), $ruleList = el("ruleList"), $evidence = el("evidence");
  const $toasts = el("toasts"), $runBtn = el("runBtn"), $conn = el("conn");
  const $connText = el("connText"), $repo = el("repo"), $pane = el("evidencePane");
  const $flow = el("flow"), $flowOutcome = el("flowOutcome"), $flowClock = el("flowClock");

  const state = {
    order: [],          // rule ids in document order
    rules: new Map(),   // rule id -> verdict-ish object
    filter: "all",
    selected: null,
    running: false,
    repo: null,
    steps: new Map(),   // step key -> step object
    startedAt: null,
    clock: null,
  };

  const escape = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const fileOf = (p) => String(p || "").split("/").pop();

  // ------------------------------------------------------------ loading

  async function boot() {
    await loadRepo();
    const res = await fetch("/api/report");
    const report = await res.json();
    if (report.status === "empty") {
      renderEmpty();
    } else {
      ingest(report);
      render();
    }
    connect();
  }

  async function loadRepo() {
    try {
      const r = await fetch("/api/repo/state");
      state.repo = await r.json();
      $repo.textContent =
        `${state.repo.name} · ${state.repo.branch || "—"} · ${state.repo.commit || "no commit"}`;
    } catch {
      $repo.textContent = "repository unavailable";
    }
  }

  function ingest(report) {
    state.report = report;
    ingestSteps(report.pipeline);
    state.rules.clear();
    const rows = [];
    (report.verdicts || []).forEach((v) => rows.push(v));
    (report.unverifiable_rules || []).forEach((u) =>
      rows.push({
        rule_id: u.id, rule_text: u.text, section: u.section,
        verdict: "UNVERIFIABLE", reason: u.reason, evidence: [], confidence: 0,
        adversary: {}, stage1: {}, stage2: {},
      }));
    rows.sort((a, b) => a.rule_id.localeCompare(b.rule_id));
    state.order = rows.map((r) => r.rule_id);
    rows.forEach((r) => state.rules.set(r.rule_id, r));
  }

  // ------------------------------------------------------------- render

  function render() {
    renderStats();
    renderRibbon();
    renderList();
    renderFlow();
    if (state.selected && state.rules.has(state.selected)) showRule(state.selected);
    else renderEvidencePlaceholder();
  }

  function renderEmpty() {
    $ribbon.innerHTML = "";
    $ruleList.innerHTML =
      `<div class="empty">No check has run yet.<br>Click <b>Run check</b> to read the spec and the code.</div>`;
    $evidence.innerHTML =
      `<div class="empty">Evidence appears here once a rule has a verdict.</div>`;
    ingestSteps(null);
    renderFlow();
  }

  // ------------------------------------------------- pipeline timeline

  function ingestSteps(list) {
    state.steps.clear();
    if (list && list.length) {
      list.forEach((s) => state.steps.set(s.key, s));
      return;
    }
    STEP_DEFS.forEach(([key, label, hint], i) =>
      state.steps.set(key, {
        n: i + 1, key, label, hint, status: "pending",
        done: 0, total: 0, duration_ms: 0, detail: "", failures: [],
      }));
  }

  function resetSteps() {
    state.steps.forEach((s) => {
      s.status = "pending"; s.done = 0; s.duration_ms = 0;
      s.detail = ""; s.failures = [];
    });
    renderFlow();
  }

  function ms(v) {
    if (!v) return "";
    return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;
  }

  function renderFlow() {
    $flow.innerHTML = "";
    STEP_DEFS.forEach(([key]) => {
      const s = state.steps.get(key);
      if (!s) return;

      const li = document.createElement("li");
      li.className = "flow__step";
      li.dataset.s = s.status;
      li.dataset.key = key;

      const pct = s.total ? Math.round((s.done / s.total) * 100)
        : (s.status === "pending" ? 0 : 100);

      const counter = s.total ? `${s.done}/${s.total}` : ms(s.duration_ms);
      const timing = s.total && s.duration_ms ? ` · ${ms(s.duration_ms)}` : "";

      const issues = (s.failures || []).slice(0, 3).map((f) =>
        `<li data-level="${escape(f.level)}">${f.rule_id ? `<b>${escape(f.rule_id)}</b> ` : ""}${escape(f.message)}</li>`
      ).join("");
      const more = (s.failures || []).length > 3
        ? `<div class="flow__more">+${s.failures.length - 3} more</div>` : "";

      li.innerHTML = `
        <span class="flow__marker" aria-hidden="true">${
          GLYPH[s.status] ? `<span class="flow__glyph">${GLYPH[s.status]}</span>` : s.n
        }</span>
        <div class="flow__body">
          <div class="flow__label">
            <span>${escape(s.label)}</span>
            <span class="flow__count">${escape(counter)}${escape(timing)}</span>
          </div>
          <div class="flow__detail" title="${escape(s.detail || s.hint)}">${escape(s.detail || s.hint)}</div>
          ${s.total ? `<div class="flow__bar"><i style="width:${pct}%"></i></div>` : ""}
          ${issues ? `<ul class="flow__issues">${issues}</ul>${more}` : ""}
        </div>`;

      li.setAttribute("aria-label",
        `Step ${s.n}, ${s.label}: ${s.status}${s.detail ? ". " + s.detail : ""}`);
      $flow.appendChild(li);
    });
    renderOutcome();
  }

  function renderOutcome() {
    const steps = STEP_DEFS.map(([k]) => state.steps.get(k)).filter(Boolean);
    if (!steps.length) return;

    const failed = steps.find((s) => s.status === "failed");
    const running = steps.find((s) => s.status === "running");
    const warned = steps.filter((s) => s.status === "warn");
    const done = steps.filter((s) => s.status !== "pending" && s.status !== "running").length;

    if (failed) {
      $flowOutcome.dataset.s = "failed";
      $flowOutcome.innerHTML =
        `<b>Failed at step ${failed.n} · ${escape(failed.label)}</b>` +
        escape(failed.failures[0] ? failed.failures[0].message : "See the terminal for detail.");
      return;
    }
    if (running) {
      $flowOutcome.dataset.s = "running";
      $flowOutcome.innerHTML =
        `<b>Step ${running.n} of 8 · ${escape(running.label)}</b>` +
        `${done} step${done === 1 ? "" : "s"} complete.`;
      return;
    }
    if (!done) {
      $flowOutcome.dataset.s = "idle";
      $flowOutcome.textContent = "No run yet.";
      return;
    }
    if (warned.length) {
      const total = warned.reduce((n, s) => n + s.failures.length, 0);
      $flowOutcome.dataset.s = "warn";
      $flowOutcome.innerHTML =
        `<b>All 8 steps completed</b>` +
        `${total} thing${total === 1 ? "" : "s"} needed attention, at step${warned.length === 1 ? "" : "s"} ` +
        warned.map((s) => s.n).join(", ") + ".";
      return;
    }
    $flowOutcome.dataset.s = "ok";
    $flowOutcome.innerHTML = `<b>All 8 steps completed</b>Every step of the pipeline ran clean.`;
  }

  function startClock() {
    state.startedAt = Date.now();
    clearInterval(state.clock);
    state.clock = setInterval(() => {
      $flowClock.textContent = `${((Date.now() - state.startedAt) / 1000).toFixed(1)}s`;
    }, 100);
  }

  function stopClock(finalMs) {
    clearInterval(state.clock);
    state.clock = null;
    if (finalMs != null) $flowClock.textContent = `${(finalMs / 1000).toFixed(1)}s`;
  }

  function renderStats() {
    const r = state.report;
    if (!r) return;
    const s = r.summary || {};
    el("statScore").textContent = (s.drift_score ?? 0).toFixed(2);
    el("statAligned").textContent = s.aligned ?? 0;
    el("statDrifted").textContent = s.drifted ?? 0;
    el("statHuman").textContent = s.needs_human ?? 0;
    el("statUnmapped").textContent = s.unmapped ?? 0;
    const m = r.model || {};
    const cache = r.cache && r.cache.hits ? ` · ${r.cache.hits} cached` : "";
    el("statModel").textContent =
      `${m.provider || "—"} · ${m.model_id || "—"} · ${m.prompt_version || "—"}${cache}`;
  }

  function renderRibbon() {
    $ribbon.innerHTML = "";
    state.order.forEach((id) => {
      const rule = state.rules.get(id);
      const tick = document.createElement("button");
      tick.type = "button";
      tick.className = "tick";
      tick.dataset.v = rule.verdict;
      tick.dataset.id = id;
      tick.setAttribute("aria-label", `${id}: ${LABEL[rule.verdict] || rule.verdict}`);
      tick.innerHTML =
        `<span class="tick__tip"><b>${escape(id)} · ${LABEL[rule.verdict] || rule.verdict}</b>${escape(rule.rule_text || "")}</span>`;
      tick.addEventListener("click", () => selectRule(id, { scroll: true }));
      $ribbon.appendChild(tick);
    });
    markSelection();
  }

  function meter(conf) {
    const on = Math.round((conf || 0) * 9);
    let out = '<span class="meter" aria-hidden="true">';
    for (let i = 0; i < 9; i++) out += `<i class="${i < on ? "on" : ""}"></i>`;
    return out + "</span>";
  }

  function renderList() {
    $ruleList.innerHTML = "";
    const shown = state.order.filter((id) => {
      if (state.filter === "all") return true;
      return state.rules.get(id).verdict === state.filter;
    });

    if (!shown.length) {
      $ruleList.innerHTML = `<div class="empty">No rules match this filter.</div>`;
      return;
    }

    shown.forEach((id) => {
      const r = state.rules.get(id);
      const card = document.createElement("button");
      card.type = "button";
      card.className = "card";
      card.dataset.v = r.verdict;
      card.dataset.id = id;

      const loc = r.evidence && r.evidence.length
        ? `${fileOf(r.evidence[0].path)}:${r.evidence[0].line_start}-${r.evidence[0].line_end}`
        : (r.stage1 && r.stage1.candidates && r.stage1.candidates.length
            ? fileOf(r.stage1.candidates[0].split("::")[0]) : "no code mapped");

      const foot = r.verdict === "UNVERIFIABLE"
        ? `<span class="card__conf">${escape(r.reason || "")}</span>`
        : `${meter(r.confidence)}<span class="card__conf">${(r.confidence || 0).toFixed(2)}</span>
           <span class="card__loc">${escape(loc)}</span>`;

      card.innerHTML = `
        <div class="card__top">
          <span class="card__id">${escape(id)}</span>
          <span class="badge" data-v="${r.verdict}">${LABEL[r.verdict] || r.verdict}</span>
          ${r.category ? `<span class="cat">${escape(r.category)}</span>` : ""}
          <span class="card__section">${escape(r.section || "")}</span>
          ${r.cached ? `<span class="pill">cached</span>` : ""}
        </div>
        <p class="card__text">${escape(r.rule_text)}</p>
        <div class="card__foot">${foot}</div>`;

      card.addEventListener("click", () => selectRule(id));
      $ruleList.appendChild(card);
    });
    markSelection();
  }

  function markSelection() {
    document.querySelectorAll(".tick, .card").forEach((n) =>
      n.classList.toggle("is-selected", n.dataset.id === state.selected));
  }

  function renderEvidencePlaceholder() {
    $evidence.innerHTML =
      `<div class="empty">Select a rule — or a tick in the ribbon — to see the code it was judged against.</div>`;
  }

  // ----------------------------------------------------------- evidence

  async function selectRule(id, opts = {}) {
    state.selected = id;
    markSelection();
    if (window.matchMedia("(max-width: 900px)").matches) $pane.classList.add("is-open");
    if (opts.scroll) {
      const card = document.querySelector(`.card[data-id="${id}"]`);
      if (card) card.scrollIntoView({ block: "center", behavior: "smooth" });
      else { state.filter = "all"; syncChips(); renderList(); markSelection(); }
    }
    await showRule(id);
  }

  async function showRule(id) {
    const local = state.rules.get(id);
    if (!local) return;
    let r = local;
    try {
      const res = await fetch(`/api/rule/${id}`);
      if (res.ok) r = { ...local, ...(await res.json()) };
    } catch { /* fall back to what the report already gave us */ }

    const tone = r.verdict === "ALIGNED" ? "ev-aligned"
      : r.verdict === "NEEDS_HUMAN" ? "ev-human" : "";

    const blocks = (r.evidence || []).map((e) => {
      const lines = (e.lines && e.lines.length)
        ? e.lines
        : String(e.snippet || "").split("\n").map((t, i) => ({ n: e.line_start + i, text: t, cited: true }));
      const body = lines.map((l) =>
        `<div class="code__line ${l.cited ? "cited" : ""}"><span>${l.n}</span><span>${escape(l.text)}</span></div>`
      ).join("");
      return `
        <div class="ev-block">
          <div class="ev-block__head">
            <span>${escape(e.path)}</span><span>lines ${e.line_start}–${e.line_end}</span>
          </div>
          <pre class="code">${body}</pre>
          ${e.stale ? `<div class="stale">This file changed since the run. Re-run the check.</div>` : ""}
        </div>`;
    }).join("");

    const noEvidence = r.verdict === "UNVERIFIABLE"
      ? `<div class="empty">This rule was rejected before any code was read.<br><b>${escape(r.reason || "")}</b></div>`
      : `<div class="empty">No code was cited for this rule.</div>`;

    const adv = r.adversary || {};
    const advBlock = adv.ran ? `
      <div class="section">
        <span class="eyebrow">Second opinion</span>
        <div class="callout">
          <span class="callout__verdict">${adv.overturned ? "Overturned the first pass" : "Failed to overturn"}</span>
          <p>${escape(adv.argument || "")}</p>
        </div>
      </div>` : "";

    const s1 = r.stage1 || {}, s2 = r.stage2 || {};
    const stages = r.verdict === "UNVERIFIABLE" ? "" : `
      <div class="section">
        <span class="eyebrow">Instrumentation</span>
        <div class="kv">
          <div><span class="k">Stage 1 retrieval</span><span class="v">${(s1.top_score ?? 0).toFixed(3)} · ${s1.duration_ms ?? 0} ms</span></div>
          <div><span class="k">Stage 2 reasoning</span><span class="v">${s2.duration_ms ?? 0} ms</span></div>
          <div><span class="k">First pass</span><span class="v">${escape(r.pass_a_verdict || "—")} @ ${(r.pass_a_confidence ?? 0).toFixed(2)}</span></div>
          <div><span class="k">Candidates</span><span class="v">${(s1.candidates || []).length}</span></div>
        </div>
      </div>`;

    $evidence.className = `evidence ${tone}`;
    $evidence.innerHTML = `
      <div class="ev-head">
        <span class="card__id">${escape(r.rule_id || id)}</span>
        <span class="badge" data-v="${r.verdict}">${LABEL[r.verdict] || r.verdict}</span>
        ${r.category ? `<span class="cat">${escape(r.category)} ${escape(CATEGORY[r.category] || "")}</span>` : ""}
        ${r.cached ? `<span class="pill">cached</span>` : ""}
      </div>
      <p class="ev-rule">${escape(r.rule_text || r.text || "")}</p>
      ${blocks || noEvidence}
      ${r.reasoning ? `<div class="section"><span class="eyebrow">Reasoning</span><p>${escape(r.reasoning)}</p></div>` : ""}
      ${advBlock}
      ${stages}`;
  }

  // -------------------------------------------------------------- events

  let source = null, backoff = null;

  function connect() {
    if (source) source.close();
    source = new EventSource("/api/events");

    source.onopen = () => setConn("live", "live");
    source.onerror = () => {
      setConn("down", "reconnecting");
      source.close();
      clearTimeout(backoff);
      backoff = setTimeout(connect, 2000);
    };

    source.addEventListener("run_started", (e) => onRunStarted(JSON.parse(e.data)));
    source.addEventListener("run_ready", (e) => onRunReady(JSON.parse(e.data)));
    source.addEventListener("step", (e) => onStep(JSON.parse(e.data)));
    source.addEventListener("rule_started", (e) => onRuleStarted(JSON.parse(e.data)));
    source.addEventListener("rule_verdict", (e) => onRuleVerdict(JSON.parse(e.data)));
    source.addEventListener("run_finished", (e) => onRunFinished(JSON.parse(e.data)));
    source.addEventListener("run_failed", (e) => onRunFailed(JSON.parse(e.data)));
  }

  function setConn(cls, text) {
    $conn.className = `conn is-${cls}`;
    $connText.textContent = text;
  }

  function setRunning(on) {
    state.running = on;
    $runBtn.disabled = on;
    $runBtn.textContent = on ? "Checking…" : "Run check";
    $ribbon.classList.toggle("is-running", on);
  }

  function onRunStarted(d) {
    setRunning(true);
    if (d && d.steps && d.steps.length) ingestSteps(d.steps);
    resetSteps();
    startClock();
  }

  function onRunReady() {
    state.order.forEach((id) => {
      const r = state.rules.get(id);
      if (r.verdict !== "UNVERIFIABLE") r.verdict = "PENDING";
    });
    renderRibbon();
    renderList();
  }

  /* Steps 3-7 fire once per rule, so this arrives often. Patch the one step
     that changed and repaint the rail rather than re-fetching the report. */
  function onStep(s) {
    const prev = state.steps.get(s.key);
    state.steps.set(s.key, s);
    renderFlow();
    if (s.status === "failed" && (!prev || prev.status !== "failed")) {
      const f = s.failures[s.failures.length - 1] || {};
      toast("DRIFTED", `Step ${s.n} failed · ${s.label}`,
        `${f.rule_id ? f.rule_id + " · " : ""}${f.message || ""}`, f.rule_id);
    }
  }

  function onRuleStarted(d) {
    const tick = document.querySelector(`.tick[data-id="${d.rule_id}"]`);
    if (tick) tick.dataset.v = "RUNNING";
  }

  function onRuleVerdict(v) {
    state.rules.set(v.rule_id, v);
    if (!state.order.includes(v.rule_id)) {
      state.order.push(v.rule_id);
      state.order.sort();
      renderRibbon();
    }
    const tick = document.querySelector(`.tick[data-id="${v.rule_id}"]`);
    if (tick) {
      tick.dataset.v = v.verdict;
      tick.querySelector(".tick__tip").innerHTML =
        `<b>${escape(v.rule_id)} · ${LABEL[v.verdict] || v.verdict}</b>${escape(v.rule_text)}`;
    }
    renderList();

    if (v.verdict === "DRIFTED") {
      const e = v.evidence && v.evidence[0];
      toast("DRIFTED", `Drift in ${v.rule_id}`,
        e ? `${fileOf(e.path)}:${e.line_start}` : (v.category || ""), v.rule_id);
    } else if (v.verdict === "NEEDS_HUMAN") {
      toast("NEEDS_HUMAN", `${v.rule_id} needs a human`,
        v.adversary && v.adversary.overturned
          ? "the two passes disagreed" : "confidence below the threshold", v.rule_id);
    }
  }

  async function onRunFinished(s) {
    setRunning(false);
    stopClock(s.duration_ms);
    if (s.steps && s.steps.length) { ingestSteps(s.steps); renderFlow(); }
    const res = await fetch("/api/report");
    const report = await res.json();
    if (report.status !== "empty") { ingest(report); render(); }
    await loadRepo();

    if (s.drifted > 0) {
      toast("DRIFTED", `${s.drifted} ${s.drifted === 1 ? "rule" : "rules"} drifted.`,
        "Merge would be blocked.");
    } else {
      const n = (state.report && state.report.summary.aligned) || 0;
      toast("ALIGNED", `${n} of ${n} rules still match the spec.`,
        `checked in ${(s.duration_ms / 1000).toFixed(1)}s`);
    }
  }

  function onRunFailed(d) {
    setRunning(false);
    stopClock();
    // Whichever step was still running is where it broke.
    const running = STEP_DEFS.map(([k]) => state.steps.get(k))
      .find((s) => s && s.status === "running");
    if (running) {
      running.status = "failed";
      running.failures = [...(running.failures || []),
        { rule_id: "", message: d.error || "the run stopped here", level: "error" }];
      renderFlow();
    }
    toast("DRIFTED", "The check could not finish.",
      running ? `Step ${running.n} · ${running.label}` : (d.error || "See the terminal."));
  }

  // -------------------------------------------------------------- toasts

  function toast(verdict, title, meta, ruleId) {
    const node = document.createElement("div");
    node.className = "toast";
    node.dataset.v = verdict;
    node.innerHTML = `
      <div class="toast__body">
        <span class="toast__title">${escape(title)}</span>
        ${meta ? `<span class="toast__meta">${escape(meta)}</span>` : ""}
      </div>
      <button class="toast__x" type="button" aria-label="Dismiss">×</button>`;

    const kill = () => node.remove();
    node.querySelector(".toast__x").addEventListener("click", (e) => { e.stopPropagation(); kill(); });
    if (ruleId) node.addEventListener("click", () => { selectRule(ruleId, { scroll: true }); kill(); });
    $toasts.appendChild(node);
    setTimeout(kill, 6000);
  }

  // ------------------------------------------------------------ controls

  $runBtn.addEventListener("click", async () => {
    if (state.running) return;
    setRunning(true);
    try {
      await fetch("/api/check", { method: "POST" });
    } catch {
      setRunning(false);
      toast("DRIFTED", "Could not start the check.", "Is the server still running?");
    }
  });

  function syncChips() {
    document.querySelectorAll(".chip").forEach((c) =>
      c.classList.toggle("is-on", c.dataset.filter === state.filter));
  }

  document.querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      state.filter = chip.dataset.filter;
      syncChips();
      renderList();
    }));

  el("sheetClose").addEventListener("click", () => $pane.classList.remove("is-open"));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $pane.classList.remove("is-open");
  });

  boot();
})();

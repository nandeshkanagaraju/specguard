# SpecGuard

**Specification-drift detection.** Your tests tell you the code still works. SpecGuard
tells you whether it still does what the specification said it would.

SpecGuard reads a Markdown spec, breaks it into numbered atomic rules, maps each rule to
the code that should implement it, and returns one of four verdicts per rule — with the
lines of code that justify it.

| Verdict | Meaning |
|---|---|
| `ALIGNED` | the code satisfies the rule, and here are the lines |
| `DRIFTED` | the code contradicts the rule, and here are the lines |
| `NEEDS_HUMAN` | the two passes disagreed, or confidence fell below the threshold |
| `UNMAPPED` | no code scored above the retrieval floor |

---

## Quick start

**macOS / Linux**

```bash
git clone https://github.com/nandeshkanagaraju/specguard.git
cd specguard
make install                 # venv + install + build the demo fixture
make demo                    # dashboard on the drifted fixture
```

**Windows** — see **[WINDOWS.md](WINDOWS.md)** for the VS Code walkthrough.

```powershell
git clone https://github.com/nandeshkanagaraju/specguard.git
cd specguard
.\setup.ps1
```

No API key is needed for the demo. The default provider replays recorded model responses,
so it runs entirely offline. To check *your own* project you need a real model — Ollama
(free, local) or an Anthropic key. See [Providers](#providers).

> The demo fixture in `samples/orderflow` is a git repository in its own right, with
> `clean` and `drifted` tags, so it cannot be nested inside this one. `make install` and
> `setup.ps1` build it for you; to do it by hand, run `scripts/build_fixture.sh`
> (or `scripts\build_fixture.ps1`).

## The demo in one minute

```bash
make demo-clean      # the fixture matches its spec
cd samples/orderflow && pytest -q          # 15 passed
specguard check .                          # 11 aligned, drift score 0.00, exit 0

make demo-drift      # a normal week of development happened
cd samples/orderflow && pytest -q          # 15 passed  ← still green
specguard check .                          # 3 drifted, 1 needs human, exit 1
```

**That is the whole argument.** The test suite is green on both commits. Three rules
have drifted anyway.

What drifted, and why it is invisible to the tests:

| Rule | Drift | Category | Why the tests miss it |
|---|---|---|---|
| R-004 | `>= 500` became `> 500` | `D1` boundary shift | no test asserts the exact boundary |
| R-006 | payment authorised before stock reserved | `D5` sequence violation | the happy path ends the same way |
| R-008 | quantity validation deleted, docstring kept | `D2` + `D4` dropped rule / comment decoy | no test passes a quantity below 1 |
| R-009 | `except PaymentDeclined` widened to `except Exception` | — → `NEEDS_HUMAN` | the two passes genuinely disagree |
| R-010 | receipt loop rewritten as a comprehension | negative control | stays `ALIGNED` — rewriting is not drift |
| R-012 | — | unverifiable | "should feel fast" is rejected by the parser |

## How it works

```
L4  INTERFACE      CLI · pre-commit hook · PR check · dashboard (SSE)
L3  CORE ENGINE    SpecParser → RuleMapper → Verifier → ReportBuilder
L2  RELIABILITY    Adversary (2nd pass) · ConfidenceScorer · Cache
L1  FOUNDATIONS    ModelAdapter (mock/anthropic/ollama) · git · file store
```

Eight steps, each separately instrumented:

| # | Step | What it produces |
|---|---|---|
| 1 | Parse spec | `Rule[]`, plus rejected unverifiable rules |
| 2 | Index code | `Chunk[]` — one per function, method, class, constant block |
| 3 | Retrieve candidates | **Stage 1**: top-k chunks above the floor, with scores |
| 4 | Cache lookup | a stored verdict, or a miss |
| 5 | Verify · pass A | **Stage 2**: an evidence-citing verdict |
| 6 | Adversary · pass B | the strongest case that pass A is wrong |
| 7 | Score & abstain | confidence, disagreement, `NEEDS_HUMAN` |
| 8 | Build report | `report.json`, the summary table, the exit code |

Stages 1 and 2 are timed and recorded separately so a failure can be attributed to
*retrieval* (the right code was never shown to the model) or to *reasoning* (it was shown
and the model still got it wrong). The dashboard's left rail draws this live, and marks
the step where a run went wrong.

### Three design commitments

**Every verdict cites code.** A `DRIFTED` claim with no line numbers is discarded, not
down-weighted. A citation pointing outside the code the model was shown is discarded too.
The model gets one retry, then the rule is routed to a human.

**Disagreement beats confidence.** Pass B argues the opposite of whatever pass A
concluded. If it succeeds, the result is `NEEDS_HUMAN` — regardless of how sure pass A
was. This is the direct mitigation of the base-paper finding (Jin & Chen 2026) that
richer prompting inflates false rejection: a single confident pass over-corrects, so a
claim only counts if it survives an argument against it.

**The same input gives the same output.** Temperature 0 plus a content-addressed cache
keyed on `rule hash + chunk hashes + model id + prompt version`. Run it twice and the
verdicts are byte-identical; only the timings move.

## Commands

```
specguard init                     scaffold specguard.toml + SPEC.md
specguard check [PATH]             run the pipeline, write .specguard/report.json
  --spec SPEC.md                   spec file (default: SPEC.md)
  --provider mock|anthropic|ollama
  --rule R-004                     check a single rule
  --no-cache                       ignore stored verdicts
  --strict                         abstentions fail the build too
  --json                           machine-readable stdout
specguard serve [--port 8000]      dashboard + API
specguard record-oracle            regenerate the offline oracle from a live model
specguard hook install             write .git/hooks/pre-commit
specguard hook-preview             print the GitHub Action YAML
```

Exit codes: `1` if anything drifted, `0` otherwise. Abstentions and unmapped rules warn
but do not fail, unless `--strict`. Only real drift blocks a merge by default.

## Writing a spec

Rules are list items under a `## Rules` heading. IDs are assigned in document order and
stay stable as long as rules are appended rather than reordered.

```markdown
## Rules

### Shipping

- Orders with a subtotal of 500 or more qualify for free shipping.
- Standard shipping is a flat 40 for orders below the free-shipping threshold.
```

The nearest heading becomes the rule's `section`, which is used as a component hint
during retrieval — so name sections after the part of the system they govern.

A rule that uses vague language (`fast`, `robust`, `scalable`, `appropriate`, …) *and*
states no comparison, numeral, or identifier is rejected as unverifiable and reported
rather than silently checked. SpecGuard is only as good as the spec, and says so.

## Providers

| Provider | Notes |
|---|---|
| `mock` | default. Replays recorded responses from `.specguard_oracle.json`. Offline. |
| `anthropic` | `ANTHROPIC_API_KEY`, temperature 0. Falls back to `mock` if the key is missing or the call fails. |
| `ollama` | `http://localhost:11434`, `qwen2.5-coder:7b`, temperature 0, seed 7. |

The mock is a response cache, not a fake: evidence is stored as verbatim source anchors
and re-resolved to line numbers against the prompt being answered, so a recorded verdict
is only replayed while its citation still points at real code. Anything it has not seen
returns `NEEDS_HUMAN`.

## Scope

**In:** Python, Markdown specs, lexical + AST-signature retrieval, evidence-cited
verification, adversarial second pass, abstention, deterministic caching, JSON reports,
CLI, dashboard, pre-commit hook, GitHub Action.

**Not yet (Phase 2):** SpecDrift-Bench — ~250 labelled cases across the nine drift
categories injected into ten working projects, with precision, recall and false-alarm
rate reported per category; embedding retrieval and the lexical-vs-embedding ablation;
calibration of the abstention threshold; multi-language support.

The retriever sits behind a `Retriever.rank(rule, chunks) -> Candidate[]` interface
precisely so the embedding backend is a swap rather than a rewrite. Committing to
embeddings before retrieval-attributed failures can be measured would be assuming the
answer.

## Layout

```
src/specguard/
  cli.py            spec_parser.py   indexer.py     retriever.py
  verifier.py       adversary.py     scoring.py     cache.py
  engine.py         pipeline.py      report.py      prompts.py
  oracle.py         recorder.py      config.py      models.py
  adapters/         base · mock · anthropic · ollama
  server/           app.py + static/dashboard.{html,css,js}
  hooks/            pre-commit · github-action.yml
samples/orderflow/  the demo fixture, with `clean` and `drifted` tags
tests/              67 tests, no network
```

## Tests

```bash
pytest                                   # 67 tests
cd samples/orderflow && pytest -q        # the fixture's own suite: green on both tags
```

---

Base paper: Haolin Jin & Huaming Chen, "Are LLMs reliable code reviewers? Systematic
overcorrection in requirement conformance judgement", *Automated Software Engineering*
33, Art. 90 (2026). DOI 10.1007/s10515-026-00638-5.

# SpecGuard — demo run sheet

Five minutes. One idea: **the tests pass and the code has still drifted from the spec.**

---

## Before the room

```bash
cd ~/Documents/MiniProject/specguard
./scripts/setup_demo.sh
```

That puts everything in the right starting state and starts the dashboard. Then:

- Browser open at **http://127.0.0.1:8000** — all ticks teal, drift score 0.00
- A second terminal tab sitting in `samples/orderflow`
- `SPEC.md` open in an editor, ready to show

Check the header reads `orderflow · clean`. If it doesn't, run the setup script again.

---

## The run

### 1. "Every project starts with a spec."

Show `samples/orderflow/SPEC.md`. Twelve numbered rules across six sections.

> Each one is atomic and testable. SpecGuard numbers them R-001 to R-012 in document order.

### 2. "Here's the code today."

Switch to the dashboard. Every tick teal, **drift score 0.00**.

> The strip under the header is one tick per rule. Green means the code satisfies it and
> the tool can point at the lines.

### 3. "Now a normal week of development."

```bash
./scripts/demo.sh drift
```

> One commit. The message says "tidy checkout, simplify validation, adjust the
> free-shipping check." Nothing in it claims to change behaviour.

### 4. **"And the tests still pass."** ← pause here

```bash
cd samples/orderflow && pytest -q
```

**15 passed.** Let it sit for a second.

> Green suite. If this were a pull request, CI would approve it.

### 5. Click **Run check**.

The ribbon repaints left to right. Three ticks go crimson, one violet. Toasts fire.
The left rail shows the eight pipeline steps filling in live.

> Seconds, before merge. Three rules drifted, one needs a human.

### 6. Click the first crimson tick — **R-004**.

> The spec says free shipping at a subtotal of **500 or more**. The code says
> `subtotal > 500`. An order of exactly 500 is charged. That is a boundary shift — our
> category D1.
>
> And notice it cites the line. You can check its work. A drift claim with no cited line
> is discarded by the tool, not reported as low confidence.

### 7. Click the violet tick — **R-009**.

> Here the two passes disagreed. The first said the widened `except Exception` breaks the
> rule. The second argued the rule only requires that `PaymentDeclined` is raised and stock
> stays reserved — which the code still does.
>
> So it asked for a human instead of guessing. That is deliberate. The paper we build on
> shows LLM reviewers reject correct code at high rates when you ask them to explain and
> fix. Abstention is our answer to that over-correction.

### 8. Click **Run check** again.

Same verdicts. Every card now shows a `cached` chip. Sub-second.

> Same input, same answer, every run. Temperature zero and a content-addressed cache.
> Teams keep a tool switched on only if it's stable.

### 9. Close on the roadmap.

> That's the tool. The contribution is next: SpecDrift-Bench — around 250 labelled cases
> across nine drift categories injected into ten working projects, reported as precision,
> recall and false-alarm rate per category.

---

## What drifted, if they ask

| Rule | Change | Category | Why the tests miss it |
|---|---|---|---|
| R-004 | `>= 500` → `> 500` | `D1` boundary shift | no test asserts the exact boundary |
| R-006 | payment authorised before stock reserved | `D5` sequence violation | the happy path ends the same way |
| R-008 | quantity check deleted, docstring kept | `D2` + `D4` dropped rule / comment decoy | no test passes a quantity below 1 |
| R-009 | `except PaymentDeclined` → `except Exception` | → `NEEDS_HUMAN` | the disagreement is genuine |
| R-010 | receipt loop → comprehension | negative control | stays `ALIGNED` — a rewrite is not drift |
| R-012 | — | unverifiable | "should feel fast" rejected by the parser |

**R-010 is the one to point at** if someone asks "how do you know it doesn't just flag
everything that changed?" That function was rewritten and correctly stayed green.

---

## Likely questions

**"Is the model just told the answers?"** The offline run replays recorded conformance
judgements so the demo works without a network. Same code path runs live with
`--provider anthropic` or `--provider ollama`. Be straight about it: the committed oracle
is authored and compiled, and the compiler rejects any citation that doesn't resolve to
real lines. `specguard record-oracle` replaces it with live model output.

**"Why lexical retrieval, not embeddings?"** Interface parity — `Retriever.rank()` is the
seam, and lexical-vs-embedding is a planned ablation. Committing to embeddings before we
can measure retrieval-attributed failures would assume the answer. We also found a real
limit: symmetric Jaccard penalises large functions, so on a 1,400-line project the right
chunk ranked first and still fell below the floor. That's a measured motivation for the
swap, not a guess.

**"What if the spec is vague?"** R-012 in the demo. The parser rejects it up front and
reports it rather than pretending to check it.

**"How is this different from Semcheck / Spec Kit?"** Semcheck reports issue counts; it
doesn't separate retrieval failure from reasoning failure, doesn't quantify false alarms,
and doesn't catch behaviour added beyond what the spec authorised. Spec Kit and Kiro
validate once at generation time — the code then changes for months.

---

## If something breaks

| | |
|---|---|
| Dashboard blank | Show the terminal: `specguard check samples/orderflow`. The CLI table carries the whole story. |
| Server won't start | `.venv/bin/specguard serve samples/orderflow --port 8001` |
| Ribbon doesn't animate | Everything was cached. `rm -rf samples/orderflow/.specguard/cache` and re-run. |
| Everything is broken | Open `samples/orderflow/.specguard/report.json` and walk the JSON. Every claim is in it. |

## Reset between rehearsals

```bash
./scripts/setup_demo.sh
```

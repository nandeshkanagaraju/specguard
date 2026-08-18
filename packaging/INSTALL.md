# SpecGuard — install and try it

SpecGuard checks whether your code still does what your specification says it does.
Your tests tell you the code *works*. This tells you it's still the thing you agreed to build.

**Requires:** Python 3.11 or newer, and git. Nothing else — no API key needed for the demo.

---

## 1. Install

```bash
./setup.sh
```

That creates a virtualenv, installs SpecGuard into it, and builds the demo project's
two commits. Takes about a minute.

On Windows, use PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install specguard-0.1.0-py3-none-any.whl
.venv\Scripts\specguard --help
```

---

## 2. See the point of it (2 minutes)

The demo is a small order service with a 12-rule spec. It has two commits: `clean`,
where the code matches the spec, and `drifted`, after a normal week of development.

```bash
./demo.sh clean
./run.sh check demo/orderflow
```

11 rules aligned, drift score 0.00. Now move to the drifted commit:

```bash
./demo.sh drift
cd demo/orderflow && ../../.venv/bin/python -m pytest -q ; cd ../..
```

**15 tests pass.** The test suite is completely green. Now ask SpecGuard:

```bash
./run.sh check demo/orderflow
```

Three rules have drifted, one needs a human. **That gap — green tests, drifted code —
is the entire point of the project.**

What it found, and why the tests missed it:

| Rule | What changed | Why no test caught it |
|---|---|---|
| R-004 | `>= 500` became `> 500` | no test checks the exact boundary |
| R-006 | payment now authorised *before* stock is reserved | the happy path ends the same way |
| R-008 | quantity validation deleted, docstring still promises it | no test passes a quantity below 1 |
| R-009 | error handler widened to `except Exception` | the two checkers genuinely disagree → asks a human |
| R-010 | receipt loop rewritten as a comprehension | correctly stays ALIGNED — a rewrite is not drift |

---

## 3. The dashboard

```bash
./run.sh serve demo/orderflow
```

Open **http://127.0.0.1:8000** and click **Run check**. The coloured strip under the
header is one tick per rule; the left rail shows the 8 pipeline steps filling in live.
Click any rule to see the exact lines of code behind its verdict.

If the run finishes instantly with `cached` chips everywhere, that's the determinism
guarantee working — same input, same answer. To watch it run slowly again:

```bash
rm -rf demo/orderflow/.specguard/cache
```

---

## 4. Use it on your own project

The demo runs offline from recorded model answers. **Your own code needs a real model** —
otherwise every rule comes back "needs a human", which is SpecGuard refusing to guess.

Pick one:

```bash
# Option A — cloud, fast, needs a key
export ANTHROPIC_API_KEY=sk-ant-...
./run.sh check ~/my-project --provider anthropic

# Option B — fully local and free, slower
brew install ollama && ollama pull qwen2.5-coder:7b     # or see ollama.com
./run.sh check ~/my-project --provider ollama
```

Then, in your project:

```bash
cd ~/my-project
/path/to/this/run.sh init .        # creates specguard.toml + SPEC.md
```

Write your rules in `SPEC.md` — one checkable sentence per bullet:

```markdown
## Rules

### Invoicing

- A late fee of 25 applies once an invoice is 30 or more days overdue.
- Credits reduce the balance but never below zero.
```

Good rules name a number, a comparison, or an identifier. A rule like "the page should
feel fast" is rejected up front as unverifiable and reported — SpecGuard is only as good
as the spec, and it says so rather than pretending.

Set `provider = "ollama"` in `specguard.toml` and you can just run `specguard check .`
from then on.

---

## 5. Make it automatic

```bash
/path/to/this/run.sh hook install ~/my-project
```

Every `git commit` now runs the check and refuses the commit if something drifted.
`git commit --no-verify` bypasses it when you need to.

---

## Command reference

```
specguard init                  scaffold specguard.toml + SPEC.md
specguard check [PATH]          run the check, write .specguard/report.json
  --provider mock|anthropic|ollama
  --rule R-004                  check one rule (good for testing your setup)
  --no-cache                    ignore stored answers
  --strict                      abstentions fail the build too
  --json                        machine-readable output
specguard serve [--port 8000]   the dashboard
specguard hook install          install the git pre-commit hook
```

Exit code is `1` if anything drifted, `0` otherwise. "Needs a human" warns but doesn't
fail, unless you pass `--strict`.

---

## Troubleshooting

**"Python 3.11 or newer is required"** — install it, then re-run `./setup.sh`.

**Everything says "needs a human" on my project** — expected. The offline mode only has
recorded answers for the bundled demo. Use `--provider anthropic` or `--provider ollama`.

**Ollama is slow** — it makes two model calls per rule. Test with one rule first:
`./run.sh check . --rule R-001 --provider ollama`.

**Port 8000 is busy** — `./run.sh serve demo/orderflow --port 8001`.

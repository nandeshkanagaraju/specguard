# SpecGuard on Windows, in VS Code

Everything below is PowerShell inside VS Code's integrated terminal.

**You need:** Windows 10/11, [Python 3.11+](https://www.python.org/downloads/)
(tick **"Add python.exe to PATH"** during install), [Git](https://git-scm.com/download/win),
and [VS Code](https://code.visualstudio.com/).

---

## 1. Get the code

Open VS Code → **Terminal → New Terminal** (or `` Ctrl+` ``). Make sure the dropdown on
the right of the terminal says **PowerShell**.

```powershell
cd $HOME\Documents
git clone https://github.com/nandeshkanagaraju/specguard.git
cd specguard
code -r .
```

## 2. Install

```powershell
.\setup.ps1
```

If PowerShell refuses with *"running scripts is disabled on this system"*, allow local
scripts for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

then run `.\setup.ps1` again.

This creates `.venv\`, installs SpecGuard into it, and builds the demo project's two
git commits. About a minute.

## 3. Point VS Code at the virtualenv

`Ctrl+Shift+P` → **Python: Select Interpreter** → choose the one ending in
`.venv\Scripts\python.exe`. New terminals will now activate it automatically, so you can
type `specguard` instead of the full path.

If it does not activate, use the full path anywhere you see `specguard` below:

```powershell
.\.venv\Scripts\specguard.exe check samples\orderflow
```

---

## 4. See the point of it (2 minutes)

The demo is a small order service with a 12-rule spec, in two commits.

```powershell
.\demo.ps1 clean
specguard check samples\orderflow
```

11 rules aligned, drift score 0.00. Now move to the drifted commit:

```powershell
.\demo.ps1 drift
.\.venv\Scripts\python.exe -m pytest samples\orderflow\tests -q
```

**15 tests pass.** Completely green. Now ask SpecGuard:

```powershell
specguard check samples\orderflow
```

Three rules drifted, one needs a human. Green tests, drifted code — that gap is the
whole point.

### The dashboard

```powershell
specguard serve samples\orderflow
```

VS Code will offer to open **http://127.0.0.1:8000** in your browser; take it. Click
**Run check** and watch the ribbon and the pipeline rail fill in. `Ctrl+C` to stop.

If a run finishes instantly with `cached` chips everywhere, that is the determinism
guarantee working. To watch it run slowly again:

```powershell
Remove-Item -Recurse -Force samples\orderflow\.specguard\cache
```

---

## 5. Run it on your own project

The demo runs offline from recorded model answers. **Your own code needs a real model** —
without one every rule comes back "needs a human", which is SpecGuard refusing to guess
rather than a bug.

### Pick a model

**Option A — Ollama. Free, local, no account.** Download the Windows installer from
[ollama.com/download](https://ollama.com/download), then:

```powershell
ollama pull qwen2.5-coder:7b
```

**Option B — Anthropic. Faster and better, needs an API key.**

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."      # this session only
setx ANTHROPIC_API_KEY "sk-ant-..."        # permanently (reopen the terminal after)
```

### Set it up in your project

```powershell
cd C:\path\to\your-project
specguard init .
```

That writes `specguard.toml`, a `SPEC.md` skeleton, and `.specguardignore`.

Open `SPEC.md` in VS Code and write your rules — one checkable sentence per bullet:

```markdown
## Rules

### Invoicing

- A late fee of 25 applies once an invoice is 30 or more days overdue.
- Credits reduce the balance but never below zero.
```

Good rules name a number, a comparison, or an identifier. A rule like *"the page should
feel fast"* is rejected up front as unverifiable and reported — SpecGuard is only as good
as the spec, and says so rather than pretending.

Set your provider in `specguard.toml` so you do not have to pass it every time:

```toml
[model]
provider = "ollama"        # or "anthropic"
```

### Check it

```powershell
specguard check . --rule R-001      # one rule first, to confirm the model works
specguard check .                   # the whole spec
specguard serve .                   # the dashboard, on your project
```

Start with `--rule R-001`. A 7B model on Ollama makes two calls per rule, so a full spec
takes a while — confirm the setup works before running all of it.

---

## 6. Make it automatic (optional)

```powershell
specguard hook install .
```

Every `git commit` in that project now runs the check and refuses the commit if something
drifted. `git commit --no-verify` bypasses it.

This works on Windows because Git for Windows ships its own bash to run hooks. The hook
records the full path to your `.venv\Scripts\specguard.exe`, so it keeps working even
when the virtualenv is not active.

---

## Troubleshooting

**`python` opens the Microsoft Store** — Windows' stub. Install real Python from
python.org with "Add to PATH" ticked, or use `py -3.11` instead of `python`.

**`running scripts is disabled on this system`** — see step 2.

**`specguard : The term 'specguard' is not recognized`** — the virtualenv is not active.
Either select the interpreter (step 3) and open a new terminal, or use the full path
`.\.venv\Scripts\specguard.exe`.

**Everything says "needs a human" on my project** — expected without a real model.
See step 5.

**Port 8000 already in use** — `specguard serve . --port 8001`.

**Ollama connection refused** — make sure the Ollama app is running; it must be started
before `specguard check`.

**Long path errors while cloning** — enable long paths once, as Administrator:
`git config --system core.longpaths true`.

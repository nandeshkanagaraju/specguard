"""specguard — the command line."""

from __future__ import annotations

import json
import shutil
import stat
import sys
from pathlib import Path

import typer
from rich.console import Console

from .config import DEFAULT_TOML, load_config
from .models import ALIGNED, DRIFTED, NEEDS_HUMAN, UNMAPPED
from .report import exit_code, write_report

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Specification-drift detection: does the code still do what the spec says?",
)
hook_app = typer.Typer(no_args_is_help=True, help="Manage the pre-commit hook.")
app.add_typer(hook_app, name="hook")

def _console(**kw) -> Console:
    """Keep the table readable when stdout is a pipe or a git hook, not a terminal.

    Rich falls back to 80 columns off-TTY, which squeezes the verdict column down
    to "DRIF…" — exactly where the output matters most.
    """
    c = Console(**kw)
    if not c.is_terminal:
        return Console(width=110, **kw)
    return c


console = _console()
err = _console(stderr=True)

STYLES = {
    ALIGNED: "bold green",
    DRIFTED: "bold red",
    NEEDS_HUMAN: "bold magenta",
    UNMAPPED: "bold bright_black",
}
LABELS = {
    ALIGNED: "ALIGNED",
    DRIFTED: "DRIFTED",
    NEEDS_HUMAN: "NEEDS HUMAN",
    UNMAPPED: "UNMAPPED",
}


# ------------------------------------------------------------------ output


def _location(v: dict) -> str:
    if v["evidence"]:
        e = v["evidence"][0]
        return f"{Path(e['path']).name}:{e['line_start']}-{e['line_end']}"
    if v["stage1"].get("candidates"):
        return Path(v["stage1"]["candidates"][0].split("::")[0]).name
    return "—"


def _note(v: dict) -> str:
    if v["verdict"] == NEEDS_HUMAN and v["adversary"].get("overturned"):
        return "the two passes disagreed"
    if v["verdict"] == UNMAPPED:
        return "no code matched this rule"
    reasoning = v.get("reasoning") or ""
    first = reasoning.split(". ")[0].rstrip(".")
    return first[:64] + ("…" if len(first) > 64 else "")


def _clip(text: str, width: int) -> str:
    text = text or ""
    return text if len(text) <= width else text[: width - 1] + "…"


def render_table(report: dict) -> None:
    """A fixed-width table.

    Laid out by hand rather than with rich's flex algorithm, which shrinks the
    verdict column — the one column that must always be readable — whenever the
    output is a pipe or a git hook rather than a wide terminal.
    """
    console.print()
    note_width = max(24, console.width - 56)

    for v in report["verdicts"]:
        cached = "⟲" if v["cached"] else " "
        verdict = LABELS[v["verdict"]]
        console.print(
            f"  [cyan]{v['rule_id']:<6}[/cyan]"
            f"[{STYLES[v['verdict']]}]{verdict:<12}[/{STYLES[v['verdict']]}]"
            f"[bright_black]{(v.get('category') or ''):<3}[/bright_black]"
            f"{v['confidence']:>5.2f} {cached}  "
            f"[bright_black]{_clip(_location(v), 19):<19}[/bright_black]  "
            f"{_clip(_note(v), note_width)}",
            highlight=False,
        )

    for u in report["unverifiable_rules"]:
        console.print(
            f"  [yellow]{u['id']:<6}[/yellow]"
            f"[bold yellow]{'UNVERIFIABLE':<12}[/bold yellow]"
            f"{'':<3}{'':>5}    "
            f"[bright_black]{'—':<19}[/bright_black]  "
            f"{_clip(u['reason'] or '', note_width)}",
            highlight=False,
        )

    s = report["summary"]
    total = report["spec"]["rule_count"]
    parts = [
        f"{total} rule{'' if total == 1 else 's'}",
        f"[green]{s['aligned']} aligned[/green]",
        f"[red]{s['drifted']} drifted[/red]",
        f"[magenta]{s['needs_human']} needs human[/magenta]",
    ]
    if s["unmapped"]:
        parts.append(f"[bright_black]{s['unmapped']} unmapped[/bright_black]")
    if report["spec"]["unverifiable_count"]:
        parts.append(f"[yellow]{report['spec']['unverifiable_count']} unverifiable[/yellow]")
    parts.append(f"drift score {s['drift_score']:.2f}")
    parts.append(f"{report['duration_ms'] / 1000:.1f}s")
    console.print()
    console.print("  " + " · ".join(parts))
    console.print()


# ------------------------------------------------------------------ commands


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Where to scaffold."),
) -> None:
    """Scaffold specguard.toml and a SPEC.md skeleton."""
    root = path.resolve()
    root.mkdir(parents=True, exist_ok=True)

    toml_path = root / "specguard.toml"
    if toml_path.exists():
        console.print(f"[yellow]specguard.toml already exists[/yellow] at {toml_path}")
    else:
        toml_path.write_text(DEFAULT_TOML, encoding="utf-8")
        console.print(f"[green]wrote[/green] {toml_path.relative_to(root)}")

    spec_path = root / "SPEC.md"
    if spec_path.exists():
        console.print(f"[yellow]SPEC.md already exists[/yellow] at {spec_path}")
    else:
        spec_path.write_text(SPEC_SKELETON, encoding="utf-8")
        console.print(f"[green]wrote[/green] {spec_path.relative_to(root)}")

    ignore = root / ".specguardignore"
    if not ignore.exists():
        ignore.write_text("tests\ntest_*.py\n*_test.py\nconftest.py\n", encoding="utf-8")
        console.print(f"[green]wrote[/green] {ignore.relative_to(root)}")

    console.print("\nNext: write your rules in SPEC.md, then run [bold]specguard check[/bold].")


@app.command()
def check(
    path: Path = typer.Argument(Path("."), help="Repository to check."),
    spec: str = typer.Option(None, "--spec", help="Spec file, relative to PATH."),
    provider: str = typer.Option(None, "--provider", help="mock | anthropic | ollama"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Ignore cached verdicts."),
    strict: bool = typer.Option(False, "--strict", help="Abstentions fail the build too."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable stdout."),
    rule: str = typer.Option(None, "--rule", help="Check one rule, e.g. R-004."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress the table."),
) -> None:
    """Run the pipeline and write .specguard/report.json."""
    from .engine import run_check

    cfg = load_config(path)
    if spec:
        cfg.spec_path = spec
    if strict:
        cfg.strict = True

    spec_file = cfg.root / cfg.spec_path
    if not spec_file.exists():
        err.print(
            f"[red]No spec at {spec_file}.[/red] Run [bold]specguard init[/bold] to "
            f"create one, or pass --spec."
        )
        raise typer.Exit(2)

    report = run_check(cfg, provider=provider, use_cache=not no_cache, only_rule=rule)
    write_report(report, cfg.report_path)

    if as_json:
        console.print_json(json.dumps(report))
    elif not quiet:
        render_table(report)
        console.print(
            f"  [bright_black]report:[/bright_black] "
            f"{cfg.report_path.relative_to(cfg.root)}\n"
        )

    raise typer.Exit(exit_code(report, strict=cfg.strict))


@app.command()
def serve(
    path: Path = typer.Argument(Path("."), help="Repository to watch."),
    port: int = typer.Option(8000, "--port"),
    host: str = typer.Option("127.0.0.1", "--host"),
    provider: str = typer.Option(None, "--provider"),
) -> None:
    """Start the dashboard and its API."""
    import uvicorn

    from .server.app import create_app

    cfg = load_config(path)
    application = create_app(cfg, provider=provider)
    console.print(
        f"\n  [bold]SpecGuard[/bold]  watching [cyan]{cfg.root}[/cyan]\n"
        f"  dashboard  [bold blue]http://{host}:{port}[/bold blue]\n"
    )
    uvicorn.run(application, host=host, port=port, log_level="warning")


@app.command("record-oracle")
def record_oracle(
    path: Path = typer.Argument(Path("."), help="Repository to record against."),
    provider: str = typer.Option("anthropic", "--provider", help="anthropic | ollama"),
    variants: str = typer.Option(
        None,
        "--variants",
        help="Comma-separated git tags to record. Default: just the current tree.",
    ),
) -> None:
    """Regenerate the mock oracle from a real provider."""
    from .recorder import record

    cfg = load_config(path)
    tags = [t.strip() for t in variants.split(",")] if variants else None
    written = record(cfg, provider=provider, tags=tags, console=console)
    console.print(f"\n[green]wrote[/green] {written} — the mock now replays live output.\n")


@hook_app.command("install")
def hook_install(
    path: Path = typer.Argument(Path("."), help="Repository to install into."),
) -> None:
    """Write .git/hooks/pre-commit."""
    root = path.resolve()
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.parent.exists():
        err.print(f"[red]{root} is not a git repository.[/red] Run git init first.")
        raise typer.Exit(2)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    source = Path(__file__).parent / "hooks" / "pre-commit"
    target = hooks_dir / "pre-commit"
    if target.exists():
        backup = hooks_dir / "pre-commit.specguard-backup"
        shutil.copy2(target, backup)
        console.print(f"[yellow]existing hook backed up to[/yellow] {backup.name}")

    # Bake in this interpreter's own specguard, so the hook still works when
    # SpecGuard lives in a virtualenv that is not on the user's PATH.
    bindir = Path(sys.executable).parent
    binary = bindir / ("specguard.exe" if sys.platform == "win32" else "specguard")
    target.write_text(
        source.read_text(encoding="utf-8").replace(
            "@SPECGUARD_BIN@", str(binary) if binary.exists() else "specguard"
        ),
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    if binary.exists():
        console.print(f"[bright_black]using[/bright_black] {binary}")
    console.print(f"[green]installed[/green] {target}")
    console.print("Commits are now checked for spec drift. Bypass once with --no-verify.")


@app.command("hook-preview")
def hook_preview() -> None:
    """Print the GitHub Action YAML to stdout."""
    console.print((Path(__file__).parent / "hooks" / "github-action.yml").read_text())


SPEC_SKELETON = """\
# Specification

Write one atomic, checkable statement per list item. SpecGuard numbers them in
document order: the first is R-001, the second R-002, and so on.

## Rules

### Example section

- Replace this with a rule that states a measurable condition.
- Rules that name a number, a comparison, or an identifier are the easiest to check.
"""


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()

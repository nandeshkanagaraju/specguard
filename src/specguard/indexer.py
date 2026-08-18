"""AST-level code chunking. One Chunk per top-level function, method, class, and
module-level constant block."""

from __future__ import annotations

import ast
from fnmatch import fnmatch
from pathlib import Path

from .models import Chunk, sha256

DEFAULT_IGNORES = {
    ".git",
    ".specguard",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".mypy_cache",
    "build",
    "dist",
}


def _read_ignore_file(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line.rstrip("/").lstrip("/"))
    return out


def iter_python_files(root: Path) -> list[Path]:
    root = Path(root)
    ignores = set(DEFAULT_IGNORES)
    ignores |= _read_ignore_file(root / ".gitignore")
    ignores |= _read_ignore_file(root / ".specguardignore")

    files: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        parts = rel.parts
        if any(
            part == pat or fnmatch(part, pat)
            for part in parts
            for pat in ignores
        ):
            continue
        if any(fnmatch(rel.as_posix(), pat) for pat in ignores):
            continue
        files.append(p)
    return files


def _signature(node: ast.AST, source_lines: list[str]) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [a.arg for a in node.args.args]
        if node.args.vararg:
            args.append("*" + node.args.vararg.arg)
        args += [a.arg for a in node.args.kwonlyargs]
        if node.args.kwarg:
            args.append("**" + node.args.kwarg.arg)
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        return f"{prefix}{node.name}({', '.join(args)})"
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(b) for b in node.bases]
        return f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
    return ""


def _identifiers(node: ast.AST) -> list[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            names.add(sub.attr)
        elif isinstance(sub, ast.arg):
            names.add(sub.arg)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(sub.name)
        elif isinstance(sub, ast.keyword) and sub.arg:
            names.add(sub.arg)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            # String literals carry meaning ("PaymentDeclined", "free_shipping").
            if len(sub.value) <= 40:
                names.add(sub.value)
    return sorted(names)


def _slice(source_lines: list[str], start: int, end: int) -> str:
    return "\n".join(source_lines[start - 1 : end])


def _node_span(node: ast.AST) -> tuple[int, int]:
    start = node.lineno
    for dec in getattr(node, "decorator_list", []):
        start = min(start, dec.lineno)
    return start, node.end_lineno or start


def index_file(path: Path, root: Path) -> list[Chunk]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    chunks: list[Chunk] = []

    def emit(node: ast.AST, kind: str, name: str, qual: str) -> None:
        start, end = _node_span(node)
        src = _slice(lines, start, end)
        chunks.append(
            Chunk(
                id=f"{rel}::{qual}",
                path=rel,
                line_start=start,
                line_end=end,
                kind=kind,
                name=name,
                signature=_signature(node, lines),
                docstring=ast.get_docstring(node) if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ) else None,
                source=src,
                identifiers=tuple(_identifiers(node)),
                hash=sha256(src),
            )
        )

    const_run: list[ast.stmt] = []

    def flush_constants() -> None:
        if not const_run:
            return
        start = const_run[0].lineno
        end = const_run[-1].end_lineno or start
        src = _slice(lines, start, end)
        names = []
        for stmt in const_run:
            if isinstance(stmt, ast.Assign):
                names += [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                names.append(stmt.target.id)
        label = "+".join(names[:3]) or f"const_{start}"
        chunks.append(
            Chunk(
                id=f"{rel}::<constants:{label}>",
                path=rel,
                line_start=start,
                line_end=end,
                kind="constants",
                name=label,
                signature=", ".join(names),
                docstring=None,
                source=src,
                identifiers=tuple(sorted(set(names))),
                hash=sha256(src),
            )
        )
        const_run.clear()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            flush_constants()
            emit(node, "function", node.name, node.name)
        elif isinstance(node, ast.ClassDef):
            flush_constants()
            emit(node, "class", node.name, node.name)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    emit(sub, "method", sub.name, f"{node.name}.{sub.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            const_run.append(node)
        else:
            flush_constants()
    flush_constants()

    return chunks


def index_repo_verbose(root: Path) -> tuple[list[Chunk], list[str], int]:
    """Index the repo, reporting files that could not be parsed.

    An unparseable file is not fatal — the rest of the repo is still checkable —
    but it silently removes code from consideration, so the caller gets told.
    """
    root = Path(root).resolve()
    chunks: list[Chunk] = []
    unreadable: list[str] = []
    files = iter_python_files(root)
    for f in files:
        produced = index_file(f, root)
        if not produced and _is_unparseable(f):
            unreadable.append(f.relative_to(root).as_posix())
        chunks.extend(produced)
    return chunks, unreadable, len(files)


def _is_unparseable(path: Path) -> bool:
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return True
    return False


def index_repo(root: Path) -> list[Chunk]:
    chunks, _, _ = index_repo_verbose(root)
    return chunks

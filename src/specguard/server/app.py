"""FastAPI app: the dashboard, the report API, and the live event stream."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..config import Config, load_config
from ..engine import make_run_id, run_check
from ..report import git_state, utc_now, write_report

STATIC = Path(__file__).parent / "static"


class Hub:
    """Fan-out of pipeline events to every connected dashboard."""

    def __init__(self) -> None:
        self.subscribers: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def publish_threadsafe(self, event: str, data: dict[str, Any]) -> None:
        """Called from the worker thread; hands the event to the event loop."""
        if self.loop is None:
            return
        payload = (event, data)
        self.loop.call_soon_threadsafe(self._deliver, payload)

    def _deliver(self, payload: tuple[str, dict[str, Any]]) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass


def create_app(cfg: Config, provider: str | None = None) -> FastAPI:
    app = FastAPI(title="SpecGuard", docs_url=None, redoc_url=None)
    hub = Hub()
    state: dict[str, Any] = {"report": None, "running": False, "run_id": None}

    if cfg.report_path.exists():
        try:
            state["report"] = json.loads(cfg.report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state["report"] = None

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # ---------------------------------------------------------------- pages

    @app.get("/")
    def dashboard() -> FileResponse:
        return FileResponse(STATIC / "dashboard.html")

    # ------------------------------------------------------------------ api

    @app.get("/api/report")
    def get_report() -> dict[str, Any]:
        if state["report"] is None:
            return {"status": "empty"}
        return state["report"]

    @app.get("/api/repo/state")
    def repo_state() -> dict[str, Any]:
        return {
            "path": str(cfg.root),
            "name": cfg.root.name,
            "spec": cfg.spec_path,
            "running": state["running"],
            **git_state(cfg.root),
        }

    @app.get("/api/rule/{rule_id}")
    def get_rule(rule_id: str) -> dict[str, Any]:
        report = state["report"]
        if report is None:
            raise HTTPException(404, "no run yet")
        rid = rule_id.upper()
        for v in report["verdicts"]:
            if v["rule_id"] == rid:
                return {**v, "evidence": [_hydrate(cfg.root, e) for e in v["evidence"]]}
        for u in report.get("unverifiable_rules", []):
            if u["id"] == rid:
                return {**u, "verdict": "UNVERIFIABLE", "evidence": []}
        raise HTTPException(404, f"no rule {rid}")

    @app.post("/api/check")
    async def start_check() -> dict[str, Any]:
        if state["running"]:
            return {"run_id": state["run_id"], "status": "already_running"}

        hub.loop = asyncio.get_running_loop()
        run_id = make_run_id(utc_now())
        state["running"] = True
        state["run_id"] = run_id

        def worker() -> None:
            try:
                report = run_check(
                    cfg,
                    provider=provider,
                    emit=hub.publish_threadsafe,
                    run_id=run_id,
                )
                write_report(report, cfg.report_path)
                state["report"] = report
            except Exception as exc:  # a crashed run must still release the UI
                hub.publish_threadsafe("run_failed", {"run_id": run_id, "error": str(exc)})
            finally:
                state["running"] = False

        threading.Thread(target=worker, daemon=True, name="specguard-run").start()
        return {"run_id": run_id, "status": "started"}

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        hub.loop = asyncio.get_running_loop()
        queue = hub.subscribe()

        async def stream():
            yield ": connected\n\n"
            try:
                while True:
                    try:
                        event, data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
            finally:
                hub.unsubscribe(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _hydrate(root: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    """Re-read the cited lines from disk so the panel shows real file content."""
    out = dict(evidence)
    path = root / evidence["path"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        out["lines"] = []
        out["stale"] = True
        return out

    start, end = evidence["line_start"], evidence["line_end"]
    window = [
        {"n": n, "text": lines[n - 1], "cited": start <= n <= end}
        for n in range(max(1, start - 2), min(len(lines), end + 2) + 1)
    ]
    out["lines"] = window
    on_disk = "\n".join(lines[start - 1 : end])
    out["stale"] = on_disk.strip() != (evidence.get("snippet") or "").strip()
    return out


def app_from_env() -> FastAPI:  # pragma: no cover - `python -m specguard.server.app`
    import os

    return create_app(load_config(Path(os.environ.get("SPECGUARD_ROOT", "."))))


if __name__ == "__main__":  # pragma: no cover
    import os

    import uvicorn

    uvicorn.run(
        app_from_env(),
        host="127.0.0.1",
        port=int(os.environ.get("SPECGUARD_PORT", "8000")),
        log_level="warning",
    )

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from vaiiixbr.config import Settings
from vaiiixbr.runtime.embedded_worker import EmbeddedWorker
from vaiiixbr.services import EngineService
from vaiiixbr.storage.repository import Repository
from vaiiixbr.storage.sqlite_store import SQLiteStore

settings = Settings()
store = SQLiteStore(settings)
repository = Repository(store)
engine = EngineService(settings, repository)
embedded_worker = EmbeddedWorker(engine, settings.worker_poll_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.embedded_worker_enabled:
        embedded_worker.start()
    try:
        yield
    finally:
        if settings.embedded_worker_enabled:
            embedded_worker.stop()


app = FastAPI(title="VAIIIxBR API", version="1.2.0", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


@app.get("/health")
def health() -> dict[str, object]:
    status_payload = repository.get_status()
    return {
        "status": "ok",
        "service": "vaiiixbr",
        "asset": settings.asset,
        "embedded_worker": embedded_worker.snapshot(),
        "has_status": bool(status_payload),
    }


@app.get("/status")
def status() -> dict:
    payload = repository.get_status()
    if payload:
        payload.setdefault("runtime", {})
        payload["runtime"].update(embedded_worker.snapshot())
        return payload
    return {
        "asset": settings.asset,
        "interval": settings.interval,
        "runtime": embedded_worker.snapshot(),
        "message": "Aguardando primeiro ciclo do worker.",
    }


@app.get("/metrics")
def metrics() -> dict[str, object]:
    return {
        "asset": settings.asset,
        "signals": repository.signal_metrics(),
        "trades": repository.trade_metrics(),
        "runtime": embedded_worker.snapshot(),
    }


@app.get("/signals")
def signals(limit: int = 20) -> list[dict]:
    return repository.list_signals(limit=max(1, min(limit, 200)))


@app.get("/paper-trades")
def paper_trades(limit: int = 20) -> list[dict]:
    return repository.list_paper_trades(limit=max(1, min(limit, 200)))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    current_status = status()
    recent_signals = repository.list_signals(limit=10)
    recent_trades = repository.list_paper_trades(limit=10)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "status": current_status,
            "signal": current_status.get("signal", {}),
            "paper": current_status.get("paper", {}),
            "signal_metrics": current_status.get("metrics", {}).get("signals", repository.signal_metrics()),
            "trade_metrics": current_status.get("metrics", {}).get("trades", repository.trade_metrics()),
            "runtime": current_status.get("runtime", embedded_worker.snapshot()),
            "recent_signals": recent_signals,
            "recent_trades": recent_trades,
        },
    )


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse(
        {
            "message": "VAIIIxBR online",
            "dashboard": "/dashboard",
            "health": "/health",
            "status": "/status",
            "metrics": "/metrics",
            "paper_trades": "/paper-trades",
        }
    )

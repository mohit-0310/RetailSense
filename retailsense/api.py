from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from retailsense.agents import ask_retailsense
from retailsense.config import settings
from retailsense.repository import PreparedDataMissingError, default_repository
from retailsense.schemas import AskRequest, AskResponse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


app = FastAPI(title="RetailSense", version="0.1.0")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.middleware("http")
async def no_cache_frontend_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/")
def index() -> FileResponse:
    response = FileResponse(FRONTEND_DIR / "index.html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "RetailSense"}


@app.get("/api/agent-status")
def agent_status() -> dict:
    return {
        "mode": settings.agent_mode,
        "openai_api_key_present": bool(settings.openai_api_key),
        "use_openai_agents": settings.use_openai_agents,
        "model": settings.openai_model,
        "timeout_seconds": settings.agent_timeout_seconds,
    }


@app.get("/api/overview")
def overview() -> dict:
    try:
        return default_repository.overview()
    except PreparedDataMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/stores")
def stores() -> list[dict]:
    try:
        return default_repository.store_options()
    except PreparedDataMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/recommendations")
def recommendations(
    priority: str = Query("high", pattern="^(high|medium|low)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=50),
    store_id: str | None = None,
) -> dict:
    try:
        return default_repository.list_priority_recommendations(
            priority=priority,
            page=page,
            page_size=page_size,
            store_id=store_id,
        )
    except PreparedDataMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/items/{store_id}/{item_id}")
def item_detail(store_id: str, item_id: str) -> dict:
    try:
        return default_repository.inspect_item_signal(item_id=item_id, store_id=store_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PreparedDataMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> dict:
    try:
        return await ask_retailsense(
            question=request.question,
            item_id=request.item_id,
            store_id=request.store_id,
        )
    except PreparedDataMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

"""NewsVista API.

Public, read-only:  GET /health, /stories, /stories/{id}, /status
Protected:          POST /admin/collect   (Authorization: Bearer <ADMIN_TOKEN>)

GET endpoints only read stored results; they never fetch feeds or call the AI model.
"""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from . import views
from .ai import ask
from .ai.client import GeminiClient
from .config import load_model_config, settings
from .db import get_db
from .pipeline import CollectionJob, RunInProgress, default_services
from .timeutil import iso, utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("newsvista.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_db().create_all()  # idempotent; schema also in migrations/001_init.sql
    yield


app = FastAPI(
    lifespan=lifespan,
    title="NewsVista API",
    version="1.0.0",
    description="Stored, server-processed news stories: grouped coverage, background links and AI analysis.",
)

if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(OperationalError)
def _db_down(_: Request, exc: OperationalError):
    log.error("Database error: %s", exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"error": "database_unavailable",
                                                  "message": "The news database is temporarily unavailable."})


@app.exception_handler(Exception)
def _unexpected(_: Request, exc: Exception):
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": "Unexpected server error."})


@app.get("/")
def root():
    return {"service": "NewsVista API", "docs": "/docs", "endpoints": ["/health", "/stories", "/stories/{id}", "/status"]}


@app.get("/health")
def health():
    with get_db().session() as s:
        s.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok", "time": iso(utcnow())}


@app.get("/stories")
def stories(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_publishers: int = Query(1, ge=1, le=10, description="2 = only stories covered by several publishers"),
    category: str | None = Query(None, pattern="^(top|world|politics|us)$", description="Feed section"),
    q: str | None = Query(None, max_length=80, description="Search words in titles/excerpts"),
):
    with get_db().session() as s:
        return views.list_stories(s, settings, utcnow(), limit, offset, min_publishers, category, q)


@app.get("/stories/{story_id}")
def story(story_id: str):
    with get_db().session() as s:
        detail = views.story_detail(s, settings, utcnow(), story_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Story not found or all of its articles have expired.")
    return detail


@app.get("/status")
def status(runs: int = Query(20, ge=1, le=100)):
    with get_db().session() as s:
        return views.status_view(s, settings, utcnow(), runs)


class AskBody(BaseModel):
    question: str = Field(..., max_length=600)
    history: list[dict] = Field(default_factory=list, max_length=12)


_ask_limiter = ask.RateLimiter(settings.ask_per_client_limit, 300)


def ask_client():
    """Server-side Gemini client for Ask AI (None if no key). Tests replace this."""
    return GeminiClient(settings.gemini_api_key, load_model_config()) if settings.gemini_api_key else None


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _ask(request: Request, fn, *args):
    if not _ask_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="You're asking very quickly. Please wait a minute and try again.")
    try:
        with get_db().session() as s:
            return fn(s, settings, utcnow(), *args, ask_client(), load_model_config())
    except ask.AskError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@app.post("/stories/{story_id}/ask")
def ask_about_story(story_id: str, body: AskBody, request: Request):
    """Ask AI about one story. Answers come only from that story's stored coverage."""
    return _ask(request, ask.ask_story, story_id, body.question, body.history)


@app.post("/ask")
def ask_news(body: AskBody, request: Request):
    """Ask AI about recent news. Finds matching stories from the last 7 days, answers from them."""
    return _ask(request, ask.ask_global, body.question, body.history)


@app.post("/admin/collect")
def admin_collect(
    authorization: str = Header(default=""),
    x_trigger: str = Header(default="manual"),
    max_ai: int | None = Query(None, ge=0, le=40),
):
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="Admin collection is disabled (ADMIN_TOKEN not set).")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), settings.admin_token.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin token.")
    trigger = x_trigger if x_trigger in {"schedule", "workflow_dispatch", "manual"} else "manual"
    try:
        return CollectionJob(get_db(), default_services()).run(trigger, max_ai=max_ai)
    except RunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc))

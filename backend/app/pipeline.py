"""The hourly collection job.

Steps (each isolated so one failure cannot erase valid data):
  1. ingest      - fetch every feed independently; upsert articles by normalized URL
  2. retention   - delete articles published > 168h ago, invalidate AI analyses
                   that used them, delete stories left empty, drop orphan background links
  3. grouping    - assign new articles to existing stories or create new ones
  4. AI analysis - (re)generate analyses whose input fingerprint changed, within quota
  5. background  - find Wikipedia context for stories not yet checked
Every run is recorded in collection_runs / collection_run_sources.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import grouping
from .ai.analysis import InputArticle, load_system_prompt, prepare_input, validate
from .ai.client import AIError
from .background import BackgroundResult, candidates_for
from .config import Settings, load_model_config, load_sources, settings as default_settings
from .db import Database
from .feeds import FeedError, FeedResult, fetch_feed
from .models import (
    AIAnalysis,
    AIAnswer,
    AICallLog,
    Article,
    BackgroundLink,
    CollectionRun,
    CollectionRunSource,
    Source,
    Story,
    StoryArticle,
    StoryBackground,
)
from .normalize import article_id_for, content_hash, normalize_url
from .timeutil import utcnow, window_start

log = logging.getLogger("newsvista.pipeline")


class RunInProgress(Exception):
    pass


@dataclass
class Services:
    fetcher: Callable[[dict], FeedResult] | None = None
    ai_client: object | None = None  # has .generate(system, payload) and .last_model_used
    background_lookup: Callable[[list, list], list[BackgroundResult]] | None = None
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = utcnow
    sources: list[dict] | None = None
    model_config: dict = field(default_factory=load_model_config)


def story_id_for(seed_article_id: str) -> str:
    return "st_" + hashlib.sha256(seed_article_id.encode()).hexdigest()[:12]


def membership_fp(article_ids) -> str:
    return hashlib.sha256("|".join(sorted(article_ids)).encode()).hexdigest()


def to_input(a: Article) -> InputArticle:
    return InputArticle(a.id, a.publisher, a.title, a.published_at, a.excerpt, a.feed_text, a.content_hash)


def retained_members(session: Session, cutoff: datetime, story_ids: list[str] | None = None) -> dict[str, list[Article]]:
    q = (
        select(StoryArticle.story_id, Article)
        .join(Article, Article.id == StoryArticle.article_id)
        .where(Article.published_at >= cutoff)
    )
    if story_ids is not None:
        q = q.where(StoryArticle.story_id.in_(story_ids))
    out: dict[str, list[Article]] = defaultdict(list)
    for sid, art in session.execute(q):
        out[sid].append(art)
    return out


class CollectionJob:
    def __init__(self, db: Database, services: Services, cfg: Settings | None = None):
        self.db = db
        self.svc = services
        self.cfg = cfg or default_settings
        self.now = services.now()
        self.cutoff = window_start(self.now, self.cfg.retention_hours)

    # ------------------------------------------------------------------ run
    def run(self, trigger: str, max_ai: int | None = None) -> dict:
        with self.db.session() as s:
            stale = s.scalars(select(CollectionRun).where(CollectionRun.status == "running")).all()
            for r in stale:
                if r.started_at > self.now - timedelta(minutes=30):
                    raise RunInProgress(f"Run {r.id} started at {r.started_at.isoformat()} is still running")
                r.status, r.finished_at, r.error = "failed", self.now, "Abandoned (did not finish within 30 minutes)"
            run = CollectionRun(trigger=trigger, started_at=self.now, status="running")
            s.add(run)
            s.commit()
            run_id = run.id

        stats: dict = defaultdict(int)
        sources_ok = 0
        sources_total = 0
        error = None
        try:
            sources_ok, sources_total = self.ingest(run_id, stats)
            self.retention(stats)
            touched = self.group(stats)
            self.analyze(run_id, stats, max_ai)
            self.find_background(stats)
            if touched:
                log.info("Stories touched this run: %d", len(touched))
        except Exception as exc:  # never leave a run in "running"
            log.exception("Collection run %s crashed", run_id)
            error = f"{type(exc).__name__}: {exc}"[:1000]

        with self.db.session() as s:
            run = s.get(CollectionRun, run_id)
            for key, value in stats.items():
                if hasattr(run, key):
                    setattr(run, key, value)
            run.finished_at = self.svc.now()
            if error:
                run.status, run.error = "failed", error
            elif sources_ok == 0:
                run.status, run.error = "failed", "No feed could be collected"
            else:
                run.status = "success" if sources_ok == sources_total else "partial"
            s.commit()
            return run_summary(s, run)

    # --------------------------------------------------------------- ingest
    def ingest(self, run_id: int, stats: dict) -> tuple[int, int]:
        sources = self.svc.sources if self.svc.sources is not None else load_sources()
        fetcher = self.svc.fetcher or (lambda src: fetch_feed(src, self.cfg.feed_timeout_seconds))
        tolerance = timedelta(minutes=self.cfg.future_tolerance_minutes)
        ok = 0
        with self.db.session() as s:
            for src in sources:
                row = s.get(Source, src["id"])
                if row is None:
                    s.add(Source(id=src["id"], publisher=src["publisher"], name=src["name"], feed_url=src["feed_url"],
                                 homepage=src.get("homepage"), category=src.get("category", "top"), active=True,
                                 created_at=self.now))
                else:
                    row.publisher, row.name, row.feed_url, row.active = src["publisher"], src["name"], src["feed_url"], True
                    row.category = src.get("category", "top")
            s.commit()

        for src in sources:
            started = time.monotonic()
            c: dict[str, int] = defaultdict(int)  # merged into run stats only after commit
            result_row = CollectionRunSource(run_id=run_id, source_id=src["id"], status="failed",
                                             items_in_feed=0, new=0, updated=0, skipped=0)
            try:
                result = fetcher(src)
                result_row.http_status = result.http_status
                result_row.items_in_feed = len(result.items)
                with self.db.session() as s:
                    seen: dict[str, Article] = {}
                    for item in result.items:
                        c["articles_fetched"] += 1
                        if item.published_at is None:
                            c["skipped_invalid_date"] += 1
                            continue
                        if item.published_at > self.now + tolerance:
                            c["skipped_future"] += 1
                            continue
                        if item.published_at < self.cutoff:
                            c["skipped_too_old"] += 1
                            continue
                        nurl = normalize_url(item.url)
                        aid = article_id_for(nurl)
                        chash = content_hash(item.title, item.excerpt, item.feed_text)
                        art = seen.get(aid) or s.get(Article, aid)
                        if art is None:
                            art = Article(
                                id=aid, source_id=src["id"], publisher=src["publisher"], title=item.title,
                                url=item.url, normalized_url=nurl, guid=item.guid, published_at=item.published_at,
                                excerpt=item.excerpt, feed_text=item.feed_text,
                                content_kind="feed_partial_text" if item.feed_text else "feed_excerpt",
                                content_hash=chash, ingested_at=self.now, last_seen_at=self.now,
                                image_url=item.image_url, categories="",
                            )
                            s.add(art)
                            c["articles_new"] += 1
                        elif art.content_hash != chash or art.published_at != item.published_at:
                            art.title, art.excerpt, art.feed_text = item.title, item.excerpt, item.feed_text
                            art.published_at, art.content_hash, art.last_seen_at = item.published_at, chash, self.now
                            art.content_kind = "feed_partial_text" if item.feed_text else "feed_excerpt"
                            c["articles_updated"] += 1
                        else:
                            art.last_seen_at = self.now
                            c["articles_unchanged"] += 1
                        category = src.get("category", "top")
                        if f",{category}," not in (art.categories or ""):
                            art.categories = (art.categories or ",") + f"{category},"
                        if item.image_url and not art.image_url:
                            art.image_url = item.image_url
                        seen[aid] = art
                    s.commit()
                for key, value in c.items():
                    stats[key] += value
                result_row.new, result_row.updated = c["articles_new"], c["articles_updated"]
                result_row.skipped = c["skipped_invalid_date"] + c["skipped_future"] + c["skipped_too_old"]
                result_row.status = "ok"
                ok += 1
            except FeedError as exc:
                result_row.http_status = exc.http_status
                result_row.error = str(exc)[:500]
            except Exception as exc:  # isolate any per-source problem
                log.exception("Source %s failed", src["id"])
                result_row.error = f"{type(exc).__name__}: {exc}"[:500]
            result_row.duration_ms = int((time.monotonic() - started) * 1000)
            with self.db.session() as s:
                s.add(result_row)
                s.commit()
        return ok, len(sources)

    # ------------------------------------------------------------ retention
    def retention(self, stats: dict) -> None:
        with self.db.session() as s:
            expired_ids = set(s.scalars(select(Article.id).where(Article.published_at < self.cutoff)))
            if expired_ids:
                # Cached Ask AI answers that used an expiring article must go too.
                affected = {f"story:{sid}" for sid in s.scalars(
                    select(StoryArticle.story_id).where(StoryArticle.article_id.in_(expired_ids)))}
                if affected:
                    s.execute(delete(AIAnswer).where(AIAnswer.scope.in_(affected)))
                s.execute(delete(AIAnswer).where(AIAnswer.scope == "global"))
                for analysis in s.scalars(select(AIAnalysis)).all():
                    used = set(json.loads(analysis.input_article_ids or "[]"))
                    if used & expired_ids:
                        # Never keep a summary that depends on removed articles.
                        analysis.content_json = None
                        analysis.status = "pending"
                        analysis.fingerprint = None
                        analysis.input_article_ids = "[]"
                        analysis.needs_review = False
                        analysis.review_notes = "[]"
                        analysis.error = None
                        stats["analyses_invalidated"] += 1
                s.execute(delete(StoryArticle).where(StoryArticle.article_id.in_(expired_ids)))
                s.execute(delete(Article).where(Article.id.in_(expired_ids)))
                stats["articles_expired"] = len(expired_ids)
            # Stories with no remaining articles go, with their analysis and background associations.
            empty = s.scalars(
                select(Story).where(~select(StoryArticle.id).where(StoryArticle.story_id == Story.id).exists())
            ).all()
            for story in empty:
                s.delete(story)
            stats["stories_deleted"] = len(empty)
            s.flush()
            # Old cached answers (inputs likely changed) and answers for deleted stories.
            s.execute(delete(AIAnswer).where(AIAnswer.created_at < self.now - timedelta(hours=24)))
            s.execute(delete(AIAnswer).where(AIAnswer.scope.like("story:%"),
                                             ~AIAnswer.scope.in_(select("story:" + Story.id))))
            # Background resources are kept only while linked to an active story.
            s.execute(
                delete(BackgroundLink).where(~BackgroundLink.id.in_(select(StoryBackground.background_id)))
            )
            s.commit()

    # ------------------------------------------------------------- grouping
    def group(self, stats: dict) -> set[str]:
        with self.db.session() as s:
            articles = s.scalars(select(Article).where(Article.published_at >= self.cutoff)).all()
            membership = dict(s.execute(select(StoryArticle.article_id, StoryArticle.story_id)).all())
            feats = {
                a.id: grouping.build_features(a.id, a.publisher, a.published_at, a.title, a.excerpt, a.feed_text)
                for a in articles
            }
            idf = grouping.compute_idf(list(feats.values()))
            for f in feats.values():
                f.vector = grouping.vectorize(f, idf)
            existing = [(feats[aid], sid) for aid, sid in membership.items() if aid in feats]
            new = [feats[a.id] for a in articles if a.id not in membership]
            assignments = grouping.assign_articles(new, existing)

            by_id = {a.id: a for a in articles}
            touched: set[str] = set()
            new_story_ids: dict[str, str] = {}
            for asg in assignments:
                if asg.story_key.startswith("new:"):
                    sid = new_story_ids.setdefault(asg.story_key, story_id_for(asg.story_key[4:]))
                    if s.get(Story, sid) is None:
                        art = by_id[asg.article_id]
                        s.add(Story(id=sid, headline=art.title, headline_article_id=art.id, created_at=self.now,
                                    updated_at=self.now, latest_published_at=art.published_at))
                        s.flush()
                        stats["stories_created"] += 1
                else:
                    sid = asg.story_key
                    stats["stories_joined"] += 1
                s.add(StoryArticle(story_id=sid, article_id=asg.article_id, added_at=self.now,
                                   match_score=asg.score, matched_article_id=asg.matched_article_id))
                touched.add(sid)
            s.flush()

            # Refresh headline/latest time for stories whose membership changed,
            # including stories that lost expired members.
            members = retained_members(s, self.cutoff)
            for story in s.scalars(select(Story)).all():
                arts = members.get(story.id, [])
                if not arts:
                    continue
                latest = max(a.published_at for a in arts)
                if story.id in touched or story.headline_article_id not in {a.id for a in arts} \
                        or story.latest_published_at != latest:
                    pick = grouping.choose_headline([feats[a.id] for a in arts])
                    story.headline, story.headline_article_id = pick.title, pick.id
                    story.latest_published_at = latest
                    story.updated_at = self.now
            s.commit()
            return touched

    # ------------------------------------------------------------ AI
    def analyze(self, run_id: int, stats: dict, max_ai: int | None) -> None:
        cfg = self.svc.model_config
        client = self.svc.ai_client
        with self.db.session() as s:
            members = retained_members(s, self.cutoff)
            analyses = {a.story_id: a for a in s.scalars(select(AIAnalysis)).all()}
            stories = {st.id: st for st in s.scalars(select(Story)).all()}
            todo = []
            for sid, arts in members.items():
                inputs = [to_input(a) for a in arts]
                prepared = prepare_input(stories[sid].headline, inputs, cfg)
                current = analyses.get(sid)
                if current and current.fingerprint == prepared.fingerprint and current.status == "ok":
                    continue
                if (current and current.last_attempt_fp == prepared.fingerprint and current.last_attempt_at
                        and current.last_attempt_at > self.now - timedelta(hours=1)):
                    continue  # failed within the last hour on identical input; back off
                publishers = len({a.publisher for a in arts})
                todo.append((-publishers, -max(a.published_at for a in arts).timestamp(), sid, prepared))
            todo.sort(key=lambda t: (t[0], t[1], t[2]))

            if not client or not self.cfg.ai_enabled:
                stats["ai_deferred"] = len(todo)
                return
            budget = self.cfg.ai_max_per_run if max_ai is None else max_ai
            system_prompt = load_system_prompt(cfg)
            attempted = 0
            for _, _, sid, prepared in todo:
                if attempted >= budget:
                    break
                if attempted:
                    self.svc.sleep(cfg.get("seconds_between_calls", 0))
                attempted += 1
                analysis = analyses.get(sid)
                if analysis is None:
                    analysis = AIAnalysis(story_id=sid, status="pending", version=0)
                    s.add(analysis)
                    analyses[sid] = analysis
                started = time.monotonic()
                outcome, err = "ok", None
                try:
                    raw = client.generate(system_prompt, prepared.payload)
                    result = validate(raw, prepared)
                    analysis.status = "ok"
                    analysis.fingerprint = prepared.fingerprint
                    analysis.input_article_ids = json.dumps([a.id for a in prepared.articles])
                    analysis.input_scope = prepared.scope
                    analysis.model = getattr(client, "last_model_used", cfg["model"])
                    analysis.prompt_version = cfg["prompt_version"]
                    analysis.generated_at = self.svc.now()
                    analysis.content_json = json.dumps(result.content, ensure_ascii=False)
                    analysis.needs_review = result.needs_review
                    analysis.review_notes = json.dumps(result.notes, ensure_ascii=False)
                    analysis.error = None
                    analysis.version = (analysis.version or 0) + 1
                    stats["ai_generated"] += 1
                except (AIError, ValueError) as exc:
                    outcome = exc.kind if isinstance(exc, AIError) else "invalid_output"
                    err = str(exc)[:500]
                    if not analysis.content_json:
                        analysis.status = "failed"
                    analysis.error = f"{outcome}: {err}"
                    stats["ai_failed"] += 1
                analysis.last_attempt_at = self.svc.now()
                analysis.last_attempt_fp = prepared.fingerprint
                s.add(AICallLog(called_at=self.svc.now(), run_id=run_id, story_id=sid,
                                model=getattr(client, "last_model_used", cfg["model"]), outcome=outcome,
                                latency_ms=int((time.monotonic() - started) * 1000), error=err))
                s.commit()
                if outcome in {"quota", "auth", "disabled"}:
                    break  # further calls this run would fail the same way
            stats["ai_deferred"] = max(0, len(todo) - attempted)

    # ------------------------------------------------------------ background
    def find_background(self, stats: dict) -> None:
        lookup = self.svc.background_lookup
        if not lookup or not self.cfg.background_enabled:
            return
        with self.db.session() as s:
            members = retained_members(s, self.cutoff)
            stories = {st.id: st for st in s.scalars(select(Story)).all()}
            analyses = {a.story_id: a for a in s.scalars(select(AIAnalysis)).all()}
            todo = []
            for sid, arts in members.items():
                story = stories[sid]
                fp = membership_fp(a.id for a in arts)
                if story.background_checked_fp == fp:
                    continue
                if story.background_checked_fp is not None and story.background:
                    continue  # already has verified links; keep them
                todo.append((-len({a.publisher for a in arts}), -story.latest_published_at.timestamp(), sid, fp))
            todo.sort()
            for n, (_, _, sid, fp) in enumerate(todo[: self.cfg.background_max_per_run]):
                if n:
                    self.svc.sleep(1.0)  # be polite to Wikipedia (avoids HTTP 429)
                arts = members[sid]
                texts = [(a.title, a.excerpt) for a in arts]
                topics = []
                if sid in analyses and analyses[sid].content_json:
                    topics = json.loads(analyses[sid].content_json).get("background_topics", [])
                try:
                    found = lookup(candidates_for(texts, topics), texts)
                except Exception as exc:
                    log.warning("Background lookup failed for %s: %s", sid, str(exc)[:200])
                    if "429" in str(exc):
                        break  # rate limited: stop for this run, retry next run
                    continue  # retry next run
                story = stories[sid]
                for rank, res in enumerate(found):
                    link = s.scalars(select(BackgroundLink).where(BackgroundLink.url == res.url)).first()
                    if link is None:
                        link = BackgroundLink(url=res.url, title=res.title, description=res.description,
                                              provider="Wikipedia", thumbnail_url=res.thumbnail_url,
                                              fetched_at=self.now)
                        s.add(link)
                        s.flush()
                    if s.get(StoryBackground, (sid, link.id)) is None:
                        s.add(StoryBackground(story_id=sid, background_id=link.id, matched_term=res.matched_term,
                                              method=res.method, rank=rank, created_at=self.now))
                        stats["background_links_added"] += 1
                story.background_checked_fp = fp
                story.background_checked_at = self.now
                s.commit()


def run_summary(s: Session, run: CollectionRun) -> dict:
    fields = [
        "id", "trigger", "status", "articles_fetched", "articles_new", "articles_updated", "articles_unchanged",
        "skipped_invalid_date", "skipped_future", "skipped_too_old", "articles_expired", "stories_created",
        "stories_joined", "stories_deleted", "analyses_invalidated", "ai_generated", "ai_failed", "ai_deferred",
        "background_links_added", "error",
    ]
    out = {f: getattr(run, f) for f in fields}
    out["started_at"] = run.started_at.isoformat()
    out["finished_at"] = run.finished_at.isoformat() if run.finished_at else None
    out["sources"] = [
        {"source_id": r.source_id, "status": r.status, "http_status": r.http_status, "items_in_feed": r.items_in_feed,
         "new": r.new, "updated": r.updated, "skipped": r.skipped, "duration_ms": r.duration_ms, "error": r.error}
        for r in s.scalars(select(CollectionRunSource).where(CollectionRunSource.run_id == run.id)).all()
    ]
    return out


def default_services() -> Services:
    from .ai.client import GeminiClient
    from .background import lookup

    cfg = default_settings
    model_config = load_model_config()
    ai = GeminiClient(cfg.gemini_api_key, model_config) if cfg.gemini_api_key else None
    return Services(
        ai_client=ai,
        background_lookup=lambda cands, texts: lookup(cands, texts, cfg.wiki_user_agent),
        model_config=model_config,
    )

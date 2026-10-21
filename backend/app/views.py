"""Read-only views for the API. Nothing here fetches feeds or calls the AI model.

Expiration is enforced at query time: every query only sees articles published
inside the rolling window, even if the hourly cleanup has not run yet.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .ai.analysis import SCOPE_DISCLOSURES, fingerprint
from .config import Settings, load_model_config
from .feeds import phone_sized_image
from .models import AIAnalysis, AICallLog, Article, BackgroundLink, CollectionRun, CollectionRunSource, Story, StoryArticle, StoryBackground
from .pipeline import retained_members, to_input
from .timeutil import iso, window_start

NO_BACKGROUND = "No background resource available"


def last_successful_run(s: Session) -> CollectionRun | None:
    return s.scalars(
        select(CollectionRun)
        .where(CollectionRun.status.in_(["success", "partial"]))
        .order_by(CollectionRun.finished_at.desc())
        .limit(1)
    ).first()


def _analysis_state(analysis: AIAnalysis | None, arts: list[Article], prompt_version: str) -> tuple[str, str]:
    """Return (status, message) for the stored analysis against the CURRENT retained articles."""
    if analysis is None or (not analysis.content_json and not analysis.error):
        return "pending", ("AI analysis has not been generated for this story yet. Analyses are produced by the "
                           "hourly server job, not when you open the app.")
    if not analysis.content_json:
        return "failed", ("AI analysis is temporarily unavailable because the last generation attempt failed. "
                          "Original coverage is still available below.")
    used = set(json.loads(analysis.input_article_ids or "[]"))
    retained = {a.id for a in arts}
    if not used <= retained:
        return "expired_inputs", ("Some articles this analysis relied on have expired (older than 7 days), so it is "
                                  "hidden. A new analysis will be generated on a later server run.")
    current_fp = fingerprint([to_input(a) for a in arts], prompt_version)
    if analysis.fingerprint == current_fp:
        return "current", "AI analysis is up to date with the coverage listed for this story."
    newer = len(retained - used)
    if newer:
        return "outdated", (f"Generated before {newer} newer article(s) joined this story. An updated analysis is "
                            "queued for a later server run.")
    return "outdated", "Source coverage changed after this analysis was generated. An update is queued."


def analysis_view(analysis: AIAnalysis | None, arts: list[Article], prompt_version: str) -> dict:
    status, message = _analysis_state(analysis, arts, prompt_version)
    view: dict = {
        "label": "AI-generated",
        "status": status,
        "status_message": message,
        "analysis_id": analysis.id if analysis else None,
        "version": analysis.version if analysis else 0,
        "generated_at": iso(analysis.generated_at) if analysis else None,
        "model": analysis.model if analysis else None,
        "prompt_version": analysis.prompt_version if analysis else None,
        "content": None,
    }
    if status not in {"current", "outdated"}:
        return view
    used_ids = json.loads(analysis.input_article_ids)
    by_id = {a.id: a for a in arts}
    numbered = {aid: i for i, aid in enumerate(used_ids, start=1)}
    content = json.loads(analysis.content_json)

    def cites(ids: list[str]) -> list[int]:
        return [numbered[i] for i in ids if i in numbered]

    def items(section: list[dict]) -> list[dict]:
        return [{"text": it["text"], "citations": cites(it["citations"])} for it in section]

    pubs = {by_id[i].publisher for i in used_ids}
    view["content"] = {
        "overview": {"text": content["overview"]["text"], "citations": cites(content["overview"]["citations"]),
                     "flag": content["overview"].get("flag")},
        "key_points": items(content.get("key_points", [])),
        "agreements": items(content["agreements"]),
        "disagreements": items(content["disagreements"]),
        "uncertainties": items(content["uncertainties"]),
        "perspectives_status": content["perspectives_status"],
        "perspectives_message": content.get("perspectives_message"),
        "perspectives": [
            {"id": p["id"], "name": p["name"], "summary": p["summary"], "caveats": p["caveats"],
             "claims": items(p["claims"])}
            for p in content["perspectives"]
        ],
        "limitations": content["limitations"],
        "input_scope": {
            "kind": analysis.input_scope,
            "article_count": len(used_ids),
            "publisher_count": len(pubs),
            "disclosure": SCOPE_DISCLOSURES.get(analysis.input_scope, ""),
        },
        "needs_review": analysis.needs_review,
        "review_notes": json.loads(analysis.review_notes or "[]"),
        "citations": [
            {"number": numbered[aid], "article_id": aid, "publisher": by_id[aid].publisher,
             "title": by_id[aid].title, "url": by_id[aid].url, "published_at": iso(by_id[aid].published_at)}
            for aid in used_ids
        ],
    }
    return view


def _lead(story: Story, arts: list[Article]) -> Article:
    """Headline article if still retained, else the newest retained article."""
    for a in arts:
        if a.id == story.headline_article_id:
            return a
    return max(arts, key=lambda a: a.published_at)


def _image(story: Story, arts: list[Article]) -> str | None:
    lead = _lead(story, arts)
    if lead.image_url:
        return phone_sized_image(lead.image_url)
    with_image = [a for a in arts if a.image_url]
    return phone_sized_image(max(with_image, key=lambda a: a.published_at).image_url) if with_image else None


def _categories(arts: list[Article]) -> list[str]:
    return sorted({c for a in arts for c in (a.categories or "").split(",") if c})


def _headline(story: Story, arts: list[Article]) -> str:
    ids = {a.id: a for a in arts}
    if story.headline_article_id in ids:
        return story.headline
    # Headline article expired since the last run: use the newest retained title.
    return max(arts, key=lambda a: a.published_at).title


def _extra_having(category: str | None, q: str | None) -> list:
    """Optional filters, evaluated over a story's retained articles."""
    conds = []
    if category:
        conds.append(func.max(case((Article.categories.like(f"%,{category},%"), 1), else_=0)) == 1)
    for word in (q or "").split()[:5]:
        pattern = f"%{word.lower()}%"
        conds.append(func.max(case((func.lower(Article.title).like(pattern), 1),
                                   (func.lower(Article.excerpt).like(pattern), 1), else_=0)) == 1)
    return conds


def list_stories(s: Session, cfg: Settings, now: datetime, limit: int, offset: int, min_publishers: int,
                 category: str | None = None, q: str | None = None) -> dict:
    cutoff = window_start(now, cfg.retention_hours)
    prompt_version = load_model_config()["prompt_version"]
    agg = (
        select(
            StoryArticle.story_id.label("sid"),
            func.max(Article.published_at).label("latest"),
            func.count(func.distinct(Article.publisher)).label("pubs"),
            func.count(Article.id).label("n"),
        )
        .join(Article, Article.id == StoryArticle.article_id)
        .where(Article.published_at >= cutoff)
        .group_by(StoryArticle.story_id)
        .having(*_extra_having(category, q))
        .having(func.count(func.distinct(Article.publisher)) >= min_publishers)
        .subquery()
    )
    total = s.scalar(select(func.count()).select_from(agg))
    rows = s.execute(select(agg).order_by(agg.c.latest.desc(), agg.c.sid).limit(limit).offset(offset)).all()
    ids = [r.sid for r in rows]
    members = retained_members(s, cutoff, ids)
    stories = {st.id: st for st in s.scalars(select(Story).where(Story.id.in_(ids)))}
    analyses = {a.story_id: a for a in s.scalars(select(AIAnalysis).where(AIAnalysis.story_id.in_(ids)))}
    items = []
    for r in rows:
        arts = members[r.sid]
        story = stories[r.sid]
        status, _ = _analysis_state(analyses.get(r.sid), arts, prompt_version)
        items.append({
            "id": r.sid,
            "headline": _headline(story, arts),
            "latest_published_at": iso(max(a.published_at for a in arts)),
            "updated_at": iso(story.updated_at),
            "publisher_count": len({a.publisher for a in arts}),
            "article_count": len(arts),
            "publishers": sorted({a.publisher for a in arts}),
            "categories": _categories(arts),
            "summary": _lead(story, arts).excerpt,
            "summary_label": f"Excerpt from {_lead(story, arts).publisher} (original wording)",
            "image_url": _image(story, arts),
            "ai_status": status,
        })
    last = last_successful_run(s)
    return {
        "served_at": iso(now),
        "window_hours": cfg.retention_hours,
        "ordering": "newest first (by latest article publication time)",
        "last_successful_collection_at": iso(last.finished_at) if last else None,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {"min_publishers": min_publishers, "category": category, "q": q},
        "items": items,
    }


def story_detail(s: Session, cfg: Settings, now: datetime, story_id: str) -> dict | None:
    cutoff = window_start(now, cfg.retention_hours)
    story = s.get(Story, story_id)
    if story is None:
        return None
    arts = retained_members(s, cutoff, [story_id]).get(story_id, [])
    if not arts:
        return None  # every article expired: the story is no longer served
    prompt_version = load_model_config()["prompt_version"]
    analysis = s.scalars(select(AIAnalysis).where(AIAnalysis.story_id == story_id)).first()
    analysis_json = analysis_view(analysis, arts, prompt_version)

    by_pub: dict[str, list[Article]] = defaultdict(list)
    for a in arts:
        by_pub[a.publisher].append(a)
    publishers = [
        {
            "publisher": pub,
            "article_count": len(items),
            "articles": [
                {"id": a.id, "title": a.title, "url": a.url, "published_at": iso(a.published_at),
                 "image_url": phone_sized_image(a.image_url),
                 "excerpt": a.excerpt, "excerpt_label": f"Excerpt from {pub}'s RSS feed (original wording)"}
                for a in sorted(items, key=lambda a: a.published_at, reverse=True)
            ],
        }
        for pub, items in sorted(by_pub.items(), key=lambda kv: kv[0])
    ]

    if analysis_json["content"]:
        overview = {"kind": "ai_generated", "label": "AI-generated overview",
                    "text": analysis_json["content"]["overview"]["text"],
                    "generated_at": analysis_json["generated_at"]}
    else:
        lead = next((a for a in arts if a.id == story.headline_article_id), max(arts, key=lambda a: a.published_at))
        overview = {"kind": "publisher_excerpt", "label": f"Publisher excerpt — {lead.publisher} (original wording)",
                    "text": lead.excerpt or lead.title, "generated_at": None}

    bg_rows = s.execute(
        select(StoryBackground, BackgroundLink)
        .join(BackgroundLink, BackgroundLink.id == StoryBackground.background_id)
        .where(StoryBackground.story_id == story_id)
        .order_by(StoryBackground.rank)
    ).all()
    links = [
        {"title": link.title, "description": link.description, "url": link.url, "provider": link.provider,
         "thumbnail_url": link.thumbnail_url,
         "matched_term": sb.matched_term, "method": sb.method}
        for sb, link in bg_rows
    ]
    if links:
        background = {"status": "available", "message": None, "links": links}
    elif story.background_checked_at:
        background = {"status": "none", "message": NO_BACKGROUND, "links": []}
    else:
        background = {"status": "pending", "message": NO_BACKGROUND + " yet — the server has not searched for "
                      "background on this story.", "links": []}

    last = last_successful_run(s)
    return {
        "id": story.id,
        "headline": _headline(story, arts),
        "created_at": iso(story.created_at),
        "updated_at": iso(story.updated_at),
        "latest_published_at": iso(max(a.published_at for a in arts)),
        "publisher_count": len(by_pub),
        "article_count": len(arts),
        "image_url": _image(story, arts),
        "categories": _categories(arts),
        "overview": overview,
        "publishers": publishers,
        "background": background,
        "analysis": analysis_json,
        "window_hours": cfg.retention_hours,
        "last_successful_collection_at": iso(last.finished_at) if last else None,
        "served_at": iso(now),
    }


def status_view(s: Session, cfg: Settings, now: datetime, runs_limit: int = 20) -> dict:
    cutoff = window_start(now, cfg.retention_hours)
    runs = s.scalars(select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(runs_limit)).all()
    run_ids = [r.id for r in runs]
    per_source = defaultdict(list)
    for r in s.scalars(select(CollectionRunSource).where(CollectionRunSource.run_id.in_(run_ids))):
        per_source[r.run_id].append({"source_id": r.source_id, "status": r.status, "new": r.new,
                                     "items_in_feed": r.items_in_feed, "error": r.error})
    last = last_successful_run(s)
    model_config = load_model_config()
    analyses = s.scalars(select(AIAnalysis)).all()
    return {
        "served_at": iso(now),
        "last_successful_collection_at": iso(last.finished_at) if last else None,
        "window_hours": cfg.retention_hours,
        "counts": {
            "articles_in_window": s.scalar(select(func.count()).select_from(Article).where(Article.published_at >= cutoff)),
            "stories": s.scalar(select(func.count()).select_from(Story)),
            "background_links": s.scalar(select(func.count()).select_from(BackgroundLink)),
        },
        "ai": {
            "configured": bool(cfg.gemini_api_key) and cfg.ai_enabled,
            "model": model_config["model"],
            "prompt_version": model_config["prompt_version"],
            "max_calls_per_run": cfg.ai_max_per_run,
            "analyses_ok": sum(1 for a in analyses if a.content_json),
            "analyses_failed": sum(1 for a in analyses if not a.content_json and a.error),
            "analyses_needing_review": sum(1 for a in analyses if a.content_json and a.needs_review),
            "model_calls_total": s.scalar(select(func.count()).select_from(AICallLog)),
            "ask_calls_last_24h": s.scalar(select(func.count()).select_from(AICallLog).where(
                AICallLog.story_id.like("ask%"), AICallLog.called_at >= now - timedelta(hours=24))),
            "ask_daily_limit": cfg.ask_daily_limit,
            "model_calls_last_24h": s.scalar(
                select(func.count()).select_from(AICallLog).where(AICallLog.called_at >= now - timedelta(hours=24))),
        },
        "runs": [
            {
                "id": r.id, "trigger": r.trigger, "status": r.status, "started_at": iso(r.started_at),
                "finished_at": iso(r.finished_at), "articles_fetched": r.articles_fetched,
                "articles_new": r.articles_new, "articles_updated": r.articles_updated,
                "articles_expired": r.articles_expired, "stories_created": r.stories_created,
                "stories_deleted": r.stories_deleted, "ai_generated": r.ai_generated, "ai_failed": r.ai_failed,
                "ai_deferred": r.ai_deferred, "background_links_added": r.background_links_added,
                "error": r.error, "sources": per_source.get(r.id, []),
            }
            for r in runs
        ],
    }

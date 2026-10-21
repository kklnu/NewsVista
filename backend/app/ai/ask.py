"""Ask AI: reader questions answered on the server from stored coverage.

Two scopes:
  - story:  answers from one story's retained articles + background descriptions
  - global: finds the best-matching stories of the last 7 days, answers from them

Guardrails (documented in README "Ask AI assistant"):
  - The model is called only by the server; the key never reaches the app.
  - Answers must cite the supplied labels; unknown labels are dropped.
  - Quotes/numbers not found in the inputs are flagged in the reply.
  - Optional "general_context" (model's general knowledge) is returned separately
    and labelled in the app as NOT coming from the collected coverage.
  - Identical first questions on unchanged inputs reuse a cached answer.
  - Per-client and daily limits protect the quota used by the hourly analyses.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import AI_CONFIG_DIR, Settings
from ..grouping import tokens
from ..models import AIAnalysis, AIAnswer, AICallLog, Article, BackgroundLink, Story, StoryArticle, StoryBackground
from ..timeutil import iso, window_start
from .analysis import InputArticle, fingerprint, select_inputs
from .client import AIError

ASK_PROMPT_VERSION = "ask-v1"
MAX_QUESTION_CHARS = 300
MAX_HISTORY_TURNS = 4
NO_COVERAGE = ("NewsVista has no coverage matching that question from the last 7 days. "
               "Try different words, or browse the Top Stories list.")

ASK_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "answer": {"type": "STRING"},
        "citations": {"type": "ARRAY", "items": {"type": "STRING"}},
        "general_context": {"type": "STRING"},
        "follow_up_questions": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["answer", "citations", "general_context", "follow_up_questions"],
}


class AskError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class RateLimiter:
    """In-memory sliding window per client (resets on restart; fine for a beta)."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit, self.window = limit, window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def _prompt(name: str) -> str:
    return (AI_CONFIG_DIR / name).read_text(encoding="utf-8")


def question_key(question: str) -> str:
    q = re.sub(r"\s+", " ", question.lower()).strip()
    return re.sub(r"[?.!\s]+$", "", q)[:MAX_QUESTION_CHARS]


def clean_question(question: str) -> str:
    q = re.sub(r"\s+", " ", question or "").strip()
    if len(q) < 3:
        raise AskError(422, "Please type a question.")
    if len(q) > MAX_QUESTION_CHARS:
        raise AskError(422, f"Questions are limited to {MAX_QUESTION_CHARS} characters.")
    return q


def clean_history(history: list | None) -> list[dict]:
    out = []
    for turn in (history or [])[-MAX_HISTORY_TURNS * 2:]:
        role = turn.get("role") if isinstance(turn, dict) else None
        text = str(turn.get("text", ""))[:800] if isinstance(turn, dict) else ""
        if role in {"user", "assistant"} and text.strip():
            out.append({"role": role, "text": text})
    return out


_QUOTE = re.compile(r"[\"“”]([^\"“”]{12,}?)[\"“”]")
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).lower()


def _unsupported(answer: str, corpus: str) -> str | None:
    answer = re.sub(r"\[\d+\]", "", answer)  # our own citation markers are not claims
    corpus_n = _norm(corpus)
    numbers = {n.replace(",", "") for n in _NUMBER.findall(corpus_n)}
    for quote in _QUOTE.findall(answer):
        if _norm(quote).strip(" .,'") not in corpus_n:
            return f'the quotation "{quote[:50]}" was not found in the sources'
    for num in _NUMBER.findall(answer):
        if num.replace(",", "") not in numbers:
            return f"the number {num} was not found in the sources"
    return None


def _daily_guard(s: Session, cfg: Settings, now: datetime) -> None:
    used = s.scalar(
        select(func.count()).select_from(AICallLog)
        .where(AICallLog.story_id.like("ask%"), AICallLog.called_at >= now - timedelta(hours=24))
    )
    if used >= cfg.ask_daily_limit:
        raise AskError(429, "The AI assistant has reached today's question limit. Please try again tomorrow.")


def _call(s: Session, client, system: str, payload: str, log_id: str, now: datetime) -> dict:
    started = time.monotonic()
    model = getattr(client, "model", "unknown")
    try:
        raw = client.generate(system, payload, ASK_SCHEMA)
        outcome, err = "ok", None
    except AIError as exc:
        raw, outcome, err = None, exc.kind, str(exc)[:500]
    s.add(AICallLog(called_at=now, run_id=None, story_id=log_id[:32],
                    model=getattr(client, "last_model_used", model), outcome=outcome,
                    latency_ms=int((time.monotonic() - started) * 1000), error=err))
    s.commit()
    if raw is None:
        raise AskError(503, "The AI assistant is busy right now. Please try again in a minute.")
    if not isinstance(raw, dict) or not str(raw.get("answer", "")).strip():
        raise AskError(502, "The AI assistant returned an unusable answer. Please try rephrasing.")
    return raw


_LABEL = re.compile(r"\b([ABS]\d{1,2})\b")
_PAREN_GROUP = re.compile(r"\(\s*((?:\[\d+\][,;\s]*(?:and\s*)?)+)\)")
_NO_SOURCE_PHRASES = ("doesn't say", "does not say", "can only help", "no coverage", "not mentioned",
                      "isn't mentioned", "is not mentioned")


def renumber_labels(answer: str, citations: list[dict]) -> str:
    """Show the model's inline labels (A1, S6) as the app's citation numbers ([1], [4])."""
    number = {c["label"]: c["number"] for c in citations}

    def repl(m: re.Match) -> str:
        return f"[{number[m.group(1)]}]" if m.group(1) in number else ""

    text = _LABEL.sub(repl, answer)
    text = _PAREN_GROUP.sub(lambda m: " " + "".join(re.findall(r"\[\d+\]", m.group(1))), text)
    text = re.sub(r"\(\s*[,;\s]*\)", "", text)  # "( , )" left by uncited labels
    return re.sub(r"\s+([.,;])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()


def _no_source_needed(answer: str) -> bool:
    low = answer.lower()
    return any(p in low for p in _NO_SOURCE_PHRASES)


def _reply(answer: str, citations: list[dict], raw: dict, flag: str | None, model: str, cached: bool,
           generated_at: datetime, scope: str) -> dict:
    return {
        "label": "AI-generated",
        "scope": scope,
        "answer": answer,
        "citations": citations,
        "general_context": str(raw.get("general_context", "")).strip()[:600] or None,
        "general_context_label": "General background from the AI model — not from the collected coverage",
        "follow_up_questions": [str(q).strip() for q in raw.get("follow_up_questions") or [] if str(q).strip()][:3],
        "flag": flag,
        "model": model,
        "cached": cached,
        "generated_at": iso(generated_at),
    }


def _cached(s: Session, scope: str, key: str, fp: str) -> dict | None:
    row = s.scalars(select(AIAnswer).where(AIAnswer.scope == scope, AIAnswer.question_key == key,
                                           AIAnswer.fingerprint == fp)).first()
    if row is None:
        return None
    row.hits += 1
    s.commit()
    data = json.loads(row.answer_json)
    data["cached"] = True
    return data


def _store(s: Session, scope: str, key: str, fp: str, reply: dict, now: datetime) -> None:
    s.add(AIAnswer(scope=scope, question_key=key, fingerprint=fp, answer_json=json.dumps(reply, ensure_ascii=False),
                   model=reply["model"], created_at=now, hits=0))
    try:
        s.commit()
    except Exception:  # concurrent identical question: keep the first
        s.rollback()


# ---------------------------------------------------------------- per story
def ask_story(s: Session, cfg: Settings, now: datetime, story_id: str, question: str, history: list | None,
              client, model_config: dict) -> dict:
    question = clean_question(question)
    history = clean_history(history)
    cutoff = window_start(now, cfg.retention_hours)
    story = s.get(Story, story_id)
    arts = s.scalars(
        select(Article).join(StoryArticle, StoryArticle.article_id == Article.id)
        .where(StoryArticle.story_id == story_id, Article.published_at >= cutoff)
    ).all() if story else []
    if not arts:
        raise AskError(404, "This story is no longer available.")
    inputs = [InputArticle(a.id, a.publisher, a.title, a.published_at, a.excerpt, a.feed_text, a.content_hash) for a in arts]
    by_id = {a.id: a for a in arts}
    scope, key = f"story:{story_id}", question_key(question)
    fp = hashlib.sha256((ASK_PROMPT_VERSION + fingerprint(inputs, model_config["prompt_version"])).encode()).hexdigest()
    if not history and (hit := _cached(s, scope, key, fp)):
        return hit
    if client is None:
        raise AskError(503, "The AI assistant is not configured on the server.")
    _daily_guard(s, cfg, now)

    chosen = select_inputs(inputs, model_config.get("max_articles_per_story", 8))
    limit = model_config.get("max_chars_per_article", 1800)
    labels: dict[str, dict] = {}
    articles = []
    for i, a in enumerate(chosen, start=1):
        art = by_id[a.id]
        labels[f"A{i}"] = {"kind": "article", "title": art.title, "publisher": art.publisher, "url": art.url,
                           "published_at": iso(art.published_at), "article_id": art.id}
        text = (a.excerpt + "\n" + a.feed_text).strip() if a.feed_text else a.excerpt
        articles.append({"label": f"A{i}", "publisher": a.publisher, "title": a.title,
                         "published_at": iso(a.published_at), "text": text[:limit]})
    background = []
    bg_rows = s.execute(select(BackgroundLink).join(StoryBackground, StoryBackground.background_id == BackgroundLink.id)
                        .where(StoryBackground.story_id == story_id).order_by(StoryBackground.rank)).scalars().all()
    for i, b in enumerate(bg_rows, start=1):
        labels[f"B{i}"] = {"kind": "background", "title": b.title, "publisher": b.provider, "url": b.url,
                           "published_at": None}
        background.append({"label": f"B{i}", "title": b.title, "description": b.description})
    analysis = s.scalars(select(AIAnalysis).where(AIAnalysis.story_id == story_id)).first()
    overview = json.loads(analysis.content_json)["overview"]["text"] if analysis and analysis.content_json else None
    payload = json.dumps({"story_headline": story.headline, "articles": articles, "background": background,
                          "ai_overview": overview, "conversation": history, "question": question},
                         ensure_ascii=False, indent=1)
    raw = _call(s, client, _prompt("ask_story_prompt.md"), payload, f"ask:{story_id}", now)

    citations, seen = [], set()
    for label in raw.get("citations") or []:
        label = str(label).strip().strip("[]")
        if label in labels and label not in seen:
            seen.add(label)
            citations.append({"number": len(citations) + 1, "label": label, **labels[label]})
    answer = renumber_labels(str(raw["answer"]).strip(), citations)
    corpus = " ".join(f"{a['title']} {a['text']}" for a in articles) + " " + " ".join(
        f"{b['title']} {b['description']}" for b in background)
    reason = _unsupported(answer, corpus)
    flag = f"Automated check: {reason}. Verify with the original coverage." if reason else None
    if not citations and not _no_source_needed(answer):
        flag = flag or "Automated check: this answer has no citations to the coverage. Treat it with caution."
    reply = _reply(answer, citations, raw, flag, getattr(client, "last_model_used", "unknown"), False, now, "story")
    if not history:
        _store(s, scope, key, fp, reply, now)
    return reply


# ---------------------------------------------------------------- global
def find_stories(s: Session, cutoff: datetime, question: str, limit: int = 6) -> list[tuple[str, list[Article]]]:
    q_terms = set(tokens(question))
    if not q_terms:
        return []
    rows = s.execute(
        select(StoryArticle.story_id, Article).join(Article, Article.id == StoryArticle.article_id)
        .where(Article.published_at >= cutoff)
    ).all()
    stories: dict[str, list[Article]] = defaultdict(list)
    for sid, art in rows:
        stories[sid].append(art)
    terms = {sid: set(tokens(" ".join(f"{a.title} {a.excerpt}" for a in arts))) for sid, arts in stories.items()}
    df: dict[str, int] = defaultdict(int)
    for ts in terms.values():
        for t in ts & q_terms:
            df[t] += 1
    n = len(stories) or 1
    scored = []
    for sid, ts in terms.items():
        hit = ts & q_terms
        if not hit:
            continue
        score = sum(math.log((n + 1) / (df[t] + 1)) + 1 for t in hit)
        latest = max(a.published_at for a in stories[sid])
        scored.append((score, len({a.publisher for a in stories[sid]}), latest, sid))
    scored.sort(reverse=True)
    if not scored:
        return []
    best = scored[0][0]
    # Keep only reasonably strong matches (avoid padding with weak one-word hits).
    return [(sid, stories[sid]) for score, _, _, sid in scored[:limit] if score >= best * 0.5]


_GENERIC = re.compile(r"\b(top|biggest|main|major|latest|today'?s?|headlines?|happening|news|stories|summari[sz]e|"
                      r"this week|right now|important)\b", re.I)


def top_stories(s: Session, cutoff: datetime, limit: int = 6) -> list[tuple[str, list[Article]]]:
    """Most recent stories, preferring those covered by several publishers."""
    rows = s.execute(
        select(StoryArticle.story_id, Article).join(Article, Article.id == StoryArticle.article_id)
        .where(Article.published_at >= cutoff)
    ).all()
    stories: dict[str, list[Article]] = defaultdict(list)
    for sid, art in rows:
        stories[sid].append(art)
    ranked = sorted(stories.items(), key=lambda kv: (len({a.publisher for a in kv[1]}) >= 2,
                                                     max(a.published_at for a in kv[1])), reverse=True)
    return ranked[:limit]


def ask_global(s: Session, cfg: Settings, now: datetime, question: str, history: list | None, client,
               model_config: dict) -> dict:
    question = clean_question(question)
    history = clean_history(history)
    cutoff = window_start(now, cfg.retention_hours)
    search_text = question + " " + " ".join(t["text"] for t in history if t["role"] == "user")[-300:]
    matches = find_stories(s, cutoff, search_text)
    if not matches and _GENERIC.search(question):
        matches = top_stories(s, cutoff)  # "What are today's top stories?"
    if not matches:
        return {**_reply(NO_COVERAGE, [], {}, None, "none", False, now, "global"), "label": "NewsVista"}
    fp_src = ASK_PROMPT_VERSION + "|" + "|".join(
        f"{sid}:{','.join(sorted(a.content_hash for a in arts))}" for sid, arts in matches)
    fp = hashlib.sha256(fp_src.encode()).hexdigest()
    key = question_key(question)
    if not history and (hit := _cached(s, "global", key, fp)):
        return hit
    if client is None:
        raise AskError(503, "The AI assistant is not configured on the server.")
    _daily_guard(s, cfg, now)

    story_rows = {st.id: st for st in s.scalars(select(Story).where(Story.id.in_([sid for sid, _ in matches])))}
    analyses = {a.story_id: a for a in s.scalars(select(AIAnalysis).where(AIAnalysis.story_id.in_(story_rows)))}
    labels, items, corpus = {}, [], []
    for i, (sid, arts) in enumerate(matches, start=1):
        st = story_rows[sid]
        ordered = sorted(arts, key=lambda a: a.published_at, reverse=True)[:3]
        overview = None
        if sid in analyses and analyses[sid].content_json:
            overview = json.loads(analyses[sid].content_json)["overview"]["text"]
        excerpts = [f"{a.publisher}: {a.title} — {a.excerpt[:300]}" for a in ordered]
        items.append({"label": f"S{i}", "headline": st.headline, "publishers": sorted({a.publisher for a in arts}),
                      "latest": iso(max(a.published_at for a in arts)), "excerpts": excerpts, "ai_overview": overview})
        labels[f"S{i}"] = {"kind": "story", "story_id": sid, "title": st.headline,
                           "publisher": ", ".join(sorted({a.publisher for a in arts})),
                           "url": None, "published_at": iso(max(a.published_at for a in arts))}
        corpus.append(" ".join(excerpts) + " " + (overview or ""))
    payload = json.dumps({"stories": items, "conversation": history, "question": question}, ensure_ascii=False, indent=1)
    raw = _call(s, client, _prompt("ask_global_prompt.md"), payload, "ask:global", now)

    citations, seen = [], set()
    for label in raw.get("citations") or []:
        label = str(label).strip().strip("[]")
        if label in labels and label not in seen:
            seen.add(label)
            citations.append({"number": len(citations) + 1, "label": label, **labels[label]})
    answer = renumber_labels(str(raw["answer"]).strip(), citations)
    reason = _unsupported(answer, " ".join(corpus))
    flag = f"Automated check: {reason}. Open the cited stories to verify." if reason else None
    reply = _reply(answer, citations, raw, flag, getattr(client, "last_model_used", "unknown"), False, now, "global")
    if not history:
        _store(s, "global", key, fp, reply, now)
    return reply

"""Database schema (SQLAlchemy 2). The same models run on SQLite (tests/local)
and PostgreSQL (Supabase). migrations/001_init.sql is generated from these
models by scripts/dump_schema.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UTCDateTime(TypeDecorator):
    """Stores aware datetimes as UTC; always returns aware UTC datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use UTC-aware values")
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Source(Base):
    """One RSS feed. Several feeds may belong to the same publisher."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publisher: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(120))
    feed_url: Mapped[str] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32), default="top")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Article(Base):
    """One publisher's report. id = hash of the normalized URL (stable)."""

    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    publisher: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text, unique=True)
    guid: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    # Feed-provided summary, shown in-app as a labeled publisher excerpt.
    excerpt: Mapped[str] = mapped_column(Text, default="")
    # Partial article text the feed itself distributes (content:encoded). Used only
    # as AI input; never displayed as a full article.
    feed_text: Mapped[str] = mapped_column(Text, default="")
    content_kind: Mapped[str] = mapped_column(String(32), default="feed_excerpt")
    # Image URL published in the feed (hot-linked from the publisher; optional).
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Feed sections the article appeared in, e.g. ",top,world," (for category chips).
    categories: Mapped[str] = mapped_column(String(100), default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)

    membership: Mapped["StoryArticle | None"] = relationship(
        back_populates="article", cascade="all, delete-orphan", uselist=False
    )


class Story(Base):
    """An event; groups one or more articles. id never changes once assigned."""

    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    headline: Mapped[str] = mapped_column(Text)
    headline_article_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    latest_published_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    # Fingerprint of the article set when background links were last searched.
    background_checked_fp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    background_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    members: Mapped[list["StoryArticle"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )
    analysis: Mapped["AIAnalysis | None"] = relationship(
        back_populates="story", cascade="all, delete-orphan", uselist=False
    )
    background: Mapped[list["StoryBackground"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )


class StoryArticle(Base):
    """Association: which story an article belongs to (an article joins one story)."""

    __tablename__ = "story_articles"
    __table_args__ = (UniqueConstraint("article_id", name="uq_story_articles_article"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Grouping evidence: similarity to the article it matched (null = story seed).
    match_score: Mapped[float | None] = mapped_column(nullable=True)
    matched_article_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    story: Mapped[Story] = relationship(back_populates="members")
    article: Mapped[Article] = relationship(back_populates="membership")


class BackgroundLink(Base):
    """A reference resource. Kept only while linked to an active story."""

    __tablename__ = "background_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(64), default="Wikipedia")
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime)


class StoryBackground(Base):
    __tablename__ = "story_background"

    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True)
    background_id: Mapped[int] = mapped_column(
        ForeignKey("background_links.id", ondelete="CASCADE"), primary_key=True
    )
    matched_term: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(32))  # "entity" or "ai_topic"
    rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    story: Mapped[Story] = relationship(back_populates="background")
    link: Mapped[BackgroundLink] = relationship()


class AIAnalysis(Base):
    """Current stored AI analysis for a story (one row per story, versioned)."""

    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[str] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), unique=True
    )
    # ok | failed | pending
    status: Mapped[str] = mapped_column(String(24), default="pending")
    # sha256 over (article ids + content hashes + prompt version + model)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_article_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    input_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    content_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_notes: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_attempt_fp: Mapped[str | None] = mapped_column(String(64), nullable=True)

    story: Mapped[Story] = relationship(back_populates="analysis")


class AIAnswer(Base):
    """Cached answer to a reader question ("Ask AI"). Keyed by scope + normalized
    question + input fingerprint, so a repeated question reuses the stored answer.
    Deleted when the story's inputs change or expire (see pipeline.retention)."""

    __tablename__ = "ai_answers"
    __table_args__ = (UniqueConstraint("scope", "question_key", "fingerprint", name="uq_ai_answers_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(48), index=True)  # "story:<id>" or "global"
    question_key: Mapped[str] = mapped_column(String(300))
    fingerprint: Mapped[str] = mapped_column(String(64))
    answer_json: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)


class AICallLog(Base):
    """Operational log of model calls (no article text or summaries)."""

    __tablename__ = "ai_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    called_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    story_id: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # running | success | partial | failed
    status: Mapped[str] = mapped_column(String(16), default="running")
    articles_fetched: Mapped[int] = mapped_column(Integer, default=0)
    articles_new: Mapped[int] = mapped_column(Integer, default=0)
    articles_updated: Mapped[int] = mapped_column(Integer, default=0)
    articles_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    skipped_invalid_date: Mapped[int] = mapped_column(Integer, default=0)
    skipped_future: Mapped[int] = mapped_column(Integer, default=0)
    skipped_too_old: Mapped[int] = mapped_column(Integer, default=0)
    articles_expired: Mapped[int] = mapped_column(Integer, default=0)
    stories_created: Mapped[int] = mapped_column(Integer, default=0)
    stories_joined: Mapped[int] = mapped_column(Integer, default=0)
    stories_deleted: Mapped[int] = mapped_column(Integer, default=0)
    analyses_invalidated: Mapped[int] = mapped_column(Integer, default=0)
    ai_generated: Mapped[int] = mapped_column(Integer, default=0)
    ai_failed: Mapped[int] = mapped_column(Integer, default=0)
    ai_deferred: Mapped[int] = mapped_column(Integer, default=0)
    background_links_added: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    sources: Mapped[list["CollectionRunSource"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CollectionRunSource(Base):
    """Per-feed outcome of a run, so one failing feed is visible but isolated."""

    __tablename__ = "collection_run_sources"
    __table_args__ = (Index("ix_run_sources_run", "run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id", ondelete="CASCADE"))
    source_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # ok | failed
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_in_feed: Mapped[int] = mapped_column(Integer, default=0)
    new: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[CollectionRun] = relationship(back_populates="sources")

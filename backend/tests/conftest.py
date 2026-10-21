from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import Settings, load_model_config  # noqa: E402
from app.db import Database, set_db  # noqa: E402
from app.feeds import FeedError, FeedItem, FeedResult  # noqa: E402
from app.pipeline import CollectionJob, Services  # noqa: E402

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
FIXTURES = json.loads((BACKEND / "tests" / "fixtures" / "grouping_fixtures.json").read_text(encoding="utf-8"))


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeFeeds:
    """Serves controlled FeedItems per source; a source mapped to an Exception fails."""

    def __init__(self):
        self.items: dict[str, list[FeedItem] | Exception] = {}

    def __call__(self, src: dict) -> FeedResult:
        value = self.items.get(src["id"], [])
        if isinstance(value, Exception):
            raise value
        return FeedResult(200, list(value))


class FakeAI:
    """Counts calls; returns a well-formed analysis citing the given labels."""

    def __init__(self, response_fn=None, error: Exception | None = None):
        self.calls = 0
        self.model = "fake-model"
        self.last_model_used = "fake-model"
        self.response_fn = response_fn
        self.error = error

    def generate(self, system_prompt: str, payload: str) -> dict:
        self.calls += 1
        if self.error:
            raise self.error
        data = json.loads(payload)
        labels = [a["label"] for a in data["articles"]]
        if self.response_fn:
            return self.response_fn(labels, data)
        return {
            "overview": "Officials described the event; coverage differs on details.",
            "overview_citations": labels,
            "agreements": [{"text": "Both outlets report the event happened.", "citations": labels[:2]}],
            "disagreements": [],
            "uncertainties": [{"text": "Details remain unconfirmed.", "citations": labels[:1]}],
            "perspectives_status": "supported",
            "perspectives": [
                {"name": "Officials: safety first", "summary": "Officials urged caution.",
                 "claims": [{"text": "Officials urged residents to be careful.", "citations": labels[:1]}], "caveats": ""},
                {"name": "Residents: frustration", "summary": "Residents criticized the response.",
                 "claims": [{"text": "Residents said help was slow.", "citations": labels[-1:]}], "caveats": ""},
            ],
            "limitations": ["Only feed excerpts were available."],
            "background_topics": [],
        }


SOURCES = [
    {"id": "bbc", "publisher": "BBC News", "name": "BBC", "feed_url": "https://example.test/bbc"},
    {"id": "npr", "publisher": "NPR", "name": "NPR", "feed_url": "https://example.test/npr"},
    {"id": "fox", "publisher": "Fox News", "name": "Fox", "feed_url": "https://example.test/fox"},
]


def item(slug: str, title: str, published: datetime | None, excerpt: str = "") -> FeedItem:
    return FeedItem(title=title, url=f"https://news.example/{slug}?utm_source=rss", guid=slug,
                    published_at=published, excerpt=excerpt, feed_text="")


@pytest.fixture
def env(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    db.create_all()
    set_db(db)
    clock = Clock(T0)
    feeds = FakeFeeds()
    cfg = Settings()
    cfg.admin_token = "test-token"
    cfg.ai_max_per_run = 20
    config = load_model_config()
    config["seconds_between_calls"] = 0

    class Env:
        pass

    e = Env()
    e.db, e.clock, e.feeds, e.cfg, e.model_config = db, clock, feeds, cfg, config
    e.ai = FakeAI()

    def run(trigger="test", ai=None, background=None):
        services = Services(fetcher=feeds, ai_client=ai if ai is not None else e.ai, background_lookup=background,
                            sleep=lambda _: None, now=clock, sources=SOURCES, model_config=config)
        return CollectionJob(db, services, cfg).run(trigger)

    e.run = run
    return e


__all__ = ["T0", "FIXTURES", "FakeAI", "FeedError", "item", "timedelta"]

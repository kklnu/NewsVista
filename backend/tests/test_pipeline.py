"""End-to-end pipeline behaviour with controlled feeds, clock and AI."""
import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import main as api
from app import views
from app.ai.client import AIError
from app.models import AIAnalysis, Article, BackgroundLink, CollectionRun, Story, StoryArticle
from app.background import BackgroundResult

from conftest import T0, FakeAI, FeedError, item, timedelta

QUAKE = "Magnitude 6.8 earthquake strikes off northern Japan near Aomori, tsunami advisory issued"
QUAKE2 = "Strong 6.8 earthquake shakes northern Japan near Aomori; tsunami advisory lifted"
QUAKE3 = "Japan earthquake: 6.8 quake rattles Aomori as tsunami advisory issued"
EX = "The earthquake struck off Aomori, Japan, prompting a tsunami advisory."


def quake_feeds(env, hours=(10, 9, 8)):
    env.feeds.items = {
        "bbc": [item("bbc-quake", QUAKE, T0 - timedelta(hours=hours[0]), EX)],
        "npr": [item("npr-quake", QUAKE2, T0 - timedelta(hours=hours[1]), EX)],
        "fox": [item("fox-quake", QUAKE3, T0 - timedelta(hours=hours[2]), EX)],
    }


def counts(env):
    with env.db.session() as s:
        return (s.scalar(select(func.count()).select_from(Article)),
                s.scalar(select(func.count()).select_from(Story)),
                s.scalar(select(func.count()).select_from(StoryArticle)))


def test_repeated_ingestion_does_not_duplicate(env):
    quake_feeds(env)
    first = env.run()
    before = counts(env)
    second = env.run()
    assert first["articles_new"] == 3 and second["articles_new"] == 0
    assert second["articles_unchanged"] == 3
    assert counts(env) == before == (3, 1, 3)


def test_same_event_merges_into_one_story_with_publisher_buttons(env):
    quake_feeds(env)
    env.run()
    with env.db.session() as s:
        listing = views.list_stories(s, env.cfg, T0, 50, 0, 1)
        assert listing["total"] == 1
        story = listing["items"][0]
        assert story["publisher_count"] == 3
        detail = views.story_detail(s, env.cfg, T0, story["id"])
    pubs = {p["publisher"]: p["articles"][0]["url"] for p in detail["publishers"]}
    assert pubs == {"BBC News": "https://news.example/bbc-quake?utm_source=rss",
                    "NPR": "https://news.example/npr-quake?utm_source=rss",
                    "Fox News": "https://news.example/fox-quake?utm_source=rss"}


def test_new_article_joins_existing_story_with_stable_id(env):
    quake_feeds(env)
    fox = env.feeds.items.pop("fox")
    env.run()
    with env.db.session() as s:
        sid = s.scalar(select(Story.id))
    env.feeds.items["fox"] = fox
    env.clock.now = T0 + timedelta(hours=1)
    out = env.run()
    assert out["stories_created"] == 0 and out["stories_joined"] == 1
    with env.db.session() as s:
        assert s.scalar(select(Story.id)) == sid
        assert s.scalar(select(func.count()).select_from(StoryArticle).where(StoryArticle.story_id == sid)) == 3


def test_invalid_missing_and_future_dates_are_excluded(env):
    env.feeds.items = {"bbc": [
        item("no-date", "Undated item about a parliament vote", None),
        item("future", "Future dated item about a summit", T0 + timedelta(hours=5)),
        item("too-old", "Old item about a court ruling", T0 - timedelta(hours=200)),
        item("ok", "Valid item about a mining law in Ghana", T0 - timedelta(hours=1)),
    ]}
    out = env.run()
    assert (out["skipped_invalid_date"], out["skipped_future"], out["skipped_too_old"], out["articles_new"]) == (1, 1, 1, 1)


def test_seven_day_boundary_api_filter_and_cleanup(env):
    env.feeds.items = {"bbc": [
        item("recent", "Ghana parliament approves mining royalty law", T0 - timedelta(hours=100)),
        item("edge", "Bank of England holds interest rates steady", T0 - timedelta(hours=167)),
    ]}
    env.run()
    with env.db.session() as s:
        assert views.list_stories(s, env.cfg, T0, 50, 0, 1)["total"] == 2
    # Two hours later, "edge" is 169h old. No run has happened yet: the API must already hide it.
    later = T0 + timedelta(hours=2)
    with env.db.session() as s:
        listing = views.list_stories(s, env.cfg, later, 50, 0, 1)
        assert [i["headline"] for i in listing["items"]] == ["Ghana parliament approves mining royalty law"]
        assert s.scalar(select(func.count()).select_from(Article)) == 2  # still stored until cleanup
    env.clock.now = later
    env.feeds.items = {}
    out = env.run()
    assert out["articles_expired"] == 1 and out["stories_deleted"] == 1
    with env.db.session() as s:
        assert [a.id for a in s.scalars(select(Article))] != [] and s.scalar(select(func.count()).select_from(Article)) == 1


def test_expiration_inside_group_removes_source_and_regenerates_ai(env):
    quake_feeds(env, hours=(166, 160, 150))
    env.run()
    assert env.ai.calls == 1
    with env.db.session() as s:
        sid = s.scalar(select(Story.id))
        first = s.scalar(select(AIAnalysis))
        assert len(json.loads(first.input_article_ids)) == 3
    # 3h later the BBC article (now 169h old) has expired, before any run.
    later = T0 + timedelta(hours=3)
    with env.db.session() as s:
        detail = views.story_detail(s, env.cfg, later, sid)
    assert {p["publisher"] for p in detail["publishers"]} == {"NPR", "Fox News"}
    assert detail["analysis"]["status"] == "expired_inputs" and detail["analysis"]["content"] is None
    assert detail["overview"]["kind"] == "publisher_excerpt"
    # The next run deletes the article, invalidates and regenerates the analysis from retained inputs.
    env.clock.now = later
    env.feeds.items = {}
    out = env.run()
    assert out["articles_expired"] == 1 and out["analyses_invalidated"] == 1 and out["ai_generated"] == 1
    with env.db.session() as s:
        detail = views.story_detail(s, env.cfg, later, sid)
        analysis = s.scalar(select(AIAnalysis))
    assert env.ai.calls == 2
    assert detail["analysis"]["status"] == "current"
    assert len(json.loads(analysis.input_article_ids)) == 2
    assert {c["publisher"] for c in detail["analysis"]["content"]["citations"]} == {"NPR", "Fox News"}


def test_shared_ai_output_reused_by_two_clients_without_model_calls(env, monkeypatch):
    quake_feeds(env)
    env.run()
    assert env.ai.calls == 1
    monkeypatch.setattr(api, "utcnow", lambda: T0)
    client_a, client_b = TestClient(api.app), TestClient(api.app)
    sid = client_a.get("/stories").json()["items"][0]["id"]
    a = client_a.get(f"/stories/{sid}").json()["analysis"]
    b = client_b.get(f"/stories/{sid}").json()["analysis"]
    b2 = client_b.get(f"/stories/{sid}").json()["analysis"]
    assert a["analysis_id"] == b["analysis_id"] == b2["analysis_id"]
    assert a["generated_at"] == b["generated_at"] and a["version"] == b["version"] == 1
    assert env.ai.calls == 1  # GETs never call the model
    env.run()  # unchanged input -> no regeneration
    assert env.ai.calls == 1


def test_feed_failure_is_isolated_and_recorded(env):
    quake_feeds(env)
    env.feeds.items["npr"] = FeedError("HTTP 503", 503)
    out = env.run()
    assert out["status"] == "partial"
    failed = [s for s in out["sources"] if s["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["source_id"] == "npr" and failed[0]["http_status"] == 503
    with env.db.session() as s:
        assert views.list_stories(s, env.cfg, T0, 50, 0, 1)["items"][0]["publisher_count"] == 2
        assert views.last_successful_run(s) is not None
    # A total outage keeps previously stored stories.
    env.feeds.items = {k: FeedError("timeout") for k in ("bbc", "npr", "fox")}
    out = env.run()
    assert out["status"] == "failed"
    with env.db.session() as s:
        assert views.list_stories(s, env.cfg, T0, 50, 0, 1)["total"] == 1


def test_ai_failure_shows_honest_status_and_keeps_story(env):
    quake_feeds(env)
    failing = FakeAI(error=AIError("quota", "HTTP 429"))
    out = env.run(ai=failing)
    assert out["ai_failed"] == 1
    with env.db.session() as s:
        sid = s.scalar(select(Story.id))
        detail = views.story_detail(s, env.cfg, T0, sid)
    assert detail["analysis"]["status"] == "failed"
    assert detail["analysis"]["content"] is None
    assert detail["overview"]["kind"] == "publisher_excerpt"
    assert len(detail["publishers"]) == 3


def test_background_links_and_cleanup(env):
    quake_feeds(env, hours=(166, 166, 166))

    def lookup(cands, texts):
        return [BackgroundResult("Aomori Prefecture", "https://en.wikipedia.org/wiki/Aomori_Prefecture",
                                 "Prefecture of Japan", "Aomori", "entity")]

    env.run(background=lookup)
    with env.db.session() as s:
        sid = s.scalar(select(Story.id))
        detail = views.story_detail(s, env.cfg, T0, sid)
    assert detail["background"]["links"][0]["title"] == "Aomori Prefecture"
    env.clock.now = T0 + timedelta(hours=3)
    env.feeds.items = {}
    out = env.run(background=lookup)
    assert out["stories_deleted"] == 1
    with env.db.session() as s:
        assert s.scalar(select(func.count()).select_from(BackgroundLink)) == 0
        assert s.scalar(select(func.count()).select_from(AIAnalysis)) == 0


def test_no_background_message(env):
    env.feeds.items = {"bbc": [item("x", "Local council approves new park budget", T0 - timedelta(hours=1))]}
    env.run(background=lambda c, t: [])
    with env.db.session() as s:
        detail = views.story_detail(s, env.cfg, T0, s.scalar(select(Story.id)))
    assert detail["background"] == {"status": "none", "message": "No background resource available", "links": []}


def test_admin_endpoint_requires_token(env, monkeypatch):
    client = TestClient(api.app)
    monkeypatch.setattr(api.settings, "admin_token", "")
    assert client.post("/admin/collect").status_code == 503
    monkeypatch.setattr(api.settings, "admin_token", "secret-token")
    assert client.post("/admin/collect", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/admin/collect").status_code == 405


def test_runs_are_logged(env):
    quake_feeds(env)
    env.run(trigger="schedule")
    env.clock.now = T0 + timedelta(hours=1)
    env.run(trigger="schedule")
    with env.db.session() as s:
        runs = s.scalars(select(CollectionRun).order_by(CollectionRun.id)).all()
        status = views.status_view(s, env.cfg, env.clock.now)
    assert [r.trigger for r in runs] == ["schedule", "schedule"]
    assert all(r.status == "success" and r.finished_at for r in runs)
    assert status["last_successful_collection_at"] is not None and len(status["runs"]) == 2


def test_category_and_search_filters(env):
    quake_feeds(env)
    env.feeds.items["bbc"].append(item("bbc-ghana", "Ghana parliament approves mining royalty law", T0 - timedelta(hours=2)))
    env.run()
    with env.db.session() as s:
        assert views.list_stories(s, env.cfg, T0, 50, 0, 1)["total"] == 2
        assert views.list_stories(s, env.cfg, T0, 50, 0, 1, category="top")["total"] == 2  # test sources default to "top"
        assert views.list_stories(s, env.cfg, T0, 50, 0, 1, category="world")["total"] == 0
        found = views.list_stories(s, env.cfg, T0, 50, 0, 1, q="ghana mining")["items"]
        assert [i["headline"] for i in found] == ["Ghana parliament approves mining royalty law"]
        assert views.list_stories(s, env.cfg, T0, 50, 0, 1, q="aomori")["items"][0]["publisher_count"] == 3

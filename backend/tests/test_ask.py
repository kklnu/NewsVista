"""Ask AI assistant: grounding, citations, caching, limits, cleanup."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import main as api
from app.ai import ask
from app.ai.client import AIError
from app.models import AIAnswer, Story

from conftest import T0, item, timedelta
from test_pipeline import quake_feeds


class FakeAsk:
    def __init__(self, answer="The quake struck off Aomori, prompting a tsunami advisory.", cites=("A1", "A2"),
                 error=None):
        self.calls, self.payloads = 0, []
        self.model = self.last_model_used = "fake-model"
        self.answer, self.cites, self.error = answer, list(cites), error

    def generate(self, system, payload, schema=None):
        self.calls += 1
        self.payloads.append(json.loads(payload))
        if self.error:
            raise self.error
        return {"answer": self.answer, "citations": self.cites, "general_context": "Japan has frequent earthquakes.",
                "follow_up_questions": ["Was there damage?", "What is a tsunami advisory?"]}


@pytest.fixture
def story_env(env, monkeypatch):
    quake_feeds(env)
    env.run()
    with env.db.session() as s:
        env.sid = s.scalar(select(Story.id))
    monkeypatch.setattr(api, "utcnow", lambda: T0)
    api._ask_limiter = ask.RateLimiter(100, 300)
    env.http = TestClient(api.app)
    return env


def use(monkeypatch, client):
    monkeypatch.setattr(api, "ask_client", lambda: client)
    return client


def test_story_answer_has_citations_and_labelled_context(story_env, monkeypatch):
    ai = use(monkeypatch, FakeAsk())
    r = story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": "What happened?"})
    assert r.status_code == 200
    d = r.json()
    assert d["label"] == "AI-generated" and d["cached"] is False
    assert [c["label"] for c in d["citations"]] == ["A1", "A2"]
    assert all(c["url"].startswith("https://news.example/") for c in d["citations"])
    assert d["general_context"] and "not from the collected coverage" in d["general_context_label"]
    assert d["flag"] is None
    # The model only saw this story's articles, marked as data.
    payload = ai.payloads[0]
    assert payload["question"] == "What happened?" and len(payload["articles"]) == 3


def test_repeat_question_reuses_cached_answer(story_env, monkeypatch):
    ai = use(monkeypatch, FakeAsk())
    first = story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": "What happened?"}).json()
    again = story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": "what happened"}).json()
    assert ai.calls == 1 and again["cached"] is True and again["answer"] == first["answer"]
    # Follow-ups with conversation history are not cached (context differs).
    story_env.http.post(f"/stories/{story_env.sid}/ask", json={
        "question": "Was there damage?", "history": [{"role": "user", "text": "What happened?"},
                                                     {"role": "assistant", "text": first["answer"]}]})
    assert ai.calls == 2


def test_unknown_citations_dropped_and_unsupported_number_flagged(story_env, monkeypatch):
    use(monkeypatch, FakeAsk(answer="At least 4000 homes were damaged.", cites=("A9", "A1")))
    d = story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": "Damage?"}).json()
    assert [c["label"] for c in d["citations"]] == ["A1"]
    assert d["flag"] and "4000" in d["flag"]


def test_ai_failure_returns_readable_503(story_env, monkeypatch):
    use(monkeypatch, FakeAsk(error=AIError("overloaded", "busy")))
    r = story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": "What happened?"})
    assert r.status_code == 503 and "busy" in r.json()["detail"]


def test_limits_and_validation(story_env, monkeypatch):
    use(monkeypatch, FakeAsk())
    assert story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": "?"}).status_code == 422
    assert story_env.http.post("/stories/st_missing/ask", json={"question": "What happened?"}).status_code == 404
    api._ask_limiter = ask.RateLimiter(2, 300)
    codes = [story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": f"Question {i}?"}).status_code
             for i in range(3)]
    assert codes[-1] == 429


def test_global_finds_matching_story_and_skips_ai_without_match(story_env, monkeypatch):
    ai = use(monkeypatch, FakeAsk(answer="An earthquake struck off Aomori in Japan.", cites=("S1",)))
    d = story_env.http.post("/ask", json={"question": "What happened in Aomori?"}).json()
    assert d["citations"][0]["story_id"] == story_env.sid and ai.calls == 1
    none = story_env.http.post("/ask", json={"question": "volcano eruption iceland"}).json()
    assert none["citations"] == [] and "no coverage" in none["answer"] and ai.calls == 1  # no model call


def test_generic_question_uses_top_stories(story_env, monkeypatch):
    ai = use(monkeypatch, FakeAsk(answer="The main story is an earthquake near Aomori.", cites=("S1",)))
    d = story_env.http.post("/ask", json={"question": "What are today's top stories?"}).json()
    assert ai.calls == 1 and d["citations"][0]["story_id"] == story_env.sid


def test_cached_answers_removed_when_story_expires(story_env, monkeypatch):
    use(monkeypatch, FakeAsk())
    story_env.http.post(f"/stories/{story_env.sid}/ask", json={"question": "What happened?"})
    with story_env.db.session() as s:
        assert s.scalar(select(func.count()).select_from(AIAnswer)) == 1
    story_env.clock.now = T0 + timedelta(hours=200)
    story_env.feeds.items = {}
    story_env.run()
    with story_env.db.session() as s:
        assert s.scalar(select(func.count()).select_from(AIAnswer)) == 0


def test_inline_labels_become_citation_numbers():
    cites = [{"label": "S1", "number": 1}, {"label": "S6", "number": 2}]
    text = ask.renumber_labels("Attacks rose (S1, S6). A strike killed 53 (S2).", cites)
    assert text == "Attacks rose [1][2]. A strike killed 53."


def test_citation_markers_are_not_treated_as_numbers():
    assert ask._unsupported("Hubbard was freed [1][2]. Talks continue [3].", "Hubbard was freed. Talks continue.") is None
    assert "40" in ask._unsupported("At least 40 people died [1].", "People died.")

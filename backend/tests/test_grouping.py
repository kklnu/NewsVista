"""Grouping on the controlled fixture set (NOT live articles)."""
from collections import defaultdict

from app import grouping
from app.normalize import article_id_for, normalize_url

from conftest import FIXTURES, T0, timedelta


def _features(articles):
    feats = [
        grouping.build_features(a["id"], a["publisher"], T0 - timedelta(hours=a["hours_ago"]), a["title"], a["excerpt"])
        for a in articles
    ]
    idf = grouping.compute_idf(feats)
    for f in feats:
        f.vector = grouping.vectorize(f, idf)
    return feats


def _clusters(assignments):
    clusters = defaultdict(set)
    for a in assignments:
        clusters[a.story_key].add(a.article_id)
    return {frozenset(v) for v in clusters.values()}


def test_fixture_groups_match_expected_partition():
    articles = FIXTURES["articles"]
    expected = defaultdict(set)
    for a in articles:
        expected[a["group"]].add(a["id"])
    got = _clusters(grouping.assign_articles(_features(articles), []))
    assert got == {frozenset(v) for v in expected.values()}
    multi = [g for g in expected.values() if len(g) >= 2]
    assert len(multi) >= 5  # rubric: at least five multi-publisher groups


def test_similar_topic_distinct_events_stay_separate():
    by_id = {f.id: f for f in _features(FIXTURES["articles"])}
    assert len(FIXTURES["distinct_pairs"]) >= 2
    for left, right, why in FIXTURES["distinct_pairs"]:
        decision = grouping.link_decision(by_id[left], by_id[right])
        assert not decision.linked, f"{why}: {decision.reason}"


def test_new_coverage_joins_existing_story_incrementally():
    articles = FIXTURES["articles"]
    first = [a for a in articles if a["id"] != "jp3"]
    feats = _features(articles)
    by_id = {f.id: f for f in feats}
    initial = grouping.assign_articles([by_id[a["id"]] for a in first], [])
    story_of = {a.article_id: a.story_key for a in initial}
    existing = [(by_id[aid], sid) for aid, sid in story_of.items()]
    later = grouping.assign_articles([by_id["jp3"]], existing)
    assert later[0].story_key == story_of["jp1"]  # joins, no new story


def test_time_gap_prevents_merge():
    a, b = _features([
        {"id": "x1", "publisher": "BBC News", "hours_ago": 100, "title": "Magnitude 6.8 earthquake strikes off northern Japan", "excerpt": "Aomori tsunami advisory."},
        {"id": "x2", "publisher": "NPR", "hours_ago": 1, "title": "Magnitude 6.8 earthquake strikes off northern Japan", "excerpt": "Aomori tsunami advisory."},
    ])
    assert not grouping.link_decision(a, b).linked


def test_url_normalization_is_stable():
    u1 = "https://www.bbc.co.uk/news/articles/abc123?at_medium=RSS&at_campaign=rss"
    u2 = "http://WWW.BBC.CO.UK/news/articles/abc123/#0"
    assert normalize_url(u1) == normalize_url(u2) == "https://www.bbc.co.uk/news/articles/abc123"
    assert article_id_for(normalize_url(u1)) == article_id_for(normalize_url(u2))
    assert normalize_url("https://x.test/a?id=5&utm_source=x") == "https://x.test/a?id=5"

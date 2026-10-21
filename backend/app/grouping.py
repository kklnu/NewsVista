"""Event grouping: decide which articles describe the same specific event.

Method (documented in README "Grouping method"):
  1. Text features per article: stemmed title tokens (weighted x2), excerpt tokens,
     and proper-noun "entity" terms (capitalized words/phrases, acronyms).
  2. TF-IDF weighting over all articles currently in the 7-day window, so very
     common words ("Trump", "says", "war") count for little and rare, event-specific
     words ("Oslo", "Ebola", "Abuja") count for a lot.
  3. Two articles may link only if ALL of these hold:
       - published within MAX_GAP_HOURS of each other,
       - share at least one specific (non-generic) entity,
       - share at least MIN_SHARED_TERMS meaningful terms,
       - cosine similarity >= LINK_THRESHOLD, raised to SINGLE_ENTITY_THRESHOLD when
         only one specific entity is shared, and to SAME_PUBLISHER_THRESHOLD for two
         articles from the same publisher.
  4. Incremental, stable assignment: each new article joins the story of its best
     qualifying match among already-grouped articles; otherwise it starts a new
     story. Existing assignments are never reshuffled, so story IDs stay stable.
     For stories with 3+ members, the candidate must also be reasonably similar to
     the story as a whole (COHESION_MIN) to prevent "chaining" drift.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

MAX_GAP_HOURS = 72
LINK_THRESHOLD = 0.33
SINGLE_ENTITY_THRESHOLD = 0.40
SAME_PUBLISHER_THRESHOLD = 0.55
MIN_SHARED_TERMS = 3
COHESION_MIN = 0.16

STOPWORDS = set(
    """a about above across after again against ago ahead all almost also am amid among an and another any
    are around as at away back be became because become been before being below between both but by can
    cannot could did do does doing done down during each either else even ever every few for from further
    get gets getting got had has have having he her here hers herself him himself his how however i if in
    inside into is it its itself just last late latest least less like live make makes making many may me
    might more most much must my near nearly new news next no nor not now of off on once one only onto or
    other others our ours out over own per put said same say saying says see seen she should since so some
    still such take takes than that the their theirs them then there these they this those though three
    through to today told too two under until up upon us very via was way we were what when where whether
    which while who whom whose why will with within without would year years yet you your week weeks day
    days month months time times first second people report reports reported update updates video watch
    could after amid what know here's what's it's don't can't won't new latest analysis opinion explained
    mr mrs ms dr st""".split()
)

# Entities so common in this news mix that sharing them says little about the event.
GENERIC_ENTITIES = {
    "us", "u.s", "uk", "america", "american", "americans", "britain", "british", "europe", "european",
    "world", "news", "fox", "bbc", "npr", "cbs", "guardian", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december", "president", "house", "white",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'’.\-]*[A-Za-z0-9]|[A-Za-z]")


def stem(word: str) -> str:
    w = word.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    w = w.strip("'.-")
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss") and not w.endswith("us"):
        w = w[:-1]
    for suffix in ("ing", "ed"):
        if len(w) - len(suffix) >= 4 and w.endswith(suffix):
            w = w[: -len(suffix)]
            break
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def tokens(text: str) -> list[str]:
    out = []
    for raw in _WORD.findall(text or ""):
        low = raw.lower().replace("’", "'")
        if low in STOPWORDS or low.rstrip("'s") in STOPWORDS:
            continue
        s = stem(raw)
        if len(s) < 3 or s in STOPWORDS:
            continue
        out.append(s)
    return out


def _is_capitalized(word: str) -> bool:
    return word[:1].isupper()


def entity_phrases(text: str) -> list[str]:
    """Capitalized phrases ("Helen Haines", "NATO", "White House").

    Sentence-initial words are skipped unless they are acronyms, because news
    titles here are sentence case ("Man charged with...").
    """
    phrases: list[str] = []
    for sentence in re.split(r"(?<=[.!?:;])\s+|\n|\s[-–—|]\s", text or ""):
        words = _WORD.findall(sentence)
        current: list[str] = []
        for idx, word in enumerate(words):
            clean = word.replace("’", "'")
            if clean.endswith("'s"):
                clean = clean[:-2]
            is_acronym = len(clean) >= 2 and clean.replace(".", "").isupper() and clean.replace(".", "").isalpha()
            capital = _is_capitalized(clean) and (idx > 0 or is_acronym)
            if capital and clean.lower() not in STOPWORDS:
                current.append(clean)
            elif current and clean.lower() in {"of", "de", "al", "bin"} and idx + 1 < len(words) and _is_capitalized(words[idx + 1]):
                current.append(clean.lower())
            else:
                if current:
                    phrases.append(" ".join(current))
                current = []
        if current:
            phrases.append(" ".join(current))
    return [p for p in phrases if p.lower() not in GENERIC_ENTITIES]


@dataclass
class ArticleFeatures:
    id: str
    publisher: str
    published_at: datetime
    title: str
    title_tokens: list[str]
    body_tokens: list[str]
    entities: set[str]
    phrases: list[str] = field(default_factory=list)
    vector: dict[str, float] = field(default_factory=dict)

    @property
    def all_terms(self) -> set[str]:
        return set(self.title_tokens) | set(self.body_tokens)


def build_features(article_id: str, publisher: str, published_at: datetime, title: str, excerpt: str,
                   feed_text: str = "") -> ArticleFeatures:
    body = excerpt if len(excerpt) >= 80 else (excerpt + " " + feed_text[:400])
    phrases = entity_phrases(title) + entity_phrases(body)
    # The first word of a sentence-case title counts as an entity only if the same
    # word is capitalized mid-sentence elsewhere or used as a possessive
    # ("Ghana's parliament..."), e.g. "Ghana passes...", but not "Man charged...".
    first = _WORD.findall(title)[:1]
    mid_caps = {w for p in phrases for w in p.split()}
    full_text = f"{title} {body}".replace("’", "'")
    if first and first[0].lower() not in STOPWORDS and (
        first[0] in mid_caps or f"{first[0]}'s" in full_text
    ):
        phrases.insert(0, first[0])
    ents = set()
    for p in phrases:
        for w in p.split():
            s = stem(w)
            if len(s) >= 2 and s not in STOPWORDS and w.lower() not in GENERIC_ENTITIES:
                ents.add(s)
    return ArticleFeatures(
        id=article_id,
        publisher=publisher,
        published_at=published_at,
        title=title,
        title_tokens=tokens(title),
        body_tokens=tokens(body),
        entities=ents,
        phrases=phrases,
    )


def compute_idf(features: list[ArticleFeatures]) -> dict[str, float]:
    df: Counter[str] = Counter()
    for f in features:
        df.update(f.all_terms)
    n = len(features)
    return {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}


def vectorize(f: ArticleFeatures, idf: dict[str, float]) -> dict[str, float]:
    tf: Counter[str] = Counter()
    for t in f.title_tokens:
        tf[t] += 2.0
    for t in f.body_tokens:
        tf[t] += 1.0
    for t in f.entities:
        if t in tf:
            tf[t] += 1.0
    default_idf = max(idf.values(), default=1.0)
    vec = {t: (1 + math.log(c)) * idf.get(t, default_idf) for t, c in tf.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {t: v / norm for t, v in vec.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


@dataclass
class LinkDecision:
    linked: bool
    similarity: float
    reason: str


def link_decision(a: ArticleFeatures, b: ArticleFeatures) -> LinkDecision:
    sim = cosine(a.vector, b.vector)
    gap_h = abs((a.published_at - b.published_at).total_seconds()) / 3600
    if gap_h > MAX_GAP_HOURS:
        return LinkDecision(False, sim, f"published {gap_h:.0f}h apart (> {MAX_GAP_HOURS}h)")
    shared_entities = a.entities & b.entities
    if not shared_entities:
        return LinkDecision(False, sim, "no shared specific entity")
    shared_terms = a.all_terms & b.all_terms
    if len(shared_terms) < MIN_SHARED_TERMS:
        return LinkDecision(False, sim, f"only {len(shared_terms)} shared terms")
    threshold = LINK_THRESHOLD
    if len(shared_entities) == 1:
        threshold = SINGLE_ENTITY_THRESHOLD
    if a.publisher == b.publisher:
        threshold = max(threshold, SAME_PUBLISHER_THRESHOLD)
    if sim < threshold:
        return LinkDecision(False, sim, f"similarity {sim:.2f} < {threshold:.2f}")
    return LinkDecision(True, sim, f"similarity {sim:.2f}; shared entities {sorted(shared_entities)[:4]}")


@dataclass
class Assignment:
    article_id: str
    story_key: str  # existing story id, or "new:<seed article id>"
    score: float | None
    matched_article_id: str | None


def assign_articles(new: list[ArticleFeatures], existing: list[tuple[ArticleFeatures, str]]) -> list[Assignment]:
    """Assign each new article to an existing story or a new one.

    `existing` holds (features, story_id) of already-grouped, retained articles.
    All features (new and existing) must already have `.vector` set.
    """
    pool: list[tuple[ArticleFeatures, str]] = list(existing)
    members: dict[str, list[ArticleFeatures]] = {}
    for f, sid in pool:
        members.setdefault(sid, []).append(f)

    out: list[Assignment] = []
    for art in sorted(new, key=lambda f: (f.published_at, f.id)):
        best: tuple[float, ArticleFeatures, str] | None = None
        for other, sid in pool:
            d = link_decision(art, other)
            if d.linked and (best is None or d.similarity > best[0]):
                story_members = members[sid]
                if len(story_members) >= 3:
                    mean = sum(cosine(art.vector, m.vector) for m in story_members) / len(story_members)
                    if mean < COHESION_MIN:
                        continue
                best = (d.similarity, other, sid)
        if best:
            sim, other, sid = best
            out.append(Assignment(art.id, sid, round(sim, 4), other.id))
        else:
            sid = f"new:{art.id}"
            out.append(Assignment(art.id, sid, None, None))
        pool.append((art, sid))
        members.setdefault(sid, []).append(art)
    return out


def choose_headline(features: list[ArticleFeatures]) -> ArticleFeatures:
    """Most central article (highest total similarity); ties -> earliest."""
    if len(features) <= 2:
        return min(features, key=lambda f: (f.published_at, f.id))

    def centrality(f: ArticleFeatures) -> float:
        return sum(cosine(f.vector, o.vector) for o in features if o is not f)

    return max(features, key=lambda f: (round(centrality(f), 6), -f.published_at.timestamp()))

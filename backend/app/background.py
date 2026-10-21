"""Find background resources (Wikipedia) for a story, conservatively.

Method (documented in README "Background method"):
  1. Candidates: proper-noun phrases from the story's titles/excerpts, ranked by
     how many of the story's articles mention them (multi-word names first), plus
     up to 3 topic names suggested by the AI analysis when available.
  2. Exact-title lookup on the Wikipedia API (following redirects) - no fuzzy
     search, so we never jump to a loosely related page.
  3. Reject missing pages, disambiguation/list/surname/placeholder pages, redirects
     that change the name (e.g. "Jane Doe" -> "John Doe", "Gov" -> "Government"),
     and generic-concept titles such as "Town hall" (entity candidates only).
  4. Relevance check: the page's intro must mention at least two OTHER specific
     terms from the story (e.g. the "Helen Haines" page must mention "Australian",
     "politician"/"MP", "Indi", ...), so a same-named but unrelated page is rejected.
  5. Keep at most 3 links. If none pass, the API reports
     "No background resource available".
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import httpx

from .grouping import STOPWORDS, entity_phrases, stem, tokens

WIKI_API = "https://en.wikipedia.org/w/api.php"
MAX_LINKS = 3
MAX_CANDIDATES = 8


@dataclass
class BackgroundCandidate:
    phrase: str
    method: str  # "entity" | "ai_topic"


@dataclass
class BackgroundResult:
    title: str
    url: str
    description: str
    matched_term: str
    method: str
    thumbnail_url: str | None = None


def candidates_for(texts: list[tuple[str, str]], ai_topics: list[str] | None = None) -> list[BackgroundCandidate]:
    """texts: (title, excerpt) per article."""
    counts: Counter[str] = Counter()
    original: dict[str, str] = {}
    for title, excerpt in texts:
        seen = set()
        for phrase in entity_phrases(title) + entity_phrases(excerpt):
            key = phrase.lower()
            if len(key) < 3 or key in STOPWORDS:
                continue
            if key not in seen:
                counts[key] += 1
                seen.add(key)
                original.setdefault(key, phrase)
    # Specific multi-word names first, then by how many articles mention them.
    ranked = sorted(counts, key=lambda k: (len(k.split()) == 1, -counts[k], k))
    out: list[BackgroundCandidate] = []
    for topic in (ai_topics or [])[:3]:
        if topic.strip():
            out.append(BackgroundCandidate(topic.strip(), "ai_topic"))
    for key in ranked:
        if len(out) >= MAX_CANDIDATES:
            break
        if any(c.phrase.lower() == key for c in out):
            continue
        out.append(BackgroundCandidate(original[key], "entity"))
    return out


def _story_terms(texts: list[tuple[str, str]]) -> set[str]:
    terms: set[str] = set()
    for title, excerpt in texts:
        terms.update(tokens(f"{title} {excerpt}"))
    return terms


def _relevant(extract: str, page_title: str, story_terms: set[str]) -> tuple[bool, int]:
    page_terms = {stem(w) for w in re.findall(r"[A-Za-z]+", page_title)}
    intro_terms = set(tokens(extract))
    overlap = (intro_terms & story_terms) - page_terms
    # Prefix match catches "Australia"/"Australian", "Ukraine"/"Ukrainian".
    if len(overlap) < 2:
        for st in story_terms - page_terms:
            if len(st) >= 5 and any(it != st and (it.startswith(st[:5])) for it in intro_terms):
                overlap.add(st)
    return len(overlap) >= 2, len(overlap)


_BAD_DESCRIPTION = re.compile(r"surname|given name|placeholder|disambiguation|list of|topics referred|"
                              r"index of|family name", re.I)
_JOINERS = {"of", "the", "and", "de", "la", "al", "in", "on", "for", "to", "bin", "von", "van"}


def _redirect_keeps_name(candidate: str, target: str) -> bool:
    """'Houthi' -> 'Houthis' or 'NFL' -> 'National Football League' are fine;
    'Jane Doe' -> 'John Doe' and 'Gov' -> 'Government' are not."""
    cand = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", candidate)]
    targ = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", target)]
    if candidate.isupper() and len(candidate) >= 2:
        initials = "".join(w[0] for w in targ if w not in _JOINERS)
        if initials == candidate.lower():
            return True
    for w in cand:
        if w in targ:
            continue
        if len(w) >= 5 and any(t.startswith(w) and len(t) - len(w) <= 2 for t in targ):
            continue
        return False
    return True


def _generic_concept(title: str) -> bool:
    words = title.split()
    return len(words) > 1 and any(w.islower() and w not in _JOINERS for w in words[1:])


def lookup(candidates: list[BackgroundCandidate], texts: list[tuple[str, str]], user_agent: str,
           timeout: float = 10.0, client: httpx.Client | None = None) -> list[BackgroundResult]:
    if not candidates:
        return []
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
        "titles": "|".join(c.phrase for c in candidates[:MAX_CANDIDATES]),
        "prop": "extracts|pageprops|info|pageimages",
        "piprop": "thumbnail",
        "pithumbsize": "240",
        "exintro": "1",
        "explaintext": "1",
        "exsentences": "3",
        "exlimit": "max",
        "inprop": "url",
        "ppprop": "disambiguation|wikibase-shortdesc",
    }
    http = client or httpx
    resp = http.get(WIKI_API, params=params, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()
    query = resp.json().get("query", {})
    # Map each candidate to its final page title after normalization/redirects.
    resolve: dict[str, str] = {}
    for step in ("normalized", "redirects"):
        for entry in query.get(step, []):
            resolve[entry["from"]] = entry["to"]
    pages = {p["title"]: p for p in query.get("pages", [])}
    story_terms = _story_terms(texts)
    results: list[BackgroundResult] = []
    seen_urls = set()
    for cand in candidates:
        title = cand.phrase
        while title in resolve and resolve[title] != title:
            title = resolve[title]
        page = pages.get(title)
        if not page or page.get("missing") or page.get("invalid"):
            continue
        props = page.get("pageprops", {})
        short = props.get("wikibase-shortdesc") or ""
        if "disambiguation" in props or title.lower().startswith("list of") or _BAD_DESCRIPTION.search(short):
            continue
        if title != cand.phrase and not _redirect_keeps_name(cand.phrase, title):
            continue
        if cand.method == "entity" and _generic_concept(title):
            continue
        extract = page.get("extract", "") or ""
        ok, _ = _relevant(extract, title, story_terms)
        if not ok:
            continue
        url = page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        description = short or (extract.split(". ")[0][:200] if extract else "")
        thumb = (page.get("thumbnail") or {}).get("source")
        results.append(BackgroundResult(title, url, description, cand.phrase, cand.method, thumb))
        if len(results) >= MAX_LINKS:
            break
    return results

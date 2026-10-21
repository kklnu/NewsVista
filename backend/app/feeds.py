"""Fetch and parse RSS/Atom feeds into plain records."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from .normalize import strip_html, truncate

USER_AGENT = "NewsVista/1.0 (CS403 news aggregation project; RSS reader)"
EXCERPT_LIMIT = 600
FEED_TEXT_LIMIT = 2500


class FeedError(Exception):
    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


@dataclass
class FeedItem:
    title: str
    url: str
    guid: str | None
    published_at: datetime | None  # None = missing or unparseable
    excerpt: str
    feed_text: str
    image_url: str | None = None


@dataclass
class FeedResult:
    http_status: int
    items: list[FeedItem]


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                # feedparser normalizes to UTC struct_time.
                return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
            except (OverflowError, ValueError, TypeError):
                return None
    return None


def _clean_excerpt(text: str) -> str:
    for tail in ("Continue reading...", "Continue reading…"):
        if text.endswith(tail):
            text = text[: -len(tail)].rstrip()
    return text


_NPR_RESIZE = re.compile(r"/resize/\d+x\d+!?/")


def phone_sized_image(url: str | None) -> str | None:
    """Ask image CDNs for a phone-friendly size instead of the full original.

    NPR feeds link to originals (e.g. 8116x5410) that are too large to load in a
    card; their CDN accepts /resize/1200/ in the same URL.
    """
    if not url:
        return url
    if "brightspotcdn.com" in url:
        return _NPR_RESIZE.sub("/resize/1200/quality/80/format/jpeg/", url, count=1)
    return url


_IMG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)


def _image(entry) -> str | None:
    """Largest image the feed itself publishes for the item, if any."""
    candidates = []
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            url = m.get("url", "")
            if url.startswith("https://") and m.get("medium", "image") == "image":
                try:
                    width = int(m.get("width") or 0)
                except ValueError:
                    width = 0
                candidates.append((width, url))
    for enc in entry.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image/") and enc.get("href", "").startswith("https://"):
            candidates.append((0, enc["href"]))
    if candidates:
        url = max(candidates)[1]
        # BBC feeds only list a 240px thumbnail; the same image is served at 800px.
        return url.replace("ichef.bbci.co.uk/ace/standard/240/", "ichef.bbci.co.uk/ace/standard/800/")
    raw = (entry.get("content") or [{}])[0].get("value") or entry.get("summary") or ""
    match = _IMG.search(raw)
    if not (match and match.group(1).startswith("https://")):
        return None
    return phone_sized_image(match.group(1).replace("&amp;", "&"))


def parse_feed(content: bytes) -> list[FeedItem]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise FeedError(f"Unparseable feed: {parsed.get('bozo_exception')!s:.200}")
    items: list[FeedItem] = []
    for entry in parsed.entries:
        title = strip_html(entry.get("title"))
        url = (entry.get("link") or "").strip()
        if not title or not url.startswith("http"):
            continue
        excerpt = _clean_excerpt(strip_html(entry.get("summary") or entry.get("description")))
        feed_text = ""
        if entry.get("content"):
            feed_text = strip_html(entry["content"][0].get("value"))
        items.append(
            FeedItem(
                title=title,
                url=url,
                guid=entry.get("id"),
                published_at=_published(entry),
                excerpt=truncate(excerpt, EXCERPT_LIMIT),
                feed_text=truncate(feed_text, FEED_TEXT_LIMIT) if feed_text and feed_text != excerpt else "",
                image_url=_image(entry),
            )
        )
    return items


def fetch_feed(source: dict, timeout: float = 15.0) -> FeedResult:
    try:
        resp = httpx.get(
            source["feed_url"],
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        )
    except httpx.HTTPError as exc:
        raise FeedError(f"Network error: {type(exc).__name__}: {exc!s:.200}") from exc
    if resp.status_code != 200:
        raise FeedError(f"HTTP {resp.status_code}", resp.status_code)
    return FeedResult(http_status=resp.status_code, items=parse_feed(resp.content))

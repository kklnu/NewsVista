"""Article identity and text cleanup."""
from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that only track the click and never change the article.
_TRACKING_PARAMS = re.compile(r"^(utm_.*|at_.*|cmpid|ftag|ns_.*|ocid|cmp|src|ref|fbclid|gclid|mc_.*)$", re.I)


def normalize_url(url: str) -> str:
    """Canonical form used for duplicate detection.

    https://www.bbc.co.uk/news/articles/x?at_medium=RSS#0 -> https://www.bbc.co.uk/news/articles/x
    """
    parts = urlsplit(url.strip())
    scheme = "https"
    host = parts.netloc.lower()
    path = re.sub(r"/+$", "", parts.path) or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_PARAMS.match(k)]
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


def article_id_for(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:20]


_TAG = re.compile(r"<[^>]+>")
_DROP_BLOCKS = re.compile(r"<(script|style|figure|figcaption|iframe|picture)\b.*?</\1>", re.I | re.S)
_WS = re.compile(r"\s+")


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = _DROP_BLOCKS.sub(" ", raw)
    text = re.sub(r"</(p|div|li|h\d)>|<br\s*/?>", "\n", text, flags=re.I)
    text = _TAG.sub(" ", text)
    text = html.unescape(html.unescape(text))  # some feeds double-escape
    return _WS.sub(" ", text).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def content_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()

"""RSS / Atom reader on the standard library.

Only headline, link, date and a short snippet are kept. Full article text is
never stored (publisher terms), and the snippet is capped at 300 characters.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from shadowdesk.ingest.snapshot import Provenance, SnapshotStore

# The 12 feeds wired into Retail Agent V1 (Google News query feeds are built per need).
FEEDS: dict[str, str] = {
    "wsj_markets": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "wsj_economy": "https://feeds.content.dowjones.io/public/rss/socialeconomyfeed",
    "wsj_tech": "https://feeds.content.dowjones.io/public/rss/RSSWSJD",
    "dow_wsj": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "ft": "https://www.ft.com/rss/home",
    "cnbc": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "marketwatch": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    "seeking_alpha": "https://seekingalpha.com/market_currents.xml",
    "oilprice": "https://oilprice.com/rss/main",
    "fed_press": "https://www.federalreserve.gov/feeds/press_all.xml",
    "fed_research": "https://www.federalreserve.gov/feeds/feds.xml",
}
# NOTE: these URLs are best-known public endpoints and must be checked against
# the n8n RSS nodes' configured URLs on the first live run (parity check P-RSS-URLS).


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


@dataclass(frozen=True)
class Article:
    feed: str
    title: str
    link: str
    published: str  # ISO-8601 or ''
    snippet: str
    prov: Provenance


_TAG = re.compile(r"<[^>]+>")


def _iso(text: str) -> str:
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).isoformat()
    except (TypeError, ValueError):
        return text.strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(feed: str, body: bytes, prov: Provenance) -> list[Article]:
    root = ET.fromstring(body)
    out: list[Article] = []
    for el in root.iter():
        if _local(el.tag) not in {"item", "entry"}:
            continue
        fields: dict[str, str] = {}
        for child in el:
            name = _local(child.tag)
            if name == "link" and child.get("href"):
                fields.setdefault("link", child.get("href", ""))
            elif child.text:
                fields.setdefault(name, child.text.strip())
        title = _TAG.sub("", fields.get("title", "")).strip()
        if not title:
            continue
        snippet = _TAG.sub(" ", fields.get("description", fields.get("summary", "")))
        snippet = re.sub(r"\s+", " ", snippet).strip()[:300]
        published = _iso(fields.get("pubDate", fields.get("published", fields.get("updated", ""))))
        out.append(Article(feed, title, fields.get("link", ""), published, snippet, prov))
    return out


def read_feed(store: SnapshotStore, feed: str, url: str) -> list[Article]:
    body, prov = store.get("rss", feed, url)
    return parse_feed(feed, body, prov)

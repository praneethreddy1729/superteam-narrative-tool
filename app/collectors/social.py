"""Social signal collection from free, public APIs.

Sources:
- Reddit r/solana and r/solanadev (free JSON API, no auth)
- Solana StackExchange (free API, no auth)
- Solana Forum RSS (governance proposals, SIMDs)
- Solana blog RSS
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger(__name__)


async def get_reddit_hot(client: httpx.AsyncClient, subreddit: str, limit: int = 25) -> list[dict]:
    """Fetch hot posts from a subreddit — free, no auth needed."""
    try:
        resp = await client.get(
            f"https://www.reddit.com/r/{subreddit}/hot.json",
            params={"limit": limit, "raw_json": 1},
            headers={"User-Agent": "Mozilla/5.0 (compatible; SolanaNarrativeBot/1.0; research)"},
        )
        if resp.status_code != 200:
            log.warning(f"Reddit r/{subreddit}: {resp.status_code}")
            return []
        posts = resp.json().get("data", {}).get("children", [])
        return [
            {
                "title": p["data"].get("title", ""),
                "score": p["data"].get("score", 0),
                "comments": p["data"].get("num_comments", 0),
                "created_utc": p["data"].get("created_utc", 0),
                "url": p["data"].get("url", ""),
                "flair": p["data"].get("link_flair_text", ""),
                "subreddit": subreddit,
            }
            for p in posts
            if p.get("kind") == "t3"
        ]
    except Exception as e:
        log.warning(f"Reddit r/{subreddit} failed: {e}")
        return []


async def get_stackexchange_hot(client: httpx.AsyncClient) -> list[dict]:
    """Fetch trending Solana StackExchange questions — developer signal."""
    try:
        resp = await client.get(
            "https://api.stackexchange.com/2.3/questions",
            params={"order": "desc", "sort": "hot", "site": "solana", "pagesize": 20, "filter": "default"},
        )
        if resp.status_code != 200:
            return []
        items = resp.json().get("items", [])
        return [
            {
                "title": q.get("title", ""),
                "score": q.get("score", 0),
                "views": q.get("view_count", 0),
                "answers": q.get("answer_count", 0),
                "tags": q.get("tags", []),
                "created": q.get("creation_date", 0),
                "link": q.get("link", ""),
            }
            for q in items
        ]
    except Exception as e:
        log.warning(f"StackExchange failed: {e}")
        return []


async def get_rss_feed(client: httpx.AsyncClient, url: str, source_name: str) -> list[dict]:
    """Parse an RSS feed for recent items."""
    try:
        resp = await client.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        items = []
        for item in root.findall(".//item")[:15]:
            items.append({
                "title": item.findtext("title", ""),
                "link": item.findtext("link", ""),
                "date": item.findtext("pubDate", ""),
                "source": source_name,
            })
        return items
    except Exception as e:
        log.warning(f"RSS {source_name} failed: {e}")
        return []


async def collect() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        results = await asyncio.gather(
            get_reddit_hot(client, "solana", 30),
            get_reddit_hot(client, "solanadev", 20),
            get_stackexchange_hot(client),
            get_rss_feed(client, "https://solana.com/news/rss.xml", "Solana Blog"),
            get_rss_feed(client, "https://forum.solana.com/latest.rss", "Solana Forum"),
            return_exceptions=True,
        )

    def safe(r, default=None):
        if default is None:
            default = []
        return r if not isinstance(r, (Exception, BaseException)) else default

    reddit_solana = safe(results[0])
    reddit_dev = safe(results[1])
    stackexchange = safe(results[2])
    blog = safe(results[3])
    forum = safe(results[4])

    # Build text corpus for narrative discovery
    text_corpus = []
    for post in reddit_solana + reddit_dev:
        if post.get("title"):
            text_corpus.append(post["title"].lower())
    for q in stackexchange:
        if q.get("title"):
            text_corpus.append(q["title"].lower())
        text_corpus.extend(t.lower() for t in q.get("tags", []))
    for item in blog + forum:
        if item.get("title"):
            text_corpus.append(item["title"].lower())

    log.info(f"Social: {len(reddit_solana)} reddit, {len(reddit_dev)} dev, {len(stackexchange)} SE, {len(blog)} blog, {len(forum)} forum")

    return {
        "reddit": {"solana": reddit_solana, "solanadev": reddit_dev},
        "stackexchange": stackexchange,
        "blog": blog,
        "forum": forum,
        "text_corpus": text_corpus,
    }

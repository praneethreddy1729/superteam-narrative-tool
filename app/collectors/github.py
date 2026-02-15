"""GitHub signal collection — efficient, discovery-oriented.

Strategy: Instead of fetching 34 hardcoded repos (84 API calls, guaranteed rate limit),
use 6 strategic search queries that return rich data about the ENTIRE ecosystem.
This discovers new projects rather than just tracking known ones.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import GITHUB_TOKEN, LOOKBACK_DAYS

log = logging.getLogger(__name__)

# Semaphore to stay within GitHub rate limits
_sem = asyncio.Semaphore(5)


def _headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


async def _gh_get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> Any:
    """Rate-limited GitHub GET with retry on 403/429."""
    async with _sem:
        for attempt in range(3):
            try:
                resp = await client.get(url, params=params, headers=_headers())
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (403, 429):
                    wait = min(2 ** attempt * 5, 30)
                    remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                    log.warning(f"GitHub rate limit ({remaining} remaining), retry in {wait}s: {url}")
                    await asyncio.sleep(wait)
                    continue
                log.warning(f"GitHub {resp.status_code} for {url}")
                return None
            except Exception as e:
                log.warning(f"GitHub request failed: {e}")
                await asyncio.sleep(2)
    return None


async def discover_trending_repos(client: httpx.AsyncClient) -> list[dict]:
    """Find trending Solana repos — sorted by stars, recently active."""
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    data = await _gh_get(client, "https://api.github.com/search/repositories", {
        "q": f"topic:solana pushed:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": 50,
    })
    if not data:
        return []
    return _parse_repos(data.get("items", []))


async def discover_new_repos(client: httpx.AsyncClient) -> list[dict]:
    """Find brand-new Solana repos created this month — early signals."""
    first_of_month = datetime.now(timezone.utc).replace(day=1).strftime("%Y-%m-%d")
    data = await _gh_get(client, "https://api.github.com/search/repositories", {
        "q": f"topic:solana created:>{first_of_month}",
        "sort": "stars",
        "order": "desc",
        "per_page": 30,
    })
    if not data:
        return []
    return _parse_repos(data.get("items", []))


async def discover_most_active(client: httpx.AsyncClient) -> list[dict]:
    """Find most recently updated Solana repos — active development."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    data = await _gh_get(client, "https://api.github.com/search/repositories", {
        "q": f"topic:solana pushed:>{since} stars:>10",
        "sort": "updated",
        "order": "desc",
        "per_page": 30,
    })
    if not data:
        return []
    return _parse_repos(data.get("items", []))


async def search_narrative_signal(client: httpx.AsyncClient, query: str) -> dict:
    """Search for repos matching a narrative query and return signal strength."""
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    data = await _gh_get(client, "https://api.github.com/search/repositories", {
        "q": f"{query} pushed:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": 5,
    })
    if not data:
        return {"query": query, "count": 0, "total_stars": 0, "repos": []}
    items = data.get("items", [])
    return {
        "query": query,
        "count": data.get("total_count", len(items)),
        "total_stars": sum(r.get("stargazers_count", 0) for r in items),
        "repos": _parse_repos(items[:3]),
    }


# Focused narrative probes — 8 high-signal queries to stay within unauthenticated rate limits (60/hr)
# Total API calls: 3 discovery + 8 probes = 11 (well within limit)
NARRATIVE_PROBES = [
    "solana AI agent",
    "solana depin",
    "solana stablecoin payment payfi",
    "solana zk compression privacy confidential",
    "solana mev jito trading",
    "solana token-2022 extension RWA",
    "solana liquid staking restaking LST",
    "solana blinks actions gaming",
]


async def collect() -> dict[str, Any]:
    """Main collection — 6 API calls for discovery + 16 for narrative probes = 22 total."""
    async with httpx.AsyncClient(timeout=20) as client:
        # Phase 1: Open-ended discovery (3 calls)
        trending, new_repos, most_active = await asyncio.gather(
            discover_trending_repos(client),
            discover_new_repos(client),
            discover_most_active(client),
        )

        # Phase 2: Narrative-specific probes (16 calls, throttled)
        probe_tasks = [search_narrative_signal(client, q) for q in NARRATIVE_PROBES]
        probe_results = await asyncio.gather(*probe_tasks, return_exceptions=True)
        probes = [r for r in probe_results if isinstance(r, dict)]

    # Extract text corpus for narrative discovery
    all_repos = {r["name"]: r for r in trending + new_repos + most_active}
    text_corpus = []
    for r in all_repos.values():
        text = f"{r.get('description', '')} {' '.join(r.get('topics', []))}"
        if text.strip():
            text_corpus.append(text.lower())

    rate_info = "authenticated" if GITHUB_TOKEN else "unauthenticated (60 req/hr)"
    log.info(f"GitHub: {len(all_repos)} unique repos, {len(probes)} probes, mode={rate_info}")

    return {
        "trending_repos": trending[:15],
        "new_repos": new_repos[:15],
        "most_active": most_active[:15],
        "narrative_probes": probes,
        "text_corpus": text_corpus,
        "unique_repo_count": len(all_repos),
    }


def _parse_repos(items: list[dict]) -> list[dict]:
    return [
        {
            "name": r.get("full_name", ""),
            "description": r.get("description", "") or "",
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "language": r.get("language"),
            "topics": r.get("topics", []),
            "created_at": r.get("created_at", ""),
            "updated_at": r.get("updated_at", ""),
            "open_issues": r.get("open_issues_count", 0),
        }
        for r in items
    ]

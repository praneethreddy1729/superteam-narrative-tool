"""Collect social and ecosystem signals from public sources."""

import httpx
from datetime import datetime, timezone
from typing import Any


# Key ecosystem news/signal sources (public RSS/APIs)
SOLANA_BLOG_FEED = "https://solana.com/news/rss.xml"
HELIUS_BLOG = "https://www.helius.dev/blog"

# Notable KOLs and their known focus areas
SOLANA_KOLS = {
    "toly (Anatoly Yakovenko)": {
        "role": "Co-founder of Solana",
        "focus": ["core protocol", "scalability", "Firedancer", "mobile", "AI"],
        "x_handle": "@aaboronkov",
    },
    "Mert Mumtaz": {
        "role": "CEO of Helius",
        "focus": ["infrastructure", "RPCs", "DAS", "compressed NFTs", "developer tooling"],
        "x_handle": "@0xMert_",
    },
    "Akshay BD": {
        "role": "Head of Strategy, Solana Foundation",
        "focus": ["ecosystem growth", "Superteam", "grants", "community"],
        "x_handle": "@AkshayBD",
    },
    "Chase Barker": {
        "role": "Head of DeFi, Solana Foundation",
        "focus": ["DeFi", "token extensions", "confidential transfers", "stablecoins"],
        "x_handle": "@ChaseBarker",
    },
    "Austin Federa": {
        "role": "Head of Strategy, Solana Foundation",
        "focus": ["institutional adoption", "enterprise", "regulation"],
        "x_handle": "@AustinVirts",
    },
    "Vibhu Norby": {
        "role": "CEO of DRiP",
        "focus": ["consumer apps", "NFTs", "distribution", "creator economy"],
        "x_handle": "@VibhuNorby",
    },
    "Armani Ferrante": {
        "role": "Creator of Anchor Framework",
        "focus": ["developer tooling", "Anchor", "Backpack", "Mad Lads", "xNFTs"],
        "x_handle": "@ArmaniFerrante",
    },
}


async def fetch_solana_ecosystem_projects(client: httpx.AsyncClient) -> list[dict]:
    """Fetch Solana ecosystem projects from public registry."""
    try:
        resp = await client.get(
            "https://raw.githubusercontent.com/solana-labs/ecosystem/main/src/data/ecosystem.json",
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        projects = resp.json()
        # Get recently added/updated
        return [
            {
                "name": p.get("name", ""),
                "category": p.get("category", ""),
                "description": p.get("description", ""),
                "url": p.get("url", ""),
            }
            for p in projects[:50]
        ]
    except Exception:
        return []


async def fetch_recent_solana_news(client: httpx.AsyncClient) -> list[dict]:
    """Aggregate recent Solana ecosystem news from public sources."""
    news_items = []

    # Try Solana blog RSS
    try:
        resp = await client.get(SOLANA_BLOG_FEED, timeout=15)
        if resp.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item")[:10]:
                title = item.findtext("title", "")
                pub_date = item.findtext("pubDate", "")
                link = item.findtext("link", "")
                news_items.append({
                    "source": "Solana Blog",
                    "title": title,
                    "date": pub_date,
                    "url": link,
                })
    except Exception:
        pass

    return news_items


async def get_solana_dapp_rankings(client: httpx.AsyncClient) -> list[dict]:
    """Get Solana dApp usage data from DappRadar-style APIs (via DeFiLlama)."""
    try:
        resp = await client.get("https://api.llama.fi/overview/dexs/solana?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true&dataType=dailyVolume")
        if resp.status_code != 200:
            return []
        data = resp.json()
        protocols = data.get("protocols", [])
        protocols.sort(key=lambda p: p.get("total24h", 0), reverse=True)
        return [
            {
                "name": p.get("name", ""),
                "volume_24h": round(p.get("total24h", 0), 0),
                "volume_7d": round(p.get("total7d", 0), 0),
                "change_7d_pct": round(p.get("change_7d", 0) or 0, 2),
                "category": "DEX",
            }
            for p in protocols[:15]
        ]
    except Exception:
        return []


async def get_solana_nft_signals(client: httpx.AsyncClient) -> dict[str, Any]:
    """Get NFT marketplace volume signals."""
    try:
        resp = await client.get("https://api.llama.fi/overview/nfts/solana?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true")
        if resp.status_code != 200:
            return {}
        data = resp.json()
        total_24h = data.get("total24h", 0)
        total_7d = data.get("total7d", 0)
        change_7d = data.get("change_7d", 0) or 0
        protocols = data.get("protocols", [])
        protocols.sort(key=lambda p: p.get("total24h", 0), reverse=True)
        return {
            "total_volume_24h": round(total_24h, 0),
            "total_volume_7d": round(total_7d, 0),
            "change_7d_pct": round(change_7d, 2),
            "top_marketplaces": [
                {"name": p.get("name", ""), "volume_24h": round(p.get("total24h", 0), 0)}
                for p in protocols[:5]
            ],
        }
    except Exception:
        return {}


async def collect_social_signals() -> dict[str, Any]:
    """Main collection function for social/ecosystem signals."""
    import asyncio

    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(
            fetch_solana_ecosystem_projects(client),
            fetch_recent_solana_news(client),
            get_solana_dapp_rankings(client),
            get_solana_nft_signals(client),
            return_exceptions=True,
        )

    def safe(r: Any, default: Any = []) -> Any:
        return r if not isinstance(r, Exception) else default

    return {
        "collection_time": datetime.now(timezone.utc).isoformat(),
        "ecosystem_projects": safe(results[0]),
        "recent_news": safe(results[1]),
        "dex_rankings": safe(results[2]),
        "nft_signals": safe(results[3], {}),
        "kol_profiles": SOLANA_KOLS,
    }

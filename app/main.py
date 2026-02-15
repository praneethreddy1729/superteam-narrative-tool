"""Solana Narrative Detector — FastAPI application."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.collectors.github_collector import collect_github_signals
from app.collectors.onchain_collector import collect_onchain_signals
from app.collectors.social_collector import collect_social_signals
from app.analyzer import (
    analyze_github_narratives,
    analyze_defi_narratives,
    analyze_social_narratives,
    synthesize_narratives,
    generate_build_ideas,
)

app = FastAPI(
    title="Solana Narrative Detector",
    description="Detects emerging narratives and generates build ideas for the Solana ecosystem",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Cache for collected data
_cache: dict = {}
_cache_time: datetime | None = None
CACHE_TTL_SECONDS = 900  # 15 min


async def get_analysis(force_refresh: bool = False) -> dict:
    """Run full data collection and analysis pipeline."""
    global _cache, _cache_time

    now = datetime.now(timezone.utc)
    if not force_refresh and _cache and _cache_time and (now - _cache_time).seconds < CACHE_TTL_SECONDS:
        return _cache

    github_token = os.getenv("GITHUB_TOKEN")

    # Collect data from all sources
    import asyncio
    github_data, onchain_data, social_data = await asyncio.gather(
        collect_github_signals(github_token),
        collect_onchain_signals(),
        collect_social_signals(),
    )

    # Analyze signals
    github_narratives = analyze_github_narratives(github_data)
    defi_narratives = analyze_defi_narratives(onchain_data)
    social_narratives = analyze_social_narratives(social_data)

    # Synthesize into ranked narratives
    ranked_narratives = synthesize_narratives(github_narratives, defi_narratives, social_narratives)

    # Generate build ideas
    build_ideas = generate_build_ideas(ranked_narratives)

    result = {
        "generated_at": now.isoformat(),
        "period": "Last 14 days (fortnightly)",
        "data_sources": {
            "github": {
                "repos_tracked": len(github_data.get("core_repos", [])),
                "narrative_queries": len(github_data.get("narrative_repos", {})),
            },
            "onchain": {
                "tvl_current": onchain_data.get("tvl", {}).get("current_tvl_usd"),
                "protocols_tracked": len(onchain_data.get("top_protocols", [])),
                "avg_tps": onchain_data.get("network_performance", {}).get("avg_tps"),
            },
            "social": {
                "dex_count": len(social_data.get("dex_rankings", [])),
                "news_items": len(social_data.get("recent_news", [])),
            },
        },
        "narratives": ranked_narratives,
        "build_ideas": build_ideas,
        "raw_signals": {
            "github_narratives": github_narratives,
            "defi_narratives": defi_narratives,
            "social_narratives": social_narratives,
        },
        "github_data": {
            "most_active_repos": github_data.get("most_active_repos", []),
            "most_starred_repos": github_data.get("most_starred_repos", []),
        },
        "onchain_data": {
            "tvl": onchain_data.get("tvl", {}),
            "top_protocols": onchain_data.get("top_protocols", [])[:10],
            "stablecoins": onchain_data.get("stablecoins", {}),
            "network_performance": onchain_data.get("network_performance", {}),
            "supply": onchain_data.get("supply", {}),
        },
    }

    _cache = result
    _cache_time = now
    return result


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard."""
    analysis = await get_analysis()
    return templates.TemplateResponse("dashboard.html", {"request": request, "data": analysis})


@app.get("/api/narratives")
async def api_narratives():
    """JSON API endpoint for narratives."""
    analysis = await get_analysis()
    return {
        "generated_at": analysis["generated_at"],
        "period": analysis["period"],
        "narratives": analysis["narratives"],
        "build_ideas": analysis["build_ideas"],
    }


@app.get("/api/signals")
async def api_signals():
    """JSON API endpoint for raw signals."""
    analysis = await get_analysis()
    return {
        "generated_at": analysis["generated_at"],
        "data_sources": analysis["data_sources"],
        "raw_signals": analysis["raw_signals"],
        "github_data": analysis["github_data"],
        "onchain_data": analysis["onchain_data"],
    }


@app.get("/api/refresh")
async def api_refresh():
    """Force refresh all data."""
    analysis = await get_analysis(force_refresh=True)
    return {"status": "refreshed", "generated_at": analysis["generated_at"]}


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

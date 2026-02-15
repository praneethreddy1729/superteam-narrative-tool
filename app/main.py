"""Solana Narrative Detector — FastAPI application."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.collectors import github, defi, social
from app.analysis.engine import (
    extract_github_signals,
    extract_defi_signals,
    extract_social_signals,
    discover_narratives,
    generate_ideas,
)
from app.analysis.snapshots import save_snapshot, load_previous_snapshot, compute_deltas
from app.config import BASE_DIR, CACHE_TTL_SECONDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Solana Narrative Detector", version="2.0.0")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_cache: dict = {}
_cache_time: datetime | None = None


async def run_pipeline(force: bool = False) -> dict:
    global _cache, _cache_time

    now = datetime.now(timezone.utc)
    if not force and _cache and _cache_time and (now - _cache_time).total_seconds() < CACHE_TTL_SECONDS:
        return _cache

    log.info("Starting data collection pipeline...")

    # Collect from all sources in parallel
    github_data, defi_data, social_data = await asyncio.gather(
        github.collect(),
        defi.collect(),
        social.collect(),
        return_exceptions=True,
    )

    # Handle collection failures gracefully
    if isinstance(github_data, Exception):
        log.error(f"GitHub collection failed: {github_data}")
        github_data = {}
    if isinstance(defi_data, Exception):
        log.error(f"DeFi collection failed: {defi_data}")
        defi_data = {}
    if isinstance(social_data, Exception):
        log.error(f"Social collection failed: {social_data}")
        social_data = {}

    # Extract signals from each source
    github_signals = extract_github_signals(github_data)
    defi_signals = extract_defi_signals(defi_data)
    social_signals = extract_social_signals(social_data)
    all_signals = github_signals + defi_signals + social_signals

    # Build merged text corpus for narrative discovery
    text_corpus = github_data.get("text_corpus", []) + social_data.get("text_corpus", [])

    # Discover and rank narratives
    narratives = discover_narratives(all_signals, text_corpus)

    # Generate data-driven build ideas
    ideas = generate_ideas(narratives, defi_data)

    # Save snapshot and compute temporal deltas
    save_snapshot(narratives, ideas)
    previous = load_previous_snapshot()
    deltas = compute_deltas(narratives, previous)

    # Attach deltas to narratives
    delta_map = {d["name"]: d for d in deltas}
    for n in narratives:
        d = delta_map.get(n["name"], {})
        n["delta"] = d.get("delta", "new")
        n["score_change"] = d.get("score_change", 0)

    result = {
        "generated_at": now.isoformat(),
        "period": "Last 14 days",
        "stats": {
            "github_repos": github_data.get("unique_repo_count", 0),
            "github_probes": len(github_data.get("narrative_probes", [])),
            "reddit_posts": len(social_data.get("reddit", {}).get("solana", [])) + len(social_data.get("reddit", {}).get("solanadev", [])),
            "se_questions": len(social_data.get("stackexchange", [])),
            "signals_total": len(all_signals),
            "tvl_usd": defi_data.get("tvl", {}).get("current_usd"),
            "avg_tps": defi_data.get("network", {}).get("avg_tps"),
            "dex_volume_24h": defi_data.get("dex", {}).get("total_24h_usd"),
        },
        "narratives": narratives,
        "ideas": ideas,
        "deltas": deltas,
        "has_previous": previous is not None,
        # Supporting data for dashboard
        "github": {
            "trending": github_data.get("trending_repos", [])[:10],
            "new_repos": github_data.get("new_repos", [])[:10],
        },
        "defi": {
            "tvl": defi_data.get("tvl", {}),
            "protocols": defi_data.get("protocols", [])[:12],
            "fees": defi_data.get("fees", [])[:10],
            "dex": defi_data.get("dex", {}),
            "stablecoins": defi_data.get("stablecoins", {}),
            "network": defi_data.get("network", {}),
        },
        "social": {
            "reddit_top": sorted(
                social_data.get("reddit", {}).get("solana", []),
                key=lambda p: p.get("score", 0), reverse=True,
            )[:5],
            "se_top": social_data.get("stackexchange", [])[:5],
            "forum": social_data.get("forum", [])[:5],
        },
    }

    _cache = result
    _cache_time = now
    log.info(f"Pipeline complete: {len(narratives)} narratives, {len(ideas)} ideas from {len(all_signals)} signals")
    return result


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    data = await run_pipeline()
    return templates.TemplateResponse("dashboard.html", {"request": request, "d": data})


@app.get("/api/narratives")
async def api_narratives():
    data = await run_pipeline()
    return {"generated_at": data["generated_at"], "narratives": data["narratives"], "ideas": data["ideas"], "deltas": data["deltas"]}


@app.get("/api/signals")
async def api_signals():
    data = await run_pipeline()
    return {"generated_at": data["generated_at"], "stats": data["stats"], "github": data["github"], "defi": data["defi"], "social": data["social"]}


@app.post("/api/refresh")
async def api_refresh():
    data = await run_pipeline(force=True)
    return {"status": "refreshed", "generated_at": data["generated_at"], "narratives_count": len(data["narratives"])}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "ts": datetime.now(timezone.utc).isoformat()}

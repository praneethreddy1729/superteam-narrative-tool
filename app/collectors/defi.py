"""DeFi and on-chain data collection via DeFiLlama + Solana RPC.

DeFiLlama is free, no auth, and comprehensive. We use it for:
- TVL (total + per-protocol with 14d trends)
- Protocol fees/revenue (real usage, not just parked capital)
- DEX volumes
- Stablecoin supply
- Bridge flows (capital rotation signal)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import SOLANA_RPC

log = logging.getLogger(__name__)

LLAMA = "https://api.llama.fi"


async def _get(client: httpx.AsyncClient, url: str, timeout: float = 30) -> Any:
    try:
        resp = await client.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        log.warning(f"DeFiLlama {resp.status_code}: {url}")
    except Exception as e:
        log.warning(f"DeFiLlama failed ({url}): {type(e).__name__}: {e}")
    return None


async def get_tvl_history(client: httpx.AsyncClient) -> dict:
    data = await _get(client, f"{LLAMA}/v2/historicalChainTvl/Solana")
    if not data:
        return {}
    recent = data[-14:]
    current = recent[-1]["tvl"] if recent else 0
    prev = recent[0]["tvl"] if recent else 0
    change = round(((current - prev) / max(prev, 1)) * 100, 2)
    return {
        "current_usd": round(current),
        "prev_14d_usd": round(prev),
        "change_14d_pct": change,
        "daily": [
            {"date": datetime.fromtimestamp(d["date"], tz=timezone.utc).strftime("%Y-%m-%d"), "tvl": round(d["tvl"])}
            for d in recent
        ],
    }


async def get_protocols(client: httpx.AsyncClient) -> list[dict]:
    """Top Solana protocols with growth metrics."""
    data = await _get(client, f"{LLAMA}/protocols")
    if not data:
        return []
    solana = [p for p in data if "Solana" in (p.get("chains") or [])]
    solana.sort(key=lambda p: p.get("tvl", 0), reverse=True)
    return [
        {
            "name": p.get("name", ""),
            "category": p.get("category", ""),
            "tvl_usd": round(p.get("tvl", 0)),
            "change_1d_pct": round(p.get("change_1d") or 0, 2),
            "change_7d_pct": round(p.get("change_7d") or 0, 2),
            "slug": p.get("slug", ""),
        }
        for p in solana[:30]
    ]


async def get_fees(client: httpx.AsyncClient) -> list[dict]:
    """Protocol fee revenue — the best signal for real usage."""
    data = await _get(client, f"{LLAMA}/overview/fees/solana?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true")
    if not data:
        return []
    protocols = data.get("protocols", [])
    protocols.sort(key=lambda p: p.get("total24h") or 0, reverse=True)
    return [
        {
            "name": p.get("name", ""),
            "fees_24h": round(p.get("total24h") or 0),
            "fees_7d": round(p.get("total7d") or 0),
            "change_7d_pct": round(p.get("change_7d") or 0, 2),
        }
        for p in protocols[:20]
        if (p.get("total24h") or 0) > 0
    ]


async def get_dex_volumes(client: httpx.AsyncClient) -> dict:
    data = await _get(client, f"{LLAMA}/overview/dexs/solana?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true&dataType=dailyVolume")
    if not data:
        return {}
    total_24h = data.get("total24h", 0)
    total_7d = data.get("total7d", 0)
    protocols = sorted(data.get("protocols", []), key=lambda p: p.get("total24h") or 0, reverse=True)
    return {
        "total_24h_usd": round(total_24h),
        "total_7d_usd": round(total_7d),
        "change_7d_pct": round(data.get("change_7d") or 0, 2),
        "top_dexes": [
            {"name": p.get("name", ""), "volume_24h": round(p.get("total24h") or 0), "change_7d_pct": round(p.get("change_7d") or 0, 2)}
            for p in protocols[:10]
        ],
    }


async def get_stablecoins(client: httpx.AsyncClient) -> dict:
    data = await _get(client, "https://stablecoins.llama.fi/stablecoins?includePrices=true", timeout=45)
    if not data:
        return {}
    assets = data.get("peggedAssets", [])
    solana_stables = []
    for s in assets:
        chains = s.get("chainCirculating", {})
        if "Solana" in chains:
            mcap = chains["Solana"].get("current", {}).get("peggedUSD", 0)
            if mcap > 0:
                solana_stables.append({"name": s.get("name", ""), "symbol": s.get("symbol", ""), "mcap_usd": round(mcap)})
    solana_stables.sort(key=lambda x: x["mcap_usd"], reverse=True)
    total = sum(s["mcap_usd"] for s in solana_stables)
    return {"total_mcap_usd": round(total), "assets": solana_stables[:10]}


async def get_bridge_flows(client: httpx.AsyncClient) -> dict:
    """Net bridge flows to/from Solana — capital rotation signal."""
    data = await _get(client, f"{LLAMA}/v2/bridges")
    if not data:
        return {}
    bridges = data.get("bridges", data) if isinstance(data, dict) else data
    if isinstance(bridges, list):
        solana_bridges = [b for b in bridges if "Solana" in (b.get("chains", []) if isinstance(b.get("chains"), list) else [b.get("destinationChain", "")])]
        return {"bridge_count": len(solana_bridges), "bridges": [{"name": b.get("displayName", b.get("name", "")), "volume_24h": b.get("lastDailyVolume", 0)} for b in solana_bridges[:5]]}
    return {}


async def get_solana_network(client: httpx.AsyncClient) -> dict:
    """Basic Solana network stats from RPC."""
    try:
        perf_resp = await client.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [10]})
        samples = perf_resp.json().get("result", [])
        total_tx = sum(s.get("numTransactions", 0) for s in samples)
        total_sec = sum(s.get("samplePeriodSecs", 1) for s in samples)
        avg_tps = round(total_tx / max(total_sec, 1), 1)

        supply_resp = await client.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 2, "method": "getSupply"})
        supply = supply_resp.json().get("result", {}).get("value", {})

        return {
            "avg_tps": avg_tps,
            "total_sol": round(supply.get("total", 0) / 1e9),
            "circulating_sol": round(supply.get("circulating", 0) / 1e9),
        }
    except Exception as e:
        log.warning(f"Solana RPC failed: {e}")
        return {}


async def collect() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(
            get_tvl_history(client),
            get_protocols(client),
            get_fees(client),
            get_dex_volumes(client),
            get_stablecoins(client),
            get_bridge_flows(client),
            get_solana_network(client),
            return_exceptions=True,
        )

    def safe(r, default=None):
        if default is None:
            default = {}
        return r if not isinstance(r, (Exception, BaseException)) else default

    return {
        "tvl": safe(results[0]),
        "protocols": safe(results[1], []),
        "fees": safe(results[2], []),
        "dex": safe(results[3]),
        "stablecoins": safe(results[4]),
        "bridges": safe(results[5]),
        "network": safe(results[6]),
    }

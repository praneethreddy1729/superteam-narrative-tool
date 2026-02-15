"""Collect on-chain signals from Solana via public RPC and APIs."""

import httpx
from datetime import datetime, timezone
from typing import Any

SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# Public APIs for on-chain data
DEFILLAMA_BASE = "https://api.llama.fi"
DEFILLAMA_YIELDS = "https://yields.llama.fi"


async def get_solana_tps(client: httpx.AsyncClient) -> dict[str, Any]:
    """Get recent Solana TPS and performance metrics."""
    try:
        resp = await client.post(
            SOLANA_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [10]},
        )
        data = resp.json()
        samples = data.get("result", [])
        if not samples:
            return {"avg_tps": 0, "samples": 0}

        total_txns = sum(s.get("numTransactions", 0) for s in samples)
        total_secs = sum(s.get("samplePeriodSecs", 1) for s in samples)
        return {
            "avg_tps": round(total_txns / max(total_secs, 1), 1),
            "total_transactions_sampled": total_txns,
            "sample_count": len(samples),
        }
    except Exception:
        return {"avg_tps": 0, "error": "failed to fetch"}


async def get_solana_epoch_info(client: httpx.AsyncClient) -> dict[str, Any]:
    """Get current epoch info."""
    try:
        resp = await client.post(
            SOLANA_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": "getEpochInfo"},
        )
        data = resp.json().get("result", {})
        return {
            "epoch": data.get("epoch", 0),
            "slot_index": data.get("slotIndex", 0),
            "slots_in_epoch": data.get("slotsInEpoch", 0),
            "absolute_slot": data.get("absoluteSlot", 0),
            "transaction_count": data.get("transactionCount", 0),
        }
    except Exception:
        return {}


async def get_solana_supply(client: httpx.AsyncClient) -> dict[str, Any]:
    """Get SOL supply info."""
    try:
        resp = await client.post(
            SOLANA_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": "getSupply"},
        )
        value = resp.json().get("result", {}).get("value", {})
        return {
            "total_sol": round(value.get("total", 0) / 1e9, 0),
            "circulating_sol": round(value.get("circulating", 0) / 1e9, 0),
            "non_circulating_sol": round(value.get("nonCirculating", 0) / 1e9, 0),
        }
    except Exception:
        return {}


async def get_defi_tvl_solana(client: httpx.AsyncClient) -> dict[str, Any]:
    """Get Solana DeFi TVL from DeFiLlama."""
    try:
        resp = await client.get(f"{DEFILLAMA_BASE}/v2/historicalChainTvl/Solana")
        data = resp.json()
        if not data:
            return {}

        recent = data[-14:]  # Last 14 days
        current_tvl = recent[-1]["tvl"] if recent else 0
        tvl_14d_ago = recent[0]["tvl"] if recent else 0
        change_pct = round(((current_tvl - tvl_14d_ago) / max(tvl_14d_ago, 1)) * 100, 2)

        return {
            "current_tvl_usd": round(current_tvl, 0),
            "tvl_14d_ago_usd": round(tvl_14d_ago, 0),
            "tvl_change_14d_pct": change_pct,
            "trend": "up" if change_pct > 0 else "down",
            "daily_tvl": [{"date": datetime.fromtimestamp(d["date"], tz=timezone.utc).strftime("%Y-%m-%d"), "tvl": round(d["tvl"], 0)} for d in recent],
        }
    except Exception:
        return {"error": "failed to fetch TVL"}


async def get_top_protocols_solana(client: httpx.AsyncClient) -> list[dict]:
    """Get top Solana DeFi protocols by TVL."""
    try:
        resp = await client.get(f"{DEFILLAMA_BASE}/protocols")
        data = resp.json()
        solana_protocols = [
            p for p in data
            if "Solana" in p.get("chains", []) or "Solana" in p.get("chain", "")
        ]
        solana_protocols.sort(key=lambda p: p.get("tvl", 0), reverse=True)

        results = []
        for p in solana_protocols[:25]:
            change_1d = p.get("change_1d", 0) or 0
            change_7d = p.get("change_7d", 0) or 0
            results.append({
                "name": p.get("name", ""),
                "tvl_usd": round(p.get("tvl", 0), 0),
                "category": p.get("category", ""),
                "change_1d_pct": round(change_1d, 2),
                "change_7d_pct": round(change_7d, 2),
                "chains": p.get("chains", []),
                "slug": p.get("slug", ""),
            })
        return results
    except Exception:
        return []


async def get_stablecoin_data(client: httpx.AsyncClient) -> dict[str, Any]:
    """Get stablecoin data on Solana from DeFiLlama."""
    try:
        resp = await client.get(f"{DEFILLAMA_BASE}/v2/stablecoins?includePrices=true")
        data = resp.json().get("peggedAssets", [])

        solana_stables = []
        for s in data:
            chains = s.get("chainCirculating", {})
            if "Solana" in chains:
                sol_mcap = chains["Solana"].get("current", {}).get("peggedUSD", 0)
                if sol_mcap > 0:
                    solana_stables.append({
                        "name": s.get("name", ""),
                        "symbol": s.get("symbol", ""),
                        "solana_mcap_usd": round(sol_mcap, 0),
                    })

        solana_stables.sort(key=lambda x: x["solana_mcap_usd"], reverse=True)
        total = sum(s["solana_mcap_usd"] for s in solana_stables)

        return {
            "total_stablecoin_mcap_solana": round(total, 0),
            "top_stablecoins": solana_stables[:10],
        }
    except Exception:
        return {}


async def get_yield_data(client: httpx.AsyncClient) -> list[dict]:
    """Get top yield opportunities on Solana."""
    try:
        resp = await client.get(f"{DEFILLAMA_YIELDS}/pools")
        data = resp.json().get("data", [])
        solana_pools = [p for p in data if p.get("chain") == "Solana" and p.get("tvlUsd", 0) > 1_000_000]
        solana_pools.sort(key=lambda p: p.get("tvlUsd", 0), reverse=True)

        return [
            {
                "project": p.get("project", ""),
                "symbol": p.get("symbol", ""),
                "tvl_usd": round(p.get("tvlUsd", 0), 0),
                "apy": round(p.get("apy", 0), 2),
                "apy_mean_30d": round(p.get("apyMean30d", 0), 2),
                "category": p.get("exposure", ""),
            }
            for p in solana_pools[:20]
        ]
    except Exception:
        return []


async def collect_onchain_signals() -> dict[str, Any]:
    """Main collection function for on-chain data."""
    import asyncio

    async with httpx.AsyncClient(timeout=30) as client:
        results = await asyncio.gather(
            get_solana_tps(client),
            get_solana_epoch_info(client),
            get_solana_supply(client),
            get_defi_tvl_solana(client),
            get_top_protocols_solana(client),
            get_stablecoin_data(client),
            get_yield_data(client),
            return_exceptions=True,
        )

    def safe(r: Any) -> Any:
        return r if not isinstance(r, Exception) else {"error": str(r)}

    return {
        "collection_time": datetime.now(timezone.utc).isoformat(),
        "network_performance": safe(results[0]),
        "epoch_info": safe(results[1]),
        "supply": safe(results[2]),
        "tvl": safe(results[3]),
        "top_protocols": safe(results[4]),
        "stablecoins": safe(results[5]),
        "top_yields": safe(results[6]),
    }

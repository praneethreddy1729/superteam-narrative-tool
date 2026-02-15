"""Analyze collected signals to detect emerging narratives and generate build ideas."""

from datetime import datetime, timezone
from typing import Any


def analyze_github_narratives(github_data: dict[str, Any]) -> list[dict]:
    """Detect narratives from GitHub activity patterns."""
    narratives = []
    narrative_repos = github_data.get("narrative_repos", {})

    scored = []
    for query, data in narrative_repos.items():
        repo_count = data.get("repo_count", 0)
        total_stars = data.get("total_stars", 0)
        new_repos = data.get("new_repos", 0)

        # Score = weighted combination of activity signals
        score = (repo_count * 2) + (new_repos * 5) + (total_stars / 100)
        if repo_count > 0:
            scored.append({
                "query": query,
                "score": round(score, 1),
                "repo_count": repo_count,
                "total_stars": total_stars,
                "new_repos": new_repos,
                "top_repos": data.get("top_repos", []),
            })

    scored.sort(key=lambda x: x["score"], reverse=True)

    for item in scored[:6]:
        narratives.append({
            "source": "github",
            "signal": item["query"].replace("solana ", ""),
            "strength": item["score"],
            "evidence": f"{item['repo_count']} active repos, {item['new_repos']} new this month, {item['total_stars']} total stars",
            "top_repos": [r.get("name", "") for r in item["top_repos"][:3]],
        })

    return narratives


def analyze_defi_narratives(onchain_data: dict[str, Any]) -> list[dict]:
    """Detect narratives from DeFi/on-chain data."""
    narratives = []

    # TVL trend
    tvl = onchain_data.get("tvl", {})
    tvl_change = tvl.get("tvl_change_14d_pct", 0)
    current_tvl = tvl.get("current_tvl_usd", 0)
    if current_tvl:
        direction = "growing" if tvl_change > 0 else "contracting"
        narratives.append({
            "source": "onchain",
            "signal": f"Solana DeFi TVL {direction}",
            "strength": abs(tvl_change),
            "evidence": f"TVL at ${current_tvl/1e9:.2f}B, {tvl_change:+.1f}% over 14 days",
            "data": {"current_tvl": current_tvl, "change_pct": tvl_change},
        })

    # Protocol category analysis
    protocols = onchain_data.get("top_protocols", [])
    if isinstance(protocols, list):
        category_tvl: dict[str, float] = {}
        category_growth: dict[str, list[float]] = {}
        for p in protocols:
            cat = p.get("category", "Unknown")
            category_tvl[cat] = category_tvl.get(cat, 0) + p.get("tvl_usd", 0)
            change = p.get("change_7d_pct", 0)
            if change:
                category_growth.setdefault(cat, []).append(change)

        # Find fastest growing categories
        cat_avg_growth = {}
        for cat, changes in category_growth.items():
            if len(changes) >= 2:
                cat_avg_growth[cat] = sum(changes) / len(changes)

        for cat, avg in sorted(cat_avg_growth.items(), key=lambda x: x[1], reverse=True)[:3]:
            if avg > 2:  # Only significant growth
                tvl = category_tvl.get(cat, 0)
                narratives.append({
                    "source": "defi",
                    "signal": f"{cat} sector growth",
                    "strength": round(avg, 1),
                    "evidence": f"Average {avg:+.1f}% 7d growth across protocols, ${tvl/1e6:.0f}M category TVL",
                    "data": {"category": cat, "avg_growth": avg, "tvl": tvl},
                })

    # Stablecoin growth
    stables = onchain_data.get("stablecoins", {})
    total_stable = stables.get("total_stablecoin_mcap_solana", 0)
    if total_stable > 1e9:
        narratives.append({
            "source": "onchain",
            "signal": "Stablecoin ecosystem expansion",
            "strength": round(total_stable / 1e9, 1),
            "evidence": f"${total_stable/1e9:.2f}B total stablecoin supply on Solana",
            "data": {"total_mcap": total_stable, "top": stables.get("top_stablecoins", [])[:3]},
        })

    return narratives


def analyze_social_narratives(social_data: dict[str, Any]) -> list[dict]:
    """Detect narratives from social/ecosystem signals."""
    narratives = []

    # DEX volume trends
    dex_rankings = social_data.get("dex_rankings", [])
    if dex_rankings:
        total_24h = sum(d.get("volume_24h", 0) for d in dex_rankings)
        growing_dexes = [d for d in dex_rankings if d.get("change_7d_pct", 0) > 10]
        if total_24h > 0:
            narratives.append({
                "source": "market",
                "signal": "DEX trading activity",
                "strength": round(total_24h / 1e6, 0),
                "evidence": f"${total_24h/1e6:.0f}M 24h DEX volume, {len(growing_dexes)} DEXes growing >10% WoW",
                "data": {"total_volume_24h": total_24h, "top_dex": dex_rankings[0] if dex_rankings else {}},
            })

    # NFT market signals
    nft = social_data.get("nft_signals", {})
    nft_change = nft.get("change_7d_pct", 0)
    nft_vol = nft.get("total_volume_24h", 0)
    if nft_vol > 0:
        narratives.append({
            "source": "market",
            "signal": "NFT market activity",
            "strength": abs(nft_change) if nft_change else 0,
            "evidence": f"${nft_vol/1e3:.0f}K 24h NFT volume, {nft_change:+.1f}% WoW",
            "data": nft,
        })

    return narratives


def synthesize_narratives(
    github_narratives: list[dict],
    defi_narratives: list[dict],
    social_narratives: list[dict],
) -> list[dict]:
    """Combine all narrative signals into ranked, synthesized narratives."""
    all_signals = github_narratives + defi_narratives + social_narratives

    # Group related signals into meta-narratives
    meta_narratives = {
        "AI Agents & Autonomous Systems": {
            "keywords": ["AI agent", "agent", "autonomous"],
            "signals": [],
            "description": "",
        },
        "DePIN & Physical Infrastructure": {
            "keywords": ["depin", "physical", "helium", "mobile"],
            "signals": [],
            "description": "",
        },
        "Restaking & Validator Economics": {
            "keywords": ["restaking", "validator", "staking", "liquid staking"],
            "signals": [],
            "description": "",
        },
        "Real World Assets (RWA) & Tokenization": {
            "keywords": ["RWA", "tokeniz", "real world"],
            "signals": [],
            "description": "",
        },
        "PayFi & Stablecoin Payments": {
            "keywords": ["payfi", "stablecoin", "payment", "USDC", "USDT"],
            "signals": [],
            "description": "",
        },
        "ZK Compression & Scalability": {
            "keywords": ["zk compression", "compressed", "scalab"],
            "signals": [],
            "description": "",
        },
        "MEV & Trading Infrastructure": {
            "keywords": ["mev", "jito", "trading", "DEX", "perps"],
            "signals": [],
            "description": "",
        },
        "Token Extensions & Programmable Assets": {
            "keywords": ["token extension", "confidential transfer", "programmable"],
            "signals": [],
            "description": "",
        },
        "DeFi TVL & Yield Growth": {
            "keywords": ["TVL", "DeFi", "yield", "lending", "Liquid"],
            "signals": [],
            "description": "",
        },
        "Consumer Apps & Blinks": {
            "keywords": ["blinks", "consumer", "mobile", "actions", "creator"],
            "signals": [],
            "description": "",
        },
    }

    for signal in all_signals:
        signal_text = signal.get("signal", "").lower() + " " + signal.get("evidence", "").lower()
        for name, meta in meta_narratives.items():
            for kw in meta["keywords"]:
                if kw.lower() in signal_text:
                    meta["signals"].append(signal)
                    break

    # Score and rank meta-narratives
    ranked = []
    for name, meta in meta_narratives.items():
        if not meta["signals"]:
            continue
        total_strength = sum(s.get("strength", 0) for s in meta["signals"])
        source_diversity = len(set(s.get("source", "") for s in meta["signals"]))
        composite_score = total_strength * (1 + 0.3 * source_diversity)

        ranked.append({
            "narrative": name,
            "score": round(composite_score, 1),
            "signal_count": len(meta["signals"]),
            "source_diversity": source_diversity,
            "signals": meta["signals"],
            "sources": list(set(s.get("source", "") for s in meta["signals"])),
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


def generate_build_ideas(ranked_narratives: list[dict]) -> list[dict]:
    """Generate concrete product ideas from top narratives."""
    ideas_map: dict[str, list[dict]] = {
        "AI Agents & Autonomous Systems": [
            {
                "title": "Solana Agent Marketplace",
                "description": "A decentralized marketplace where AI agents can be deployed, discovered, and monetized. Agents register on-chain with their capabilities, users pay SOL/USDC to use them, and agent creators earn revenue. Includes reputation scoring based on task completion rates.",
                "target_users": "AI developers, DeFi traders, DAOs needing automation",
                "solana_integration": "On-chain agent registry program, SPL token payments, transaction history as agent reputation",
                "complexity": "Medium-High",
            },
            {
                "title": "Agent-Powered Portfolio Rebalancer",
                "description": "An autonomous AI agent that monitors Solana DeFi positions across Jupiter, Drift, Kamino, and MarginFi — automatically rebalancing based on market conditions, yield shifts, and risk parameters set by the user.",
                "target_users": "DeFi power users, fund managers",
                "solana_integration": "CPI calls to major Solana DeFi protocols, Pyth price feeds, Jito bundles for MEV-protected execution",
                "complexity": "High",
            },
        ],
        "DePIN & Physical Infrastructure": [
            {
                "title": "DePIN Network Health Dashboard",
                "description": "A unified dashboard tracking all Solana DePIN networks (Helium, Hivemapper, Render, etc.) — showing coverage maps, node economics, reward rates, and growth trends. Helps investors and operators compare DePIN opportunities.",
                "target_users": "DePIN operators, investors, analysts",
                "solana_integration": "Reads on-chain state from Helium, Render, and other DePIN programs",
                "complexity": "Medium",
            },
        ],
        "Restaking & Validator Economics": [
            {
                "title": "Solana Restaking Yield Optimizer",
                "description": "A tool that compares LST yields (mSOL, jitoSOL, bSOL, etc.), factors in restaking options, and recommends optimal staking strategies. Includes auto-compounding and one-click migration between LSTs.",
                "target_users": "SOL holders, validators, LST farmers",
                "solana_integration": "Stake pool programs, LST mint/redeem, Sanctum router",
                "complexity": "Medium",
            },
        ],
        "Real World Assets (RWA) & Tokenization": [
            {
                "title": "RWA Issuance Toolkit for Solana",
                "description": "A no-code platform for tokenizing real-world assets on Solana using Token Extensions (transfer hooks, confidential transfers). Supports compliance features like KYC gating, transfer restrictions, and dividend distribution.",
                "target_users": "Asset managers, real estate firms, fund administrators",
                "solana_integration": "Token-2022 extensions, transfer hooks, confidential transfers",
                "complexity": "High",
            },
        ],
        "PayFi & Stablecoin Payments": [
            {
                "title": "Solana PayFi SDK for Merchants",
                "description": "A drop-in SDK enabling any merchant (Shopify, WooCommerce, mobile POS) to accept USDC/PYUSD on Solana with instant settlement — no crypto knowledge needed. Handles QR code generation, payment verification, and fiat off-ramping.",
                "target_users": "E-commerce merchants, physical retailers, payment processors",
                "solana_integration": "SPL token transfers, Solana Pay protocol, token extensions for receipts",
                "complexity": "Medium",
            },
        ],
        "ZK Compression & Scalability": [
            {
                "title": "Compressed Token Airdrop Platform",
                "description": "A platform that uses ZK Compression to distribute tokens to millions of wallets at 1/1000th the cost of regular token accounts. Perfect for community airdrops, loyalty programs, and mass distribution events.",
                "target_users": "Token projects, DAOs, marketing teams",
                "solana_integration": "Light Protocol ZK Compression, compressed token accounts, Merkle trees",
                "complexity": "Medium-High",
            },
        ],
        "MEV & Trading Infrastructure": [
            {
                "title": "MEV-Protected DEX Aggregator API",
                "description": "An API layer that routes Solana DEX trades through Jito bundles and private transaction channels to minimize MEV extraction. Includes sandwich attack detection, optimal routing across Jupiter/Phoenix/Raydium, and post-trade analytics.",
                "target_users": "Trading bots, DEX frontends, institutional traders",
                "solana_integration": "Jito tip distribution, Jupiter swap API, Solana transaction simulation",
                "complexity": "High",
            },
        ],
        "Token Extensions & Programmable Assets": [
            {
                "title": "Token Extensions Explorer & Builder",
                "description": "A visual tool for creating and managing Token-2022 tokens with extensions (transfer fees, interest bearing, non-transferable, confidential). Includes a drag-and-drop token builder, live extension previewer, and deployment to mainnet.",
                "target_users": "Token creators, compliance teams, DeFi builders",
                "solana_integration": "Token-2022 program, all extension types, Metaplex metadata",
                "complexity": "Medium",
            },
        ],
        "DeFi TVL & Yield Growth": [
            {
                "title": "Solana Yield Aggregator with Auto-Compounding",
                "description": "An automated vault system that optimizes yield across Solana DeFi (Kamino, MarginFi, Drift, Orca) — auto-compounds rewards, rebalances across strategies, and provides a single dashboard for all positions.",
                "target_users": "Yield farmers, passive DeFi users",
                "solana_integration": "CPI into lending protocols, DEX LPs, LST staking",
                "complexity": "High",
            },
        ],
        "Consumer Apps & Blinks": [
            {
                "title": "Blinks-Powered Social Commerce Platform",
                "description": "A platform that generates Solana Blinks (blockchain links) for social commerce — embed buy/tip/subscribe actions directly in tweets, posts, and messages. Creators set up storefronts, fans interact via Blinks without leaving their social feed.",
                "target_users": "Content creators, social media influencers, small businesses",
                "solana_integration": "Solana Actions/Blinks spec, SPL token transfers, on-chain receipts",
                "complexity": "Medium",
            },
        ],
    }

    ideas = []
    for narrative in ranked_narratives[:5]:
        name = narrative["narrative"]
        if name in ideas_map:
            for idea in ideas_map[name]:
                ideas.append({
                    **idea,
                    "tied_narrative": name,
                    "narrative_score": narrative["score"],
                    "narrative_signals": len(narrative["signals"]),
                })

    # Ensure we have at least 5 ideas
    if len(ideas) < 5:
        # Pull from remaining narratives
        for narrative in ranked_narratives[5:]:
            name = narrative["narrative"]
            if name in ideas_map:
                for idea in ideas_map[name]:
                    ideas.append({
                        **idea,
                        "tied_narrative": name,
                        "narrative_score": narrative["score"],
                        "narrative_signals": len(narrative["signals"]),
                    })
                    if len(ideas) >= 5:
                        break
            if len(ideas) >= 5:
                break

    return ideas[:7]  # Return top 5-7 ideas

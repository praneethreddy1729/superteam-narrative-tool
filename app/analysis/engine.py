"""Narrative detection engine — discovers and ranks emerging narratives.

Unlike keyword matching, this engine:
1. Extracts signals from each data source independently
2. Discovers narrative themes from text corpus (repo descriptions, Reddit titles, SE questions)
3. Scores narratives using normalized, comparable metrics
4. Generates data-driven build ideas with real numbers interpolated
"""

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


# ─── Signal Extraction ──────────────────────────────────────────────

def extract_github_signals(github: dict) -> list[dict]:
    """Extract narrative signals from GitHub data."""
    signals = []

    # From narrative probes — which search terms have the most activity
    for probe in github.get("narrative_probes", []):
        count = probe.get("count", 0)
        stars = probe.get("total_stars", 0)
        if count > 0:
            signals.append({
                "source": "github",
                "type": "narrative_probe",
                "topic": probe["query"].replace("solana ", ""),
                "metrics": {"repo_count": count, "total_stars": stars},
                "text": f"{count} active repos matching '{probe['query']}' with {stars} combined stars",
                "strength_raw": count,
            })

    # From new repos — what categories are being created
    for repo in github.get("new_repos", []):
        topics = repo.get("topics", [])
        desc = repo.get("description", "")
        if topics or desc:
            signals.append({
                "source": "github",
                "type": "new_repo",
                "topic": ", ".join(topics[:3]) if topics else desc[:60],
                "metrics": {"stars": repo["stars"], "name": repo["name"]},
                "text": f"New repo: {repo['name']} ({repo['stars']} stars) — {desc[:80]}",
                "strength_raw": max(repo["stars"], 1),
            })

    # From trending — what's getting the most attention
    for repo in github.get("trending_repos", [])[:5]:
        signals.append({
            "source": "github",
            "type": "trending",
            "topic": ", ".join(repo.get("topics", [])[:3]),
            "metrics": {"stars": repo["stars"], "name": repo["name"]},
            "text": f"Trending: {repo['name']} ({repo['stars']} stars)",
            "strength_raw": repo["stars"],
        })

    return signals


def extract_defi_signals(defi: dict) -> list[dict]:
    """Extract narrative signals from DeFi/on-chain data."""
    signals = []

    # TVL trend — is capital flowing in or out?
    tvl = defi.get("tvl", {})
    tvl_change = tvl.get("change_14d_pct", 0)
    tvl_current = tvl.get("current_usd", 0)
    if tvl_current:
        direction = "inflow" if tvl_change > 0 else "outflow"
        signals.append({
            "source": "defi",
            "type": "tvl_trend",
            "topic": f"TVL {direction}",
            "metrics": {"tvl_usd": tvl_current, "change_pct": tvl_change},
            "text": f"Solana TVL: ${tvl_current/1e9:.2f}B ({tvl_change:+.1f}% in 14d)",
            "strength_raw": abs(tvl_change),
        })

    # Category analysis — which sectors are growing fastest
    protocols = defi.get("protocols", [])
    if protocols:
        cat_data: dict[str, dict] = {}
        for p in protocols:
            cat = p.get("category", "Other")
            if cat not in cat_data:
                cat_data[cat] = {"tvl": 0, "changes": [], "protocols": []}
            cat_data[cat]["tvl"] += p.get("tvl_usd", 0)
            if c7 := p.get("change_7d_pct"):
                cat_data[cat]["changes"].append(c7)
            cat_data[cat]["protocols"].append(p["name"])

        for cat, d in sorted(cat_data.items(), key=lambda x: x[1]["tvl"], reverse=True):
            avg_change = sum(d["changes"]) / len(d["changes"]) if d["changes"] else 0
            if d["tvl"] > 5_000_000:  # >$5M TVL
                signals.append({
                    "source": "defi",
                    "type": "category",
                    "topic": cat,
                    "metrics": {"tvl_usd": d["tvl"], "avg_change_7d": round(avg_change, 2), "protocol_count": len(d["protocols"]), "top_protocols": d["protocols"][:3]},
                    "text": f"{cat}: ${d['tvl']/1e6:.0f}M TVL across {len(d['protocols'])} protocols ({avg_change:+.1f}% avg 7d)",
                    "strength_raw": abs(avg_change) if avg_change else d["tvl"] / 1e9,
                })

    # Fee revenue — the strongest signal for real usage
    fees = defi.get("fees", [])
    if fees:
        total_fees_24h = sum(f.get("fees_24h", 0) for f in fees)
        growing = [f for f in fees if (f.get("change_7d_pct") or 0) > 10]
        signals.append({
            "source": "defi",
            "type": "fees",
            "topic": "protocol revenue",
            "metrics": {"total_24h": total_fees_24h, "growing_count": len(growing), "top_earners": fees[:3]},
            "text": f"${total_fees_24h/1e3:.0f}K daily protocol fees, {len(growing)} protocols with >10% weekly fee growth",
            "strength_raw": total_fees_24h / 1000,
        })

    # Stablecoin supply
    stables = defi.get("stablecoins", {})
    total_stable = stables.get("total_mcap_usd", 0)
    if total_stable > 1e9:
        non_usdc_usdt = sum(
            s["mcap_usd"] for s in stables.get("assets", [])
            if s["symbol"] not in ("USDC", "USDT")
        )
        signals.append({
            "source": "defi",
            "type": "stablecoins",
            "topic": "stablecoin ecosystem",
            "metrics": {"total_mcap": total_stable, "non_major_mcap": non_usdc_usdt, "assets": stables.get("assets", [])[:5]},
            "text": f"${total_stable/1e9:.1f}B stablecoin supply, ${non_usdc_usdt/1e6:.0f}M in non-USDC/USDT stables",
            "strength_raw": total_stable / 1e9,
        })

    # DEX volumes
    dex = defi.get("dex", {})
    dex_24h = dex.get("total_24h_usd", 0)
    dex_change = dex.get("change_7d_pct", 0)
    if dex_24h:
        signals.append({
            "source": "defi",
            "type": "dex_volume",
            "topic": "DEX trading",
            "metrics": {"volume_24h": dex_24h, "change_7d_pct": dex_change, "top_dexes": dex.get("top_dexes", [])[:3]},
            "text": f"${dex_24h/1e6:.0f}M daily DEX volume ({dex_change:+.1f}% WoW)",
            "strength_raw": abs(dex_change) if dex_change else dex_24h / 1e8,
        })

    return signals


def extract_social_signals(social: dict) -> list[dict]:
    """Extract narrative signals from social data."""
    signals = []

    # Reddit engagement — what's the community talking about
    reddit_all = social.get("reddit", {}).get("solana", []) + social.get("reddit", {}).get("solanadev", [])
    if reddit_all:
        # Top posts by engagement
        top_posts = sorted(reddit_all, key=lambda p: p.get("score", 0) + p.get("comments", 0), reverse=True)[:5]
        for post in top_posts:
            signals.append({
                "source": "social",
                "type": "reddit",
                "topic": post.get("flair", "discussion"),
                "metrics": {"score": post["score"], "comments": post["comments"], "title": post["title"]},
                "text": f'Reddit ({post["score"]}↑, {post["comments"]} comments): "{post["title"][:80]}"',
                "strength_raw": post["score"] + post["comments"] * 2,
            })

    # StackExchange — developer questions reveal what's being built
    se = social.get("stackexchange", [])
    if se:
        tag_counts = Counter()
        for q in se:
            tag_counts.update(q.get("tags", []))
        top_tags = tag_counts.most_common(10)
        if top_tags:
            signals.append({
                "source": "social",
                "type": "developer_questions",
                "topic": "developer activity",
                "metrics": {"top_tags": dict(top_tags), "question_count": len(se)},
                "text": f"{len(se)} active dev questions, top topics: {', '.join(t[0] for t in top_tags[:5])}",
                "strength_raw": len(se),
            })

    # Forum — governance and protocol-level discussions
    forum = social.get("forum", [])
    if forum:
        signals.append({
            "source": "social",
            "type": "governance",
            "topic": "governance",
            "metrics": {"items": [{"title": f["title"], "link": f.get("link", "")} for f in forum[:5]]},
            "text": f"{len(forum)} recent governance discussions: {forum[0]['title'][:60]}",
            "strength_raw": len(forum),
        })

    return signals


# ─── Narrative Discovery ─────────────────────────────────────────────

# Topic keywords that map signals to narrative themes.
# Unlike the old approach, these are used AFTER signal extraction
# and augmented by text corpus analysis to discover unknown themes.
KNOWN_THEMES = {
    "AI & Autonomous Agents": ["ai agent", "agent", "autonomous", "eliza", "sendai", "llm", "machine learning"],
    "Privacy & Confidential Transfers": ["privacy", "confidential", "zk proof", "shielded", "private"],
    "Stablecoin & PayFi Expansion": ["stablecoin", "payfi", "payment", "usdc", "usdt", "pyusd", "pay"],
    "DePIN & Physical Infrastructure": ["depin", "helium", "hivemapper", "render", "physical infrastructure", "iot"],
    "Liquid Staking & Restaking": ["liquid staking", "lst", "restaking", "msol", "jitosol", "bsol", "sanctum"],
    "Real World Assets (RWA)": ["rwa", "tokeniz", "real world", "securities", "equity"],
    "ZK Compression & Scalability": ["zk compression", "compressed", "light protocol", "scalab"],
    "MEV & Trading Infrastructure": ["mev", "jito", "sandwich", "frontrun", "order flow"],
    "Token Extensions (Token-2022)": ["token-2022", "token extension", "transfer hook", "interest bearing"],
    "Consumer Apps & Blinks": ["blinks", "actions", "consumer", "social commerce", "creator"],
    "Gaming & Entertainment": ["gaming", "game", "nft", "metaverse", "play"],
    "Infrastructure & Validators": ["firedancer", "validator", "alpenglow", "consensus", "finality"],
    "Perpetuals & Derivatives": ["perp", "perpetual", "futures", "options", "derivative"],
    "Prediction Markets": ["prediction", "betting", "oracle", "forecast"],
    "Cross-Chain & Bridges": ["bridge", "cross-chain", "wormhole", "layerzero", "interop"],
}


def _normalize_scores(values: list[float]) -> list[float]:
    """Min-max normalize to 0-100 scale."""
    if not values or max(values) == min(values):
        return [50.0] * len(values)
    mn, mx = min(values), max(values)
    return [round((v - mn) / (mx - mn) * 100, 1) for v in values]


def discover_narratives(all_signals: list[dict], text_corpus: list[str]) -> list[dict]:
    """Discover and rank narratives from signals + text corpus.

    Two-pronged approach:
    1. Match signals to known themes (catches expected narratives)
    2. Extract frequent bigrams from text corpus (catches unexpected themes)
    """
    # Phase 1: Theme matching
    theme_signals: dict[str, list[dict]] = {name: [] for name in KNOWN_THEMES}

    for signal in all_signals:
        signal_text = f"{signal.get('topic', '')} {signal.get('text', '')}".lower()
        for theme_name, keywords in KNOWN_THEMES.items():
            if any(kw in signal_text for kw in keywords):
                theme_signals[theme_name].append(signal)

    # Phase 2: Text corpus bigram analysis for unknown themes
    unknown_signals = _discover_unknown_themes(text_corpus, all_signals)

    # Score themes
    narratives = []
    for theme_name, signals in theme_signals.items():
        if not signals:
            continue

        # Normalized scoring: each signal contributes its normalized strength
        sources = list(set(s["source"] for s in signals))
        raw_strengths = [s.get("strength_raw", 0) for s in signals]

        # Source diversity bonus (multi-source corroboration is strong)
        diversity_multiplier = 1.0 + 0.4 * (len(sources) - 1)

        # Composite: average normalized strength × diversity × signal count factor
        avg_strength = sum(raw_strengths) / len(raw_strengths) if raw_strengths else 0
        signal_count_factor = min(len(signals) / 3, 2.0)  # Diminishing returns past 6 signals
        raw_score = avg_strength * diversity_multiplier * signal_count_factor

        narratives.append({
            "name": theme_name,
            "raw_score": raw_score,
            "signal_count": len(signals),
            "sources": sources,
            "source_diversity": len(sources),
            "signals": signals,
            "discovered": False,
        })

    # Add unknown/discovered themes
    for theme in unknown_signals:
        narratives.append(theme)

    # Normalize final scores to 0-100
    if narratives:
        raw_scores = [n["raw_score"] for n in narratives]
        normalized = _normalize_scores(raw_scores)
        for n, score in zip(narratives, normalized):
            n["score"] = score

    narratives.sort(key=lambda n: n.get("score", 0), reverse=True)
    return narratives


def _discover_unknown_themes(text_corpus: list[str], all_signals: list[dict]) -> list[dict]:
    """Analyze text corpus for emergent themes not in KNOWN_THEMES."""
    if not text_corpus:
        return []

    # Extract significant bigrams
    stop_words = {"the", "and", "for", "with", "that", "this", "from", "have", "are", "was", "how", "can",
                  "you", "your", "what", "not", "but", "has", "any", "get", "use", "new", "all", "one",
                  "solana", "sol", "token", "crypto", "blockchain", "web3", "program", "account",
                  "bot", "trading", "open", "source", "arbitrage", "sniper", "copy", "volume",
                  "github", "com", "http", "https", "npm", "install", "run", "build", "test",
                  "based", "using", "built", "made", "simple", "fast", "smart", "best", "free",
                  "chain", "bitcoin", "ethereum", "wallet", "protocol", "network", "transaction",
                  "contract", "swap", "dapp", "defi", "nft", "api", "sdk", "cli", "rust",
                  "typescript", "javascript", "python", "anchor", "client", "server", "data",
                  "price", "market", "order", "transfer", "address", "key", "sign", "hash",
                  "block", "validator", "node", "stake", "reward", "mint", "burn", "supply"}
    bigram_counts: Counter = Counter()

    for text in text_corpus:
        words = re.findall(r"[a-z]+", text)
        words = [w for w in words if w not in stop_words and len(w) > 2]
        for i in range(len(words) - 1):
            bigram_counts[(words[i], words[i + 1])] += 1

    # Filter to significant bigrams (appear 3+ times)
    significant = [(bg, count) for bg, count in bigram_counts.most_common(30) if count >= 3]

    # Check which bigrams DON'T match any known theme
    all_known_keywords = set()
    for keywords in KNOWN_THEMES.values():
        for kw in keywords:
            all_known_keywords.update(re.findall(r"[a-z]+", kw.lower()))

    unknown_themes = []
    for (w1, w2), count in significant:
        if w1 not in all_known_keywords and w2 not in all_known_keywords:
            theme_name = f"{w1.title()} {w2.title()} (Emerging)"
            unknown_themes.append({
                "name": theme_name,
                "raw_score": count * 3,  # Weight discovered themes higher for novelty
                "signal_count": count,
                "sources": ["text_analysis"],
                "source_diversity": 1,
                "signals": [{"source": "text_analysis", "type": "bigram", "topic": f"{w1} {w2}",
                             "text": f'Emerging topic "{w1} {w2}" appeared {count} times across sources',
                             "metrics": {"frequency": count}, "strength_raw": count}],
                "discovered": True,
            })

    return unknown_themes[:3]  # Top 3 discovered themes


# ─── Build Idea Generation ────────────────────────────────────────────

def generate_ideas(narratives: list[dict], defi_data: dict) -> list[dict]:
    """Generate build ideas dynamically from actual narrative data.

    Unlike static lookup tables, these ideas interpolate real protocol names,
    TVL numbers, and growth rates from the collected data.
    """
    protocols = defi_data.get("protocols", [])
    fees = defi_data.get("fees", [])
    dex = defi_data.get("dex", {})
    stables = defi_data.get("stablecoins", {})

    top_protocols = [p["name"] for p in protocols[:5]] if protocols else ["Jupiter", "Raydium"]
    top_fee_earners = [f["name"] for f in fees[:3]] if fees else ["Jupiter", "Raydium"]
    top_dexes = [d["name"] for d in dex.get("top_dexes", [])[:3]] if dex.get("top_dexes") else ["Jupiter"]
    tvl_str = f"${defi_data.get('tvl', {}).get('current_usd', 0) / 1e9:.1f}B"
    stable_str = f"${stables.get('total_mcap_usd', 0) / 1e9:.1f}B"
    dex_vol = f"${dex.get('total_24h_usd', 0) / 1e6:.0f}M"

    # Idea templates keyed by narrative theme — with data placeholders
    idea_templates: dict[str, list[dict]] = {
        "AI & Autonomous Agents": [
            {
                "title": "Multi-Agent DeFi Strategy Orchestrator",
                "description": f"A framework where specialized AI agents (risk assessor, yield optimizer, rebalancer) coordinate to manage DeFi positions across {', '.join(top_protocols[:3])}. With {tvl_str} Solana TVL and {dex_vol} daily DEX volume, autonomous portfolio management has a massive addressable market. Each agent operates independently but shares a common state via on-chain accounts.",
                "solana_stack": "Anchor programs for agent state, Jupiter CPI for swaps, Pyth for price feeds, Jito bundles for MEV-protected execution",
                "target_users": "DeFi power users, fund managers, DAOs with treasuries",
            },
        ],
        "Privacy & Confidential Transfers": [
            {
                "title": "Privacy-First Payroll & Treasury Tool",
                "description": f"Enterprise treasury management on Solana using Token-2022 confidential transfers. Companies can pay salaries, manage budgets, and settle invoices without revealing amounts on-chain. With {stable_str} in stablecoins on Solana, the payment infrastructure exists — what's missing is the privacy layer that enterprises require.",
                "solana_stack": "Token-2022 confidential transfer extension, SPL Token program, Solana Pay for merchant settlement",
                "target_users": "Companies, DAOs, payroll providers, accounting firms",
            },
        ],
        "Stablecoin & PayFi Expansion": [
            {
                "title": "Multi-Stablecoin Payment Router",
                "description": f"An intelligent payment routing layer that accepts any stablecoin ({', '.join(s['symbol'] for s in stables.get('assets', [])[:4])}) and settles in the recipient's preferred denomination. With {stable_str} stablecoin supply diversifying beyond USDC/USDT, merchants need a unified acceptance layer. Auto-routes through {top_dexes[0]} for optimal conversion.",
                "solana_stack": "Jupiter swap CPI, Solana Pay protocol, Token-2022 transfer hooks for automatic conversion",
                "target_users": "E-commerce merchants, POS systems, cross-border payment platforms",
            },
        ],
        "DePIN & Physical Infrastructure": [
            {
                "title": "DePIN Revenue Analytics & Staking Optimizer",
                "description": f"A unified dashboard and optimization engine across all Solana DePIN networks (Helium, Hivemapper, Render). Tracks node economics, reward rates, and ROI. With DePIN generating $150M+ monthly revenue, operators need data-driven tools to allocate capital across networks for maximum yield.",
                "solana_stack": "On-chain reads from Helium/Render programs, Pyth for token pricing, staking optimization via SPL Stake Pool",
                "target_users": "DePIN node operators, hardware investors, yield analysts",
            },
        ],
        "Liquid Staking & Restaking": [
            {
                "title": "LST Yield Aggregator with Auto-Routing",
                "description": f"One-click SOL staking that automatically routes to the highest-yield liquid staking token (mSOL, jitoSOL, bSOL) via Sanctum, then deploys the LST into the best-performing lending/LP position across {', '.join(top_protocols[:3])}. Rebalances weekly based on yield changes.",
                "solana_stack": "Sanctum router for LST swaps, CPI into lending protocols (Kamino, MarginFi), Jito stake pool",
                "target_users": "Passive SOL holders, institutional stakers",
            },
        ],
        "Real World Assets (RWA)": [
            {
                "title": "RWA Compliance Toolkit for Token-2022",
                "description": f"A no-code platform for issuing compliant tokenized securities on Solana using Token-2022 extensions. Includes KYC-gated transfers (transfer hooks), dividend distribution, and regulatory reporting. With {tvl_str} DeFi TVL proving Solana's financial infrastructure, RWA issuance is the next frontier.",
                "solana_stack": "Token-2022: transfer hooks for KYC gates, permanent delegate for freeze authority, metadata extension for asset details",
                "target_users": "Asset managers, real estate tokenizers, fund administrators",
            },
        ],
        "ZK Compression & Scalability": [
            {
                "title": "Compressed Token Airdrop & Distribution Platform",
                "description": "Mass token distribution at 1/1000th the cost using ZK Compression. Enables airdrops to millions of wallets, loyalty reward programs, and community token distributions that were previously cost-prohibitive. A single compressed airdrop to 1M wallets costs ~$50 vs ~$50,000 with regular accounts.",
                "solana_stack": "Light Protocol ZK Compression, compressed token accounts, concurrent Merkle trees",
                "target_users": "Token projects launching airdrops, loyalty programs, marketing campaigns",
            },
        ],
        "Infrastructure & Validators": [
            {
                "title": "Firedancer Migration Health Monitor",
                "description": "A real-time dashboard tracking Firedancer adoption across the validator set — stake distribution, block production quality, skip rates, and latency improvements. With Firedancer crossing 20% stake and Alpenglow promising 150ms finality, validators and delegators need visibility into the transition's impact on network performance.",
                "solana_stack": "Solana RPC for validator metrics, gossip protocol monitoring, epoch-level performance tracking",
                "target_users": "Validators, stake delegators, infrastructure teams",
            },
        ],
        "Perpetuals & Derivatives": [
            {
                "title": "On-Chain Derivatives Analytics Terminal",
                "description": f"A Bloomberg-style terminal for Solana perpetuals and options. Aggregates data from Drift, Zeta, Phoenix — showing funding rates, open interest, liquidation levels, and basis trades. With {dex_vol} daily DEX volume driving demand for sophisticated trading tools, there's a gap for on-chain derivatives intelligence.",
                "solana_stack": "Read Drift/Zeta program accounts, Pyth for mark prices, Clockwork for scheduled data snapshots",
                "target_users": "Professional traders, market makers, hedge funds",
            },
        ],
    }

    ideas = []
    used_templates = set()

    # First pass: match top narratives to templates
    for narrative in narratives:
        if len(ideas) >= 5:
            break
        name = narrative["name"]

        # Exact match
        matched_key = None
        for template_key in idea_templates:
            if template_key == name:
                matched_key = template_key
                break

        # Fuzzy match on keywords
        if not matched_key:
            name_lower = name.lower()
            for template_key in idea_templates:
                key_words = [w for w in template_key.lower().split() if len(w) > 3]
                if any(w in name_lower for w in key_words):
                    matched_key = template_key
                    break

        if matched_key and matched_key not in used_templates:
            used_templates.add(matched_key)
            for template in idea_templates[matched_key]:
                ideas.append({
                    **template,
                    "tied_narrative": name,
                    "narrative_score": narrative.get("score", 0),
                    "signal_count": narrative.get("signal_count", 0),
                })

    # Second pass: fill remaining slots from unused templates (ordered by template importance)
    if len(ideas) < 5:
        priority_order = [
            "AI & Autonomous Agents", "Privacy & Confidential Transfers",
            "Stablecoin & PayFi Expansion", "DePIN & Physical Infrastructure",
            "Liquid Staking & Restaking", "Real World Assets (RWA)",
            "ZK Compression & Scalability", "Infrastructure & Validators",
            "Perpetuals & Derivatives",
        ]
        for key in priority_order:
            if key not in used_templates and key in idea_templates:
                used_templates.add(key)
                for template in idea_templates[key]:
                    # Find the matching narrative if it exists
                    tied = next((n for n in narratives if n["name"] == key), None)
                    ideas.append({
                        **template,
                        "tied_narrative": key,
                        "narrative_score": tied["score"] if tied else 0,
                        "signal_count": tied["signal_count"] if tied else 0,
                    })
                if len(ideas) >= 5:
                    break

    return ideas[:5]

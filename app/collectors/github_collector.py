"""Collect development activity signals from Solana ecosystem GitHub repos."""

import httpx
from datetime import datetime, timedelta, timezone
from typing import Any

SOLANA_ECOSYSTEM_REPOS = [
    "solana-labs/solana",
    "solana-labs/solana-program-library",
    "anza-xyz/agave",
    "jito-foundation/jito-solana",
    "coral-xyz/anchor",
    "metaplex-foundation/metaplex-program-library",
    "marinade-finance/liquid-staking-program",
    "project-serum/serum-dex",
    "raydium-io/raydium-amm",
    "orca-so/whirlpools",
    "drift-labs/protocol-v2",
    "marginfi-v2/marginfi-v2",
    "kamino-finance/klend",
    "helium/helium-program-library",
    "pyth-network/pyth-sdk-solana",
    "tensor-foundation/marketplace",
    "jupiter-project/jupiter-core",
    "sanctum-so/sanctum-solana-cli",
    "squads-protocol/v4",
    "streamflow-finance/js-sdk",
    "switchboard-xyz/solana-sdk",
    "clockwork-xyz/clockwork",
    "phantom/phantom-wallet",
    "backpack-exchange/backpack",
    "wormhole-foundation/wormhole",
    "LayerZero-Labs/solana-vault",
    "ellipsis-labs/phoenix-v1",
    "access-protocol/access-protocol",
    "MagicBlockLabs/ephemeral-rollups",
    "solana-mobile/solana-mobile-stack",
    "tiplink/tiplink-open-source",
    "dialectlabs/actions",
    "helius-labs/atlas-txn-sender",
    "firedancer-io/firedancer",
]

# Trending topic repos to detect new narratives
NARRATIVE_SEARCH_QUERIES = [
    "solana AI agent",
    "solana depin",
    "solana restaking",
    "solana RWA",
    "solana payfi",
    "solana blinks",
    "solana compressed nft",
    "solana token extensions",
    "solana mev",
    "solana intents",
    "solana zk compression",
    "solana confidential transfers",
    "solana stablecoin",
    "solana perps dex",
    "solana liquid staking",
    "solana mobile dapp",
]


async def fetch_repo_activity(client: httpx.AsyncClient, repo: str, since_days: int = 14) -> dict[str, Any] | None:
    """Fetch recent activity for a single repo."""
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        repo_resp = await client.get(f"https://api.github.com/repos/{repo}", headers=headers)
        if repo_resp.status_code != 200:
            return None
        repo_data = repo_resp.json()

        commits_resp = await client.get(
            f"https://api.github.com/repos/{repo}/commits",
            headers=headers,
            params={"since": since, "per_page": 100},
        )
        commit_count = len(commits_resp.json()) if commits_resp.status_code == 200 else 0

        return {
            "repo": repo,
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "open_issues": repo_data.get("open_issues_count", 0),
            "recent_commits": commit_count,
            "language": repo_data.get("language"),
            "description": repo_data.get("description", ""),
            "updated_at": repo_data.get("updated_at", ""),
            "topics": repo_data.get("topics", []),
        }
    except Exception:
        return None


async def search_trending_repos(client: httpx.AsyncClient, query: str, since_days: int = 14) -> list[dict]:
    """Search GitHub for trending Solana repos matching a narrative query."""
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        resp = await client.get(
            "https://api.github.com/search/repositories",
            headers=headers,
            params={
                "q": f"{query} pushed:>{since}",
                "sort": "updated",
                "order": "desc",
                "per_page": 10,
            },
        )
        if resp.status_code != 200:
            return []

        items = resp.json().get("items", [])
        return [
            {
                "name": r["full_name"],
                "stars": r["stargazers_count"],
                "forks": r["forks_count"],
                "description": r.get("description", ""),
                "language": r.get("language"),
                "created_at": r.get("created_at", ""),
                "updated_at": r.get("updated_at", ""),
                "topics": r.get("topics", []),
            }
            for r in items
        ]
    except Exception:
        return []


async def collect_github_signals(github_token: str | None = None) -> dict[str, Any]:
    """Main collection function — gathers all GitHub signals."""
    headers = {}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        # Collect core repo activity
        import asyncio
        repo_tasks = [fetch_repo_activity(client, repo) for repo in SOLANA_ECOSYSTEM_REPOS]
        repo_results = await asyncio.gather(*repo_tasks, return_exceptions=True)
        repos = [r for r in repo_results if isinstance(r, dict)]

        # Search for narrative-specific repos
        search_tasks = [search_trending_repos(client, q) for q in NARRATIVE_SEARCH_QUERIES]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        narrative_repos: dict[str, list] = {}
        for query, result in zip(NARRATIVE_SEARCH_QUERIES, search_results):
            if isinstance(result, list):
                narrative_repos[query] = result

    # Compute signals
    most_active = sorted(repos, key=lambda r: r["recent_commits"], reverse=True)[:10]
    most_starred = sorted(repos, key=lambda r: r["stars"], reverse=True)[:10]

    # Detect narrative strength by repo count and activity
    narrative_strength: dict[str, dict] = {}
    for query, found_repos in narrative_repos.items():
        narrative_strength[query] = {
            "repo_count": len(found_repos),
            "total_stars": sum(r["stars"] for r in found_repos),
            "new_repos": sum(1 for r in found_repos if r.get("created_at", "")[:7] == datetime.now(timezone.utc).strftime("%Y-%m")),
            "top_repos": found_repos[:3],
        }

    return {
        "collection_time": datetime.now(timezone.utc).isoformat(),
        "period_days": 14,
        "core_repos": repos,
        "most_active_repos": most_active,
        "most_starred_repos": most_starred,
        "narrative_repos": narrative_strength,
    }

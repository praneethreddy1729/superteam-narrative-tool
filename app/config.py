"""Configuration and constants."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")

# Analysis period
LOOKBACK_DAYS = 14

# Cache TTL
CACHE_TTL_SECONDS = 3600  # 1 hour — data sources update hourly at most

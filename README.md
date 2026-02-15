# Solana Narrative Detector

An AI-powered tool that detects emerging narratives and generates actionable build ideas for the Solana ecosystem. Data is refreshed fortnightly.

## What It Does

The tool monitors multiple data sources across the Solana ecosystem to identify accelerating trends before they become obvious. It outputs:

- **Ranked narratives** with strength scores and supporting evidence
- **3-5+ concrete build ideas** tied to specific narratives
- **Raw signal data** for independent verification

## Data Sources

### 1. GitHub Developer Activity
- Tracks **34 core Solana ecosystem repositories** (Solana Labs, Anchor, Jito, Metaplex, Drift, Orca, Jupiter, Firedancer, etc.)
- Monitors commit frequency, star growth, fork activity, and issue counts over rolling 14-day windows
- Searches for **16 narrative-specific queries** (AI agents, DePIN, restaking, RWA, PayFi, ZK compression, MEV, etc.) to detect new repo creation and activity spikes

### 2. On-Chain Data (Solana RPC + DeFiLlama)
- **Network performance**: TPS, epoch info, SOL supply
- **DeFi TVL**: Total and per-protocol TVL with 14-day trend analysis
- **Protocol category analysis**: Identifies fastest-growing DeFi categories (lending, DEX, liquid staking, etc.)
- **Stablecoin supply**: Tracks USDC, USDT, PYUSD, and other stablecoins on Solana
- **Yield opportunities**: Top pools by TVL and APY

### 3. Social & Market Signals
- **DEX volume rankings**: 24h and 7d trading volumes across all Solana DEXes
- **NFT market activity**: Volume trends and marketplace rankings
- **Ecosystem project registry**: Tracks new project additions
- **Solana blog/news**: RSS feed monitoring
- **KOL focus tracking**: Maps key opinion leaders (Toly, Mert, Akshay, Chase Barker, etc.) and their areas of focus

## How Signals Are Detected and Ranked

### Signal Detection
Each data source produces typed signals with:
- **Source label** (github, onchain, defi, market)
- **Signal description** (what was detected)
- **Strength score** (quantitative measure of the signal's magnitude)
- **Evidence** (human-readable explanation with data points)

### Narrative Synthesis
Signals are grouped into **10 meta-narrative categories** using keyword matching:
1. AI Agents & Autonomous Systems
2. DePIN & Physical Infrastructure
3. Restaking & Validator Economics
4. Real World Assets (RWA) & Tokenization
5. PayFi & Stablecoin Payments
6. ZK Compression & Scalability
7. MEV & Trading Infrastructure
8. Token Extensions & Programmable Assets
9. DeFi TVL & Yield Growth
10. Consumer Apps & Blinks

### Scoring Formula
```
composite_score = sum(signal_strengths) × (1 + 0.3 × source_diversity)
```
Narratives with signals from multiple source types (github + onchain + market) score higher, rewarding cross-domain corroboration.

### Build Idea Generation
The top-ranked narratives are mapped to concrete product ideas. Each idea includes:
- Description and target users
- Specific Solana integration points (programs, protocols, standards)
- Complexity estimate

## Architecture

```
┌────────────────────────────────────────────┐
│              FastAPI Application            │
├────────────────┬──────────┬────────────────┤
│ GitHub         │ On-Chain │ Social/Market   │
│ Collector      │ Collector│ Collector       │
│ (GitHub API)   │ (RPC +   │ (DeFiLlama DEX │
│                │ DeFiLlama│  + NFT + News)  │
├────────────────┴──────────┴────────────────┤
│              Signal Analyzer               │
│  (per-source narrative extraction)         │
├────────────────────────────────────────────┤
│           Narrative Synthesizer            │
│  (cross-source ranking + scoring)          │
├────────────────────────────────────────────┤
│          Build Idea Generator              │
│  (narrative → product idea mapping)        │
├────────────────────────────────────────────┤
│    Dashboard (Jinja2 HTML) + JSON APIs     │
└────────────────────────────────────────────┘
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Interactive HTML dashboard |
| `GET /api/narratives` | JSON: ranked narratives + build ideas |
| `GET /api/signals` | JSON: raw signal data from all sources |
| `GET /api/refresh` | Force data refresh (bypasses 15-min cache) |
| `GET /health` | Health check |

## Running Locally

```bash
# Clone and setup
git clone https://github.com/YOUR_USER/solana-narrative-detector.git
cd solana-narrative-detector
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional: set GitHub token for higher API rate limits
export GITHUB_TOKEN=ghp_your_token_here

# Run
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000` for the dashboard.

## Deployment

### Render (recommended)
1. Connect your GitHub repo to Render
2. Use the included `render.yaml` for auto-configuration
3. Optionally set `GITHUB_TOKEN` env var

### Docker
```bash
docker build -t solana-narrative-detector .
docker run -p 8000:8000 solana-narrative-detector
```

## Tech Stack

- **Python 3.12** + **FastAPI**
- **httpx** for async HTTP
- **Jinja2** for dashboard templating
- Data: GitHub API, Solana RPC, DeFiLlama API

## License

MIT

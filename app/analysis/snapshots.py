"""Temporal snapshot storage — enables "what changed" analysis.

Stores each analysis run as a JSON file. On subsequent runs, compares
current narratives to the most recent snapshot to detect:
- New narratives (weren't in previous run)
- Rising narratives (score increased)
- Fading narratives (score decreased)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

log = logging.getLogger(__name__)
SNAPSHOT_DIR = DATA_DIR / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def save_snapshot(narratives: list[dict], ideas: list[dict]) -> str:
    """Save current analysis as a timestamped snapshot."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "narratives": [
            {"name": n["name"], "score": n.get("score", 0), "signal_count": n.get("signal_count", 0),
             "sources": n.get("sources", []), "discovered": n.get("discovered", False)}
            for n in narratives
        ],
        "idea_count": len(ideas),
    }
    path = SNAPSHOT_DIR / f"snapshot_{ts}.json"
    path.write_text(json.dumps(snapshot, indent=2))
    log.info(f"Saved snapshot: {path.name}")
    return str(path)


def load_previous_snapshot() -> dict | None:
    """Load the most recent snapshot for comparison."""
    snapshots = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    if len(snapshots) < 2:
        return None
    # Return second-to-last (the last one is the current run)
    try:
        return json.loads(snapshots[-2].read_text())
    except Exception:
        return None


def compute_deltas(current: list[dict], previous: dict | None) -> list[dict]:
    """Compare current narratives to previous snapshot."""
    if not previous:
        return [{"name": n["name"], "delta": "new", "score_change": 0} for n in current]

    prev_scores = {n["name"]: n.get("score", 0) for n in previous.get("narratives", [])}
    prev_names = set(prev_scores.keys())

    deltas = []
    for n in current:
        name = n["name"]
        curr_score = n.get("score", 0)
        if name not in prev_names:
            deltas.append({"name": name, "delta": "new", "score_change": curr_score})
        else:
            change = curr_score - prev_scores[name]
            if change > 5:
                delta_label = "rising"
            elif change < -5:
                delta_label = "fading"
            else:
                delta_label = "stable"
            deltas.append({"name": name, "delta": delta_label, "score_change": round(change, 1)})

    return deltas

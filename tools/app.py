"""
FastAPI app for the Sugarbush Trail Analyzer.
Run with: uv run python tools/run.py
"""

from collections import Counter

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path

from tools.fetch_trails import fetch_trails
from tools.fetch_elevations import add_elevations_to_trails
from tools.score_trails import score_trails, WEIGHTS

app = FastAPI(title="Sugarbush Trail Analyzer")

# Cache results in memory — cleared on server restart
_cached_response = None


def analyze_trails():
    print("Fetching trails from OpenStreetMap...")
    trails = fetch_trails()
    print(f"Found {len(trails)} named, classified trails.")
    print("Fetching elevation data...")
    trails_with_elevations = add_elevations_to_trails(trails)
    print("Scoring trails...")
    scored = score_trails(trails_with_elevations)

    # Compute official rating distribution as fractions (used by client for
    # percentile-based computed classification thresholds)
    counts = Counter(t["official"] for t in scored)
    total = len(scored)
    official_distribution = {k: round(v / total, 4) for k, v in counts.items()}

    return {
        "trails": scored,
        "official_distribution": official_distribution,
        "default_weights": WEIGHTS,
    }


@app.get("/api/trails")
def get_trails():
    global _cached_response
    if _cached_response is None:
        _cached_response = analyze_trails()
    return _cached_response


@app.get("/", response_class=HTMLResponse)
def index():
    template_path = Path(__file__).parent / "templates" / "index.html"
    return template_path.read_text()

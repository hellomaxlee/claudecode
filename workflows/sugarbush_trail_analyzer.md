# Sugarbush Trail Analyzer — Strategy Plan

## Goal
Quantitatively assess the steepness of every ski trail at Sugarbush Resort using
topographic data. Compare computed difficulty to official Sugarbush trail ratings
to determine where the resort over- or underestimates difficulty.

## Output
A FastAPI-served website listing all Sugarbush trails with:
- Trail name
- Official color classification (green / blue / black / double black)
- Vertical drop (ft)
- Average slope angle (degrees)
- Max slope angle (degrees)
- Weighted composite difficulty score (0–1)
- Computed color classification
- Verdict: accurate / overestimated / underestimated

---

## Data Sources

### Trail Geometry + Official Classification
- **Source:** OpenStreetMap via Overpass API
- **Query:** `way["piste:type"="downhill"]` within Sugarbush bounding box
  - Bbox covers both Lincoln Peak and Mt. Ellen: `44.12, -72.95, 44.25, -72.84`
- **OSM difficulty tags → color mapping:**
  | OSM tag           | Color         |
  |-------------------|---------------|
  | novice            | Green         |
  | easy              | Green         |
  | intermediate      | Blue          |
  | advanced          | Black         |
  | expert            | Double Black  |

### Elevation Data
- **Source:** OpenTopoData API (`https://api.opentopodata.org/v1/srtm30m`)
- Free, no API key required, max 100 locations per request
- Points sampled every ~20m along each trail's node geometry

---

## Computed Metrics

### 1. Vertical Drop
`max(elevation) - min(elevation)` along the trail (feet)

### 2. Average Slope Angle
Mean of `arctan(Δelevation / Δdistance)` between consecutive sampled points (degrees)

### 3. Max Slope Angle
Maximum of the above values across all consecutive point pairs (degrees)

---

## Difficulty Scoring

### Normalization
Each metric is min-max normalized across all trails to a 0–1 scale.

### Weighted Composite Score
```
score = 0.15 * norm(vertical_drop)
      + 0.35 * norm(avg_slope)
      + 0.50 * norm(max_slope)
```
Weights are derived from NSAA official rating guidelines:
- **Max slope (50%):** Primary factor per NSAA — trails are rated by their steepest section
- **Avg slope (35%):** Secondary — sustained difficulty across the full run
- **Vertical drop (15%):** Not a direct NSAA rating factor; contributes to fatigue but not steepness-based classification

### Computed Classification Thresholds
| Score Range | Computed Color  |
|-------------|-----------------|
| 0.00 – 0.25 | Green           |
| 0.25 – 0.50 | Blue            |
| 0.50 – 0.75 | Black           |
| 0.75 – 1.00 | Double Black    |

### Verdict Logic
- Official == Computed → Accurate
- Official harder than Computed → Overestimated (trail is easier than rated)
- Official easier than Computed → Underestimated (trail is harder than rated)

---

## Architecture

```
tools/
  sugarbush_trail_analyzer.py   # data pipeline: fetch, process, score
  app.py                        # FastAPI server
  templates/
    index.html                  # frontend website
```

### Pipeline Steps (sugarbush_trail_analyzer.py)
1. Query Overpass API for Sugarbush downhill piste ways
2. For each trail, collect node coordinates
3. Sample points every ~20m using linear interpolation if needed
4. Batch-fetch elevations from OpenTopoData (100 pts/request)
5. Compute vertical drop, avg slope, max slope per trail
6. Normalize metrics, compute weighted composite score
7. Assign computed classification and verdict
8. Return structured list of trail result objects

### FastAPI App (app.py)
- `GET /` → serves index.html
- `GET /api/trails` → returns JSON of all trail results
- Run: `uv run uvicorn tools.app:app --reload`

### Frontend (index.html)
- Fetches `/api/trails` on load
- Sortable table by any column
- Color-coded rows by official classification
- Verdict column highlights over/underestimated trails

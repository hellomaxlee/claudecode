"""
Sugarbush Trail Analyzer
Fetches trail geometry + official difficulty from OpenStreetMap,
then fetches elevation data to compute steepness metrics and compare
against official classifications.
"""

import math
import time
import requests
import numpy as np

# Sugarbush Resort bounding box covering both Lincoln Peak and Mt. Ellen
# (lat_min, lon_min, lat_max, lon_max)
SUGARBUSH_BBOX = (44.12, -72.95, 44.25, -72.84)

# OSM difficulty tag -> display color
OSM_DIFFICULTY_MAP = {
    "novice": "Green",
    "easy": "Green",
    "intermediate": "Blue",
    "advanced": "Black",
    "expert": "Double Black",
}

# Difficulty ordering for comparison
DIFFICULTY_ORDER = ["Green", "Blue", "Black", "Double Black"]


def fetch_osm_trails():
    """Query Overpass API for all downhill piste ways at Sugarbush."""
    bbox = f"{SUGARBUSH_BBOX[0]},{SUGARBUSH_BBOX[1]},{SUGARBUSH_BBOX[2]},{SUGARBUSH_BBOX[3]}"
    query = f"""
    [out:json];
    (
      way["piste:type"="downhill"]({bbox});
    );
    out geom;
    """
    response = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        timeout=30
    )
    response.raise_for_status()
    return response.json()["elements"]


def haversine_distance(lat1, lon1, lat2, lon2):
    """Haversine distance in meters between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def sample_trail_points(geometry, max_spacing_m=20):
    """
    Return a list of (lat, lon) points sampled every ~max_spacing_m meters
    along the trail geometry (list of {lat, lon} OSM nodes).
    """
    if len(geometry) < 2:
        return [(geometry[0]["lat"], geometry[0]["lon"])]

    sampled = [(geometry[0]["lat"], geometry[0]["lon"])]
    accumulated = 0.0

    for i in range(1, len(geometry)):
        lat1, lon1 = geometry[i - 1]["lat"], geometry[i - 1]["lon"]
        lat2, lon2 = geometry[i]["lat"], geometry[i]["lon"]
        seg_len = haversine_distance(lat1, lon1, lat2, lon2)

        if seg_len == 0:
            continue

        # How far along this segment before we need to drop a sample point
        remaining = max_spacing_m - accumulated
        dist_along = 0.0

        while dist_along + remaining <= seg_len:
            dist_along += remaining
            t = dist_along / seg_len
            sampled.append((lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)))
            accumulated = 0.0
            remaining = max_spacing_m

        accumulated += seg_len - dist_along

    # Always include the final node
    last = geometry[-1]
    sampled.append((last["lat"], last["lon"]))
    return sampled


def fetch_elevations_batch(points):
    """
    Fetch elevations from OpenTopoData SRTM30m for a list of (lat, lon) tuples.
    Sends requests in batches of 100. Returns list of elevations in meters.
    """
    elevations = []
    batch_size = 100

    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        locations = "|".join(f"{lat},{lon}" for lat, lon in batch)
        response = requests.get(
            f"https://api.opentopodata.org/v1/srtm30m?locations={locations}",
            timeout=30
        )
        response.raise_for_status()
        results = response.json()["results"]
        elevations.extend(r["elevation"] for r in results)
        # Respect rate limit: 1 request per second on free tier
        if i + batch_size < len(points):
            time.sleep(1)

    return elevations


def compute_metrics(points, elevations):
    """
    Compute vertical drop, average slope angle, and max slope angle for a trail.
    Returns dict with values in feet and degrees.
    """
    elev_m = [e for e in elevations if e is not None]
    if not elev_m:
        return None

    vertical_drop_m = max(elev_m) - min(elev_m)
    vertical_drop_ft = vertical_drop_m * 3.28084

    slopes = []
    for i in range(1, len(points)):
        if elevations[i] is None or elevations[i - 1] is None:
            continue
        horiz_dist = haversine_distance(points[i - 1][0], points[i - 1][1],
                                        points[i][0], points[i][1])
        vert_diff = abs(elevations[i] - elevations[i - 1])
        if horiz_dist > 0:
            angle = math.degrees(math.atan(vert_diff / horiz_dist))
            slopes.append(angle)

    avg_slope = float(np.mean(slopes)) if slopes else 0.0
    max_slope = float(np.max(slopes)) if slopes else 0.0

    return {
        "vertical_drop_ft": round(vertical_drop_ft, 1),
        "avg_slope_deg": round(avg_slope, 2),
        "max_slope_deg": round(max_slope, 2),
    }


def classify_score(score):
    """Map a 0–1 composite score to a difficulty color."""
    if score < 0.25:
        return "Green"
    if score < 0.50:
        return "Blue"
    if score < 0.75:
        return "Black"
    return "Double Black"


def verdict(official, computed):
    """Compare official vs computed difficulty."""
    if official not in DIFFICULTY_ORDER or computed not in DIFFICULTY_ORDER:
        return "Unknown"
    o_idx = DIFFICULTY_ORDER.index(official)
    c_idx = DIFFICULTY_ORDER.index(computed)
    if o_idx == c_idx:
        return "Accurate"
    if o_idx > c_idx:
        return "Overestimated"
    return "Underestimated"


def analyze_trails():
    """
    Full pipeline: fetch OSM trails, fetch elevations, compute metrics,
    normalize, score, and return structured results.
    """
    print("Fetching trail data from OpenStreetMap...")
    osm_elements = fetch_osm_trails()

    trails_raw = []
    for el in osm_elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("piste:name")
        difficulty_tag = tags.get("piste:difficulty", "")
        official_color = OSM_DIFFICULTY_MAP.get(difficulty_tag)
        geometry = el.get("geometry", [])

        # Skip unnamed or unclassified trails or those with no geometry
        if not name or not official_color or len(geometry) < 2:
            continue

        trails_raw.append({
            "name": name,
            "official": official_color,
            "geometry": geometry,
        })

    print(f"Found {len(trails_raw)} named, classified trails.")

    # Sample points and fetch elevations
    all_results = []
    for i, trail in enumerate(trails_raw):
        print(f"Processing trail {i + 1}/{len(trails_raw)}: {trail['name']}")
        points = sample_trail_points(trail["geometry"])

        try:
            elevations = fetch_elevations_batch(points)
        except Exception as e:
            print(f"  Elevation fetch failed: {e} — skipping")
            continue

        metrics = compute_metrics(points, elevations)
        if not metrics:
            print(f"  No valid elevation data — skipping")
            continue

        all_results.append({
            "name": trail["name"],
            "official": trail["official"],
            **metrics,
        })

    if not all_results:
        return []

    # Normalize metrics for composite scoring
    vd = np.array([r["vertical_drop_ft"] for r in all_results])
    ag = np.array([r["avg_slope_deg"] for r in all_results])
    ms = np.array([r["max_slope_deg"] for r in all_results])

    def norm(arr):
        rng = arr.max() - arr.min()
        return (arr - arr.min()) / rng if rng > 0 else np.zeros_like(arr)

    vd_n, ag_n, ms_n = norm(vd), norm(ag), norm(ms)
    # Weights based on NSAA guidelines: ratings are primarily driven by the
    # steepest section of the run, with sustained average slope secondary.
    # Vertical drop is not a direct NSAA rating factor — it contributes to
    # stamina/fatigue but not steepness-based difficulty classification.
    composite = 0.15 * vd_n + 0.35 * ag_n + 0.50 * ms_n

    for i, result in enumerate(all_results):
        score = float(composite[i])
        computed_color = classify_score(score)
        result["composite_score"] = round(score, 3)
        result["computed"] = computed_color
        result["verdict"] = verdict(result["official"], computed_color)

    # Sort by composite score descending (steepest first)
    all_results.sort(key=lambda r: r["composite_score"], reverse=True)
    return all_results

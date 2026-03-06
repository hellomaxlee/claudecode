"""
Fetch SRTM elevation data for trail geometries using the OpenTopoData API.
Samples points every ~50m along each trail and returns elevations in meters.

Rate limit: OpenTopoData free tier allows 1 request/second.
We sleep 1.1s after EVERY batch (not just between batches within a trail)
and retry up to 3 times with exponential backoff on 429 errors.
"""

import math
import time
import requests


def haversine_distance(lat1, lon1, lat2, lon2):
    """Return distance in meters between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def sample_points(geometry, spacing_m=50):
    """
    Sample (lat, lon) points every ~spacing_m meters along a trail geometry.
    Uses linear interpolation between OSM nodes. Always includes start and end.
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

        remaining = spacing_m - accumulated
        dist_along = 0.0

        while dist_along + remaining <= seg_len:
            dist_along += remaining
            t = dist_along / seg_len
            sampled.append((lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)))
            accumulated = 0.0
            remaining = spacing_m

        accumulated += seg_len - dist_along

    last = geometry[-1]
    sampled.append((last["lat"], last["lon"]))
    return sampled


def fetch_elevations(points):
    """
    Fetch SRTM30m elevations for a list of (lat, lon) points from OpenTopoData.
    Sends batches of 100. Sleeps 1.1s after every batch to respect the 1 req/sec
    rate limit — including after the last batch, so the next trail doesn't fire
    immediately. Retries up to 3 times with exponential backoff on 429 errors.
    Returns a list of elevation values in meters (None where unavailable).
    """
    elevations = []
    batch_size = 100

    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        locations = "|".join(f"{lat},{lon}" for lat, lon in batch)

        for attempt in range(3):
            response = requests.get(
                f"https://api.opentopodata.org/v1/srtm30m?locations={locations}",
                timeout=30
            )
            if response.status_code == 429:
                wait = 2 ** attempt * 2  # 2s, 4s, 8s
                print(f"    Rate limited (429), retrying in {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            break

        elevations.extend(r["elevation"] for r in response.json()["results"])
        # Always sleep after every batch to maintain 1 req/sec across all trails
        time.sleep(1.1)

    return elevations


def add_elevations_to_trails(trails):
    """
    Sample points along each trail's geometry and fetch their elevations.
    Returns input trails with 'points' and 'elevations' fields added.
    Trails that fail elevation fetching are skipped with a warning.
    """
    result = []
    for i, trail in enumerate(trails):
        print(f"  Fetching elevations {i + 1}/{len(trails)}: {trail['name']}")
        points = sample_points(trail["geometry"])
        try:
            elevations = fetch_elevations(points)
        except Exception as e:
            print(f"    Failed: {e} — skipping")
            continue
        result.append({**trail, "points": points, "elevations": elevations})
    return result

# fetch_elevations — Strategy Plan

## Goal
Given trail geometries, sample points at regular intervals along each trail and
fetch SRTM elevation data from OpenTopoData for those points.

## Data Source
- **API:** OpenTopoData SRTM30m (`https://api.opentopodata.org/v1/srtm30m`)
- Free, no API key required
- Max 100 locations per request
- Rate limit: 1 request/second on free tier

## Sampling Strategy
- Sample one point every **50 meters** along each trail using linear interpolation
  between OSM geometry nodes (coarser than 20m to reduce API call count)
- Use haversine distance to measure segment lengths accurately
- Always include the first and last nodes of the trail

## Batching & Rate Limiting
- Group sampled points into batches of 100
- Sleep **1.1 seconds after every batch** — including after the last batch of
  each trail, so the next trail's first batch is never fired immediately
- This ensures we stay under the 1 req/sec rate limit across all trails
- On 429 (Too Many Requests): retry up to 3 times with exponential backoff
  (2s, 4s, 8s delays)

## Output
Returns input trails with two fields added:
```python
{
    ...trail fields...,
    "points": [(lat, lon), ...],      # sampled trail points
    "elevations": [float | None, ...] # elevation in meters per point
}
```

## Error Handling
- On HTTP failure for a trail: log a warning and skip that trail
- `None` elevation values are handled downstream in score_trails

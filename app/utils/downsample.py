"""
Downsampling utilities for chart responsiveness.

We use a simple bucketed min/max downsample for time series, which preserves
extremes better than naive decimation while remaining cheap.
"""

from __future__ import annotations

from typing import Any, Dict, List


def downsample_minmax(points: List[Dict[str, Any]], *, x_key: str, y_key: str, max_points: int) -> List[Dict[str, Any]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    if max_points < 3:
        return [points[0], points[-1]]

    n = len(points)
    bucket_count = max_points // 2
    bucket_size = max(1, n // bucket_count)

    out: List[Dict[str, Any]] = [points[0]]
    for i in range(0, n, bucket_size):
        bucket = points[i : i + bucket_size]
        if not bucket:
            continue
        min_p = min(bucket, key=lambda p: float(p.get(y_key, 0) or 0))
        max_p = max(bucket, key=lambda p: float(p.get(y_key, 0) or 0))
        if min_p is max_p:
            out.append(min_p)
        else:
            # preserve temporal order inside bucket
            if bucket.index(min_p) < bucket.index(max_p):
                out.extend([min_p, max_p])
            else:
                out.extend([max_p, min_p])
        if len(out) >= max_points - 1:
            break

    out.append(points[-1])
    # de-dup by x while keeping order
    seen = set()
    dedup: List[Dict[str, Any]] = []
    for p in out:
        x = p.get(x_key)
        if x in seen:
            continue
        seen.add(x)
        dedup.append(p)
    return dedup[:max_points]


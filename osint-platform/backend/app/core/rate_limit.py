"""Per-IP rate limiting + per-host crawl throttling."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class IPRateLimiter:
    """Sliding-window rate limiter (per client IP)."""

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets[key]
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True


class HostThrottle:
    """Min interval between requests to the same host (politeness)."""

    def __init__(self, min_interval: float = 1.0):
        self._min = min_interval
        self._last: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, host: str) -> None:
        async with self._lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            delta = now - last
            if delta < self._min:
                await asyncio.sleep(self._min - delta)
            self._last[host] = time.monotonic()

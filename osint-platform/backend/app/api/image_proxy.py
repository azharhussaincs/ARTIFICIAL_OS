"""Image proxy.

Why this exists: many platform CDNs (`scontent.cdninstagram.com`,
`pbs.twimg.com`, `p16-sign-va.tiktokcdn.com`, `lh3.googleusercontent.com`,
…) hot-link-protect their avatars with `Referer` / session checks, or
serve them with `Cross-Origin-Resource-Policy: same-site`. The result
is that an `<img src="https://…">` in our dashboard fails silently in
the browser even though the URL is valid.

The proxy:

  1. validates the upstream URL via `is_host_allowed` (SSRF guard)
  2. fetches it server-side with our own User-Agent (and no Referer)
  3. caches the bytes in a tiny in-memory LRU
  4. streams them back with `Cache-Control: public, max-age=3600`

Limits:
  * 4 MB per image
  * must be `Content-Type: image/*`
  * 60 requests per IP per minute
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.config import get_settings
from app.core.ethics import is_host_allowed
from app.core.logger import logger
from app.core.rate_limit import IPRateLimiter

router = APIRouter(prefix="/image", tags=["image"])

MAX_BYTES = 4_000_000              # 4 MB
CACHE_MAX_ENTRIES = 256            # bounded LRU
CACHE_TTL_SECONDS = 60 * 60        # 1 h
TIMEOUT_S = 8.0

_limiter = IPRateLimiter(max_requests=60, window_seconds=60)


class _LRU:
    """Tiny TTL-aware LRU. Threadsafe enough for asyncio (single thread)."""
    def __init__(self, max_size: int):
        self._max = max_size
        self._store: "OrderedDict[str, Tuple[float, str, bytes]]" = OrderedDict()

    def get(self, key: str) -> Optional[Tuple[str, bytes]]:
        item = self._store.get(key)
        if item is None:
            return None
        ts, ctype, data = item
        if time.time() - ts > CACHE_TTL_SECONDS:
            self._store.pop(key, None)
            return None
        # mark as recently used
        self._store.move_to_end(key)
        return ctype, data

    def put(self, key: str, ctype: str, data: bytes) -> None:
        self._store[key] = (time.time(), ctype, data)
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

_cache = _LRU(CACHE_MAX_ENTRIES)


def _client_ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else req.client.host) or "unknown"


def _key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


@router.get("")
async def proxy(request: Request, url: str = Query(..., min_length=8, max_length=2048)):
    """Fetch and stream an external image. Returns 502 on upstream failure,
    400 on disallowed host, 415 on non-image content."""
    if not await _limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    if not is_host_allowed(url):
        raise HTTPException(status_code=400, detail="host not allowed")

    cache_key = _key(url)
    cached = _cache.get(cache_key)
    if cached is not None:
        ctype, data = cached
        return Response(content=data, media_type=ctype, headers={
            "Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}, immutable",
            "X-Proxy-Cache": "HIT",
        })

    s = get_settings()
    headers = {
        "User-Agent": s.user_agent,
        "Accept": "image/*,*/*;q=0.5",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, headers=headers, follow_redirects=True) as client:
            r = await client.get(url)
    except httpx.HTTPError as e:
        logger.debug("image proxy fetch failed %s: %s", url, e)
        raise HTTPException(status_code=502, detail="upstream error")

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"upstream {r.status_code}")
    ctype = r.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=415, detail=f"non-image content-type: {ctype or 'unknown'}")
    if len(r.content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="image too large")

    _cache.put(cache_key, ctype, r.content)
    return Response(content=r.content, media_type=ctype, headers={
        "Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}, immutable",
        "X-Proxy-Cache": "MISS",
    })


def proxied(url: str) -> str:
    """Helper for Python callers (e.g. the export module): rewrite a raw
    image URL to its proxied form."""
    from urllib.parse import quote
    return f"/api/image?url={quote(url, safe='')}"

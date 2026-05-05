"""Avatar perceptual hashing + cross-platform clustering.

The same human often reuses one avatar across multiple platforms. If we
fetch the avatar URL from each confirmed profile and compute a
perceptual fingerprint, two profiles with matching fingerprints become
strong evidence that they're the same person.

Algorithm: difference-hash (dHash). Robust against minor recompression,
re-scaling, and palette changes; collisions are rare.

  1. download bytes
  2. greyscale + resize to (size+1, size) with Lanczos
  3. for each row, output 1 bit per (col vs col+1) gradient
  4. concat into a 64-bit int (size=8)

Two hashes are "the same" when Hamming distance ≤ MATCH_THRESHOLD (12).

Image fetches respect:
  - app.core.ethics.is_host_allowed (SSRF guard)
  - per-host rate limit
  - max content length (no 50 MB ad banners)
  - file-size short-circuit (skip > MAX_BYTES)

We deliberately bypass the relevance.is_noise_url filter for images
because legitimate avatar URLs live on platform CDNs (e.g.
avatars.githubusercontent.com, scontent.cdninstagram.com, lh3.googleusercontent.com)
that the noise filter must reject for *website* Findings. The two
filters are intentionally separate.
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import httpx
from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.core.ethics import is_host_allowed
from app.core.logger import logger
from app.core.rate_limit import HostThrottle

MAX_BYTES = 4_000_000      # 4 MB hard cap per image
MATCH_THRESHOLD = 12       # Hamming distance considered "same image"
HASH_SIZE = 8              # produces a 64-bit hash


# ---------------------------------------------------------------------------
# Direct-avatar URL builders
# ---------------------------------------------------------------------------
#
# Some platforms expose a deterministic avatar URL keyed by the public
# handle. We use these as a FAST PATH (no HTML scraping, no JS rendering)
# and as a FALLBACK when the profile-page fetch fails.
#
# All builders here produce URLs that are public and don't require auth.
DIRECT_AVATAR_BUILDERS = {
    "github":   lambda h: f"https://github.com/{h}.png?size=256",
    "gitlab":   lambda h: f"https://gitlab.com/{h}.png?width=256",
}


def direct_avatar_url(platform: str, handle: str) -> Optional[str]:
    """Return a deterministic avatar URL for `platform/handle` if we know
    a public pattern, otherwise None."""
    if not platform or not handle:
        return None
    builder = DIRECT_AVATAR_BUILDERS.get(platform.lower())
    return builder(handle) if builder else None


def gravatar_url(email: str, size: int = 256) -> Optional[str]:
    """Public Gravatar avatar URL for `email`. Returns None for invalid input.
    Uses the standard MD5(lowercase) hash + d=404 to ensure we get a real
    avatar (or a 404 we can detect) — never the generic 'mystery person'."""
    import hashlib
    if not email or "@" not in email:
        return None
    digest = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d=404"


# ---------------------------------------------------------------------------
# Hashing primitives
# ---------------------------------------------------------------------------

def dhash(image_bytes: bytes, size: int = HASH_SIZE) -> Optional[int]:
    """Difference-hash: output is a `size*size`-bit integer, or None on
    decode failure."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except (UnidentifiedImageError, OSError) as e:
        logger.debug("dhash decode failed: %s", e)
        return None
    try:
        img = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    except Exception as e:  # noqa: BLE001
        logger.debug("dhash resize failed: %s", e)
        return None
    pixels = list(img.getdata())
    h = 0
    for row in range(size):
        for col in range(size):
            i = row * (size + 1) + col
            h = (h << 1) | (1 if pixels[i] > pixels[i + 1] else 0)
    return h


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ---------------------------------------------------------------------------
# Async fetcher
# ---------------------------------------------------------------------------

@dataclass
class AvatarHash:
    url: str
    hash: int
    bytes_len: int = 0


class AvatarFingerprinter:
    """Fetches avatar URLs concurrently and returns hashes for the ones
    we could decode."""

    def __init__(self):
        s = get_settings()
        self.ua = s.user_agent
        self.timeout = s.request_timeout
        self.throttle = HostThrottle(min_interval=0.4)

    async def hash_many(self, urls: Iterable[str]) -> Dict[str, AvatarHash]:
        urls = [u for u in {u.strip() for u in urls if u} if is_host_allowed(u)]
        if not urls:
            return {}
        sem = asyncio.Semaphore(6)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": self.ua, "Accept": "image/*"},
            follow_redirects=True,
        ) as client:
            async def _one(u: str) -> Optional[AvatarHash]:
                async with sem:
                    return await self._fetch_and_hash(u, client)
            results = await asyncio.gather(*[_one(u) for u in urls], return_exceptions=False)

        return {r.url: r for r in results if r is not None}

    async def _fetch_and_hash(self, url: str, client: httpx.AsyncClient) -> Optional[AvatarHash]:
        host = httpx.URL(url).host or ""
        await self.throttle.wait(host)
        try:
            r = await client.get(url)
        except httpx.HTTPError as e:
            logger.debug("avatar fetch failed %s: %s", url, e)
            return None
        if r.status_code >= 400:
            return None
        ctype = r.headers.get("content-type", "").lower()
        if not ctype.startswith("image/"):
            return None
        if len(r.content) > MAX_BYTES:
            return None
        h = dhash(r.content)
        if h is None:
            return None
        return AvatarHash(url=url, hash=h, bytes_len=len(r.content))


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

@dataclass
class ImageCluster:
    """A group of URLs whose avatars are pairwise close in Hamming distance."""
    representative_hash: int
    urls: List[str] = field(default_factory=list)
    # Per-URL closest neighbour distance (for diagnostic display)
    distances: Dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.urls)


def cluster_by_hash(
    hashes: Dict[str, AvatarHash],
    threshold: int = MATCH_THRESHOLD,
) -> List[ImageCluster]:
    """Greedy single-link clustering by Hamming distance.

    Two avatars are linked if their hashes differ by ≤ threshold bits.
    Returns ONLY clusters with ≥ 2 members (singletons are not interesting
    for cross-platform correlation)."""
    items: List[Tuple[str, int]] = [(u, h.hash) for u, h in hashes.items()]
    n = len(items)
    if n < 2:
        return []

    # Union-find
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[a] = b

    distances: Dict[Tuple[str, str], int] = {}
    for i in range(n):
        for j in range(i + 1, n):
            d = hamming(items[i][1], items[j][1])
            if d <= threshold:
                union(i, j)
                distances[(items[i][0], items[j][0])] = d

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    clusters: List[ImageCluster] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        urls = [items[k][0] for k in members]
        # Pick the lexicographically-smallest hash as representative
        rep = min(items[k][1] for k in members)
        # For each url store its smallest distance to any other in the cluster
        per_url_min: Dict[str, int] = {}
        for k in members:
            best = 64
            for kk in members:
                if k == kk: continue
                d = hamming(items[k][1], items[kk][1])
                if d < best: best = d
            per_url_min[items[k][0]] = best
        clusters.append(ImageCluster(representative_hash=rep, urls=urls, distances=per_url_min))

    # Largest clusters first
    clusters.sort(key=lambda c: -c.size)
    return clusters

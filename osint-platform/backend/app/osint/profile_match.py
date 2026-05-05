"""Profile-page fetcher.

Fetches a confirmed profile URL and returns a structured snapshot using
the per-platform fingerprint parsers (`fingerprints.py`). Every value
produced has already been filtered for noise — generic platform text,
chrome links, and CDN URLs are dropped before they leave this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.core.ethics import RobotsCache, is_host_allowed
from app.core.rate_limit import HostThrottle
from app.osint.fingerprints import _is_platform_default_image, _meta_image, parse_profile


@dataclass
class ProfileSnapshot:
    url: str
    platform: str
    handle: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    extracted_emails: List[str] = field(default_factory=list)
    extracted_links: List[str] = field(default_factory=list)
    extracted_handles: List[str] = field(default_factory=list)
    title: Optional[str] = None
    is_blocked: bool = False
    parser_confidence: float = 1.0
    error: Optional[str] = None


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")


class ProfileFetcher:
    def __init__(self):
        s = get_settings()
        self.ua = s.user_agent
        self.timeout = s.request_timeout
        self.respect_robots = s.respect_robots_txt
        self.robots = RobotsCache(self.ua, timeout=5)
        self.throttle = HostThrottle(min_interval=1.0)

    async def fetch(self, url: str, platform: str, handle: Optional[str] = None) -> ProfileSnapshot:
        snap = ProfileSnapshot(url=url, platform=platform, handle=handle)
        if not is_host_allowed(url):
            snap.error = "host blocked"
            return snap
        if self.respect_robots and not await self.robots.allowed(url):
            snap.error = "disallowed by robots.txt"
            return snap

        host = urlparse(url).hostname or ""
        await self.throttle.wait(host)

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": self.ua, "Accept": "text/html,application/xhtml+xml"},
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
        except httpx.HTTPError as e:
            snap.error = str(e)
            return snap

        ctype = r.headers.get("content-type", "").lower()
        is_html = "html" in ctype or "xml" in ctype

        # On non-200 OR non-HTML content, the page didn't render normally —
        # but the body might still be HTML (many platforms 403/429 with a
        # rendered error page that still ships og:image). Try to salvage
        # the avatar before giving up.
        if r.status_code >= 400 or not is_html:
            if is_html and r.text:
                try:
                    fallback_soup = BeautifulSoup(r.text, "lxml")
                    fallback_img = _meta_image(fallback_soup, url)
                    if fallback_img and not _is_platform_default_image(fallback_img):
                        snap.is_blocked = True
                        snap.parser_confidence = 0.3
                        snap.avatar_url = fallback_img
                        snap.title = None
                        return snap
                except Exception:  # noqa: BLE001
                    pass
            snap.error = f"non-html or {r.status_code}"
            return snap

        fp = parse_profile(r.text, url, platform)
        snap.is_blocked = fp.is_blocked
        snap.parser_confidence = fp.confidence
        snap.title = fp.display_name  # title is the user's display name, not page chrome
        snap.display_name = fp.display_name
        snap.bio = fp.bio
        snap.avatar_url = fp.avatar_url
        snap.extracted_links = fp.personal_links
        snap.extracted_handles = fp.referenced_handles

        # Inline email extraction from the bio only (NOT the full page).
        if fp.bio:
            snap.extracted_emails = sorted({m.group(0).lower() for m in _EMAIL_RE.finditer(fp.bio)})

        return snap


def name_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    aa = re.sub(r"[^a-z0-9 ]", "", a.lower()).strip()
    bb = re.sub(r"[^a-z0-9 ]", "", b.lower()).strip()
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    set_a, set_b = set(aa.split()), set(bb.split())
    jacc = len(set_a & set_b) / max(1, len(set_a | set_b))
    seq = SequenceMatcher(None, aa, bb).ratio()
    return max(jacc, seq)


def bios_share_anchor(snap_a: ProfileSnapshot, snap_b: ProfileSnapshot) -> Optional[str]:
    """Return a short reason if two profiles share a concrete identifier."""
    if not snap_a or not snap_b:
        return None
    a_emails = set(snap_a.extracted_emails)
    b_emails = set(snap_b.extracted_emails)
    if a_emails & b_emails:
        return f"both bios reference email {next(iter(a_emails & b_emails))}"
    a_links = {urlparse(u).netloc.lower() for u in snap_a.extracted_links if u}
    b_links = {urlparse(u).netloc.lower() for u in snap_b.extracted_links if u}
    common = (a_links & b_links) - {""}
    if common:
        return f"both bios link to {next(iter(common))}"
    a_h, b_h = set(snap_a.extracted_handles), set(snap_b.extracted_handles)
    if a_h & b_h:
        return f"both bios mention @{next(iter(a_h & b_h))}"
    sim = name_similarity(snap_a.display_name, snap_b.display_name)
    if sim >= 0.85:
        return f"display names match ({snap_a.display_name!r} ≈ {snap_b.display_name!r})"
    return None

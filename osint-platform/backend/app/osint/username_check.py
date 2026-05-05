"""Username correlation across public profile sites.

For each known site, we issue a single HEAD/GET to the profile URL and
treat 200 (with a content signal) as a probable match. We never log in
or solve captchas — false positives are possible and each result carries
a confidence score that the analyst can weigh.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import List, Optional

import httpx

from app.config import get_settings
from app.core.ethics import is_host_allowed
from app.core.logger import logger

# Each entry: (platform, profile-url-template, "not-found" signal regex or None)
#
# Confidence calibration:
#   - Sites with a reliable text signal for "not found" → high confidence.
#   - Sites that soft-404 (return 200 for any handle) → we mark them as
#     PROFILE_HIT_REDIRECT-equivalent by leaving the negative pattern very
#     specific so most checks fall back to the lower confidence band.
#   - WhatsApp is intentionally NOT here. WhatsApp has no public profile
#     surface — handles are phone numbers and the "wa.me/<phone>" link
#     unconditionally returns a generic page regardless of whether the
#     number is registered. Probing it would only generate noise.
SITES = [
    ("github",       "https://github.com/{u}",                 r"Not Found|404"),
    ("gitlab",       "https://gitlab.com/{u}",                 r"Page Not Found|404"),
    ("twitter",      "https://x.com/{u}",                      None),
    ("reddit",       "https://www.reddit.com/user/{u}/about.json", r'"error"\s*:\s*404'),
    ("medium",       "https://medium.com/@{u}",                r"PAGE NOT FOUND|404"),
    ("dev.to",       "https://dev.to/{u}",                     r"page not found|404"),
    ("stackoverflow","https://stackoverflow.com/users/{u}",    r"User not found|Page Not Found"),
    ("youtube",      "https://www.youtube.com/@{u}",           r"This page isn[’']t available|404"),
    ("tiktok",       "https://www.tiktok.com/@{u}",            r"Couldn't find this account"),
    ("instagram",    "https://www.instagram.com/{u}/",         r"Sorry, this page isn"),
    ("pinterest",    "https://www.pinterest.com/{u}/",         r"Page not found|404"),
    ("vimeo",        "https://vimeo.com/{u}",                  r"Page not found|404"),
    ("about.me",     "https://about.me/{u}",                   r"Page not found"),
    ("keybase",      "https://keybase.io/{u}",                 r"User not found"),
    ("hackerone",    "https://hackerone.com/{u}",              r"Page not found"),
    ("npmjs",        "https://www.npmjs.com/~{u}",             r"404"),
    ("dockerhub",    "https://hub.docker.com/u/{u}",           r"Page Not Found"),
    # Soft-404 / heavily-walled platforms: keep the negative pattern broad
    # so we down-weight to PROFILE_HIT_REDIRECT (lower confidence). The
    # engine still adds the platform to the cluster set, but won't grant
    # the full +30 profile_hit until corroborated.
    ("facebook",     "https://www.facebook.com/{u}",           r"This content isn't available|content you requested cannot|Page Not Found"),
    ("threads",      "https://www.threads.net/@{u}",           r"Sorry, this page isn|Page not found"),
    ("bluesky",      "https://bsky.app/profile/{u}.bsky.social", r"Profile not found|404"),
    ("mastodon-social", "https://mastodon.social/@{u}",        r"The page you are looking for|404"),
]


@dataclass(frozen=True)
class UsernameHit:
    platform: str
    url: str
    status: int
    confidence: float  # 0.0 - 1.0
    note: Optional[str] = None


def _is_probable_match(status: int, body: str, neg_pattern: Optional[str]) -> tuple[bool, float]:
    if status == 404:
        return False, 0.0
    if status >= 400:
        return False, 0.0
    if neg_pattern and re.search(neg_pattern, body, re.IGNORECASE):
        return False, 0.0
    if status == 200:
        # Hard 200 with no negative signal — high confidence.
        return True, 0.85
    if 300 <= status < 400:
        # Many sites redirect anonymous viewers — medium confidence.
        return True, 0.55
    return False, 0.0


async def _check_one(client: httpx.AsyncClient, platform: str, tmpl: str, neg: Optional[str], username: str) -> Optional[UsernameHit]:
    url = tmpl.format(u=username)
    if not is_host_allowed(url):
        return None
    try:
        r = await client.get(url)
    except httpx.HTTPError as e:
        logger.debug("username check failed %s: %s", url, e)
        return None
    body = r.text[:5000] if r.headers.get("content-type", "").startswith("text/") else ""
    is_match, conf = _is_probable_match(r.status_code, body, neg)
    if not is_match:
        return None
    return UsernameHit(platform=platform, url=url, status=r.status_code, confidence=conf)


async def check_username(username: str, timeout: int = 8) -> List[UsernameHit]:
    s = get_settings()
    if not username or not username.strip():
        return []
    username = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,40}", username):
        return []

    headers = {"User-Agent": s.user_agent, "Accept": "text/html,application/json,*/*"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
        tasks = [_check_one(client, p, t, n, username) for p, t, n in SITES]
        results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r is not None]

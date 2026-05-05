"""Ethics guard — robots.txt enforcement and domain allow/deny logic.

This module is the single chokepoint that decides whether the platform
is allowed to fetch a given URL. The platform refuses to crawl URLs
that:
  - require authentication (we never log in to a third party)
  - are explicitly disallowed by the site's robots.txt
  - belong to a denylisted host (private IPs, localhost, common cloud
    metadata endpoints, etc.)
"""
from __future__ import annotations

import ipaddress
import urllib.parse
import urllib.robotparser
from typing import Dict, Optional

import httpx

from app.core.logger import logger

# Hosts we will never fetch — protects against SSRF and accidental scraping
# of private infrastructure.
_DENY_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
}


def _is_private_host(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def is_host_allowed(url: str) -> bool:
    """Block private IPs, loopback, and known sensitive endpoints."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in _DENY_HOSTS:
        return False
    if _is_private_host(host):
        return False
    if not parsed.scheme.startswith("http"):
        return False
    return True


class RobotsCache:
    """Tiny in-process robots.txt cache."""

    def __init__(self, user_agent: str, timeout: int = 5):
        self._user_agent = user_agent
        self._timeout = timeout
        self._cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    async def allowed(self, url: str) -> bool:
        if not is_host_allowed(url):
            return False
        parsed = urllib.parse.urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._cache.get(base)
        if rp is None and base not in self._cache:
            rp = await self._load(base)
            self._cache[base] = rp
        if rp is None:
            # No robots.txt or fetch failed — be conservative and allow only
            # GET on the public surface; we treat absence as "no rules".
            return True
        return rp.can_fetch(self._user_agent, url)

    async def _load(self, base: str) -> Optional[urllib.robotparser.RobotFileParser]:
        url = f"{base}/robots.txt"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
                follow_redirects=True,
            ) as client:
                r = await client.get(url)
            if r.status_code >= 400:
                return None
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(r.text.splitlines())
            return rp
        except Exception as e:  # noqa: BLE001
            logger.debug("robots.txt fetch failed for %s: %s", base, e)
            return None

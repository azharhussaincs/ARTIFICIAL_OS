"""Polite, ethics-aware HTTP scraper for public pages.

Key guarantees:
  * never logs in to any third party
  * obeys robots.txt (configurable)
  * caps depth and pages per search
  * throttles per host
  * blocks private/loopback hosts
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.core.ethics import RobotsCache, is_host_allowed
from app.core.logger import logger
from app.core.rate_limit import HostThrottle


@dataclass
class FetchedPage:
    url: str
    status: int
    title: Optional[str] = None
    text: str = ""
    links: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)
    error: Optional[str] = None


class Scraper:
    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: Optional[int] = None,
        respect_robots: Optional[bool] = None,
    ):
        s = get_settings()
        self.ua = user_agent or s.user_agent
        self.timeout = timeout or s.request_timeout
        self.respect_robots = (
            s.respect_robots_txt if respect_robots is None else respect_robots
        )
        self.robots = RobotsCache(self.ua, timeout=5)
        self.throttle = HostThrottle(min_interval=1.0)

    async def fetch(self, url: str, client: httpx.AsyncClient) -> FetchedPage:
        if not is_host_allowed(url):
            return FetchedPage(url=url, status=0, error="host blocked")
        if self.respect_robots and not await self.robots.allowed(url):
            return FetchedPage(url=url, status=0, error="disallowed by robots.txt")

        host = urlparse(url).hostname or ""
        await self.throttle.wait(host)

        try:
            r = await client.get(url, headers={"User-Agent": self.ua})
        except httpx.HTTPError as e:
            return FetchedPage(url=url, status=0, error=str(e))

        if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
            return FetchedPage(url=url, status=r.status_code, error=f"non-html or {r.status_code}")

        return self._parse(r.text, url, r.status_code)

    @staticmethod
    def _parse(html: str, url: str, status: int) -> FetchedPage:
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.string.strip() if soup.title and soup.title.string else None

        meta: Dict[str, str] = {}
        for tag in soup.find_all("meta"):
            key = tag.get("name") or tag.get("property")
            content = tag.get("content")
            if key and content:
                meta[key.lower()] = content.strip()[:500]

        links: List[str] = []
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if href.startswith(("http://", "https://")):
                links.append(href)

        images: List[str] = []
        for img in soup.find_all("img", src=True):
            src = urljoin(url, img["src"])
            if src.startswith(("http://", "https://")):
                images.append(src)

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())

        return FetchedPage(
            url=url,
            status=status,
            title=title,
            text=text[:200_000],
            links=links[:200],
            meta=meta,
            images=images[:50],
        )

    async def crawl(self, seeds: List[str], max_pages: int) -> List[FetchedPage]:
        results: List[FetchedPage] = []
        seen: Set[str] = set()

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.ua},
        ) as client:
            queue = [u for u in seeds if u not in seen]
            for u in queue:
                seen.add(u)
            sem = asyncio.Semaphore(5)

            async def worker(u: str) -> FetchedPage:
                async with sem:
                    return await self.fetch(u, client)

            tasks = [asyncio.create_task(worker(u)) for u in queue[:max_pages]]
            for fut in asyncio.as_completed(tasks):
                page = await fut
                results.append(page)
                if len(results) >= max_pages:
                    break

        logger.info("crawl finished: %d pages, %d errors", len(results), sum(1 for p in results if p.error))
        return results

"""Per-platform profile fingerprint parsers.

A fingerprint extracts ONLY the user's own content from a profile page —
not page chrome, not platform marketing text, not footer links.

For each platform we know:
  * the CSS selector(s) for the user's display name
  * the selector(s) for the user's bio (NOT the page meta description,
    which is often a generic platform tagline)
  * the selector(s) for the user's *personal* outbound links
    (NOT the platform's own nav/footer)
  * how to detect "this page didn't load properly" (login wall,
    Cloudflare challenge, etc.) so we don't pollute the engine

Sites that block anonymous fetches entirely (LinkedIn, Instagram, X,
Facebook, TikTok) only get a weak OG-fallback parser that returns
nothing if the OG content is platform-generic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.osint.relevance import (
    is_generic_platform_text,
    is_personal_website,
)


@dataclass
class FingerprintResult:
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    personal_links: List[str] = field(default_factory=list)  # user's OWN websites
    referenced_handles: List[str] = field(default_factory=list)  # @mentions in bio
    is_blocked: bool = False  # login wall / captcha
    confidence: float = 1.0  # 0..1 — how confident we are the parse worked


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _txt(tag: Optional[Tag]) -> Optional[str]:
    if not tag:
        return None
    s = tag.get_text(" ", strip=True)
    return s or None


def _attr(tag: Optional[Tag], key: str) -> Optional[str]:
    if not tag:
        return None
    v = tag.get(key)
    if isinstance(v, list):
        v = " ".join(v)
    return (v or "").strip() or None


def _meta(soup: BeautifulSoup, key: str) -> Optional[str]:
    tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
    return _attr(tag, "content")


def _meta_image(soup: BeautifulSoup, base_url: str = "") -> Optional[str]:
    """Aggressive avatar extraction. Tries every common metadata source.

    Order matters — we want the **profile** image, not a banner / preview /
    favicon, so we start with the most specific signals.
    """
    # 1. Open Graph image (most specific for profile pages)
    for k in ("og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"):
        v = _meta(soup, k)
        if v: return _abs(v, base_url)

    # 2. JSON-LD image fields (Person/Profile schema)
    import json
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        if not s.string: continue
        try:
            blob = json.loads(s.string)
        except Exception:  # noqa: BLE001
            continue
        for entry in (blob if isinstance(blob, list) else [blob]):
            if not isinstance(entry, dict): continue
            img = entry.get("image")
            if isinstance(img, str): return _abs(img, base_url)
            if isinstance(img, dict) and img.get("url"): return _abs(str(img["url"]), base_url)
            if isinstance(img, list):
                for item in img:
                    if isinstance(item, str): return _abs(item, base_url)
                    if isinstance(item, dict) and item.get("url"): return _abs(str(item["url"]), base_url)
            # Some sites nest under "thumbnailUrl" or "logo"
            for k in ("thumbnailUrl", "logo"):
                v = entry.get(k)
                if isinstance(v, str): return _abs(v, base_url)

    # 3. <link rel="image_src" />
    link = soup.find("link", attrs={"rel": "image_src"})
    if link and link.get("href"):
        return _abs(str(link["href"]), base_url)

    # 4. <link rel="apple-touch-icon" /> as last resort (NOT favicon — too small)
    for rel in ("apple-touch-icon", "apple-touch-icon-precomposed"):
        l = soup.find("link", attrs={"rel": rel})
        if l and l.get("href"):
            href = str(l["href"])
            # skip the tiny 16x16/32x32 favicons
            if "favicon" in href.lower(): continue
            return _abs(href, base_url)

    return None


def _abs(url: str, base: str) -> str:
    """Resolve `url` against `base` if it's relative. No-op if already absolute."""
    if url.startswith(("http://", "https://", "data:")):
        return url
    if not base:
        return url
    from urllib.parse import urljoin
    return urljoin(base, url)


# ---------------------------------------------------------------------------
# Platform-default avatar filter
# ---------------------------------------------------------------------------
#
# When a page is rate-limited / login-walled / Cloudflare-challenged, the
# `og:image` we extract is often the SITE's branding (a logo, a generic
# share image) rather than the user's avatar. Promoting that as a real
# avatar would poison clustering: every blocked GitHub page would share
# the same hash and falsely indicate "same person".
#
# This denylist contains URL fragments / paths that platforms use for
# their own marketing / default-profile images. If the extracted avatar
# matches any of these, we treat it as no-avatar.

PLATFORM_DEFAULT_IMAGE_FRAGMENTS = (
    # GitHub
    "githubassets.com/images/modules",
    "githubassets.com/assets/octocat",
    "github.githubassets.com/images/site",
    # Twitter / X
    "abs.twimg.com/sticky/default_profile_images",
    "abs.twimg.com/icons/apple-touch-icon",
    "abs.twimg.com/responsive-web",
    # Meta family
    "instagram.com/static/images/",
    "facebook.com/images/fb_icon",
    "static.xx.fbcdn.net/rsrc.php",
    # LinkedIn
    "static.licdn.com/aero",
    "static.licdn.com/scds",
    # Google / YouTube
    "youtube.com/img/desktop/yt_1200",
    "ytimg.com/img/yt_logo",
    "yt3.ggpht.com/yt-",                     # generic YT icons (channel avatars are different path)
    "google.com/images/branding",
    # TikTok
    "tiktok.com/static/img",
    "lf16-tiktok-web",                       # cdn marketing assets
    # Reddit
    "redditstatic.com/icon",
    "redditstatic.com/desktop2x",
    # Generic
    "default_profile", "default-avatar", "default_avatar",
    "anonymous-user", "blank-profile", "no-avatar",
    "/missing.png", "/missing-avatar",
    "favicon", "apple-touch-icon",
)


def _is_platform_default_image(url: Optional[str]) -> bool:
    if not url:
        return True
    u = url.lower()
    return any(frag in u for frag in PLATFORM_DEFAULT_IMAGE_FRAGMENTS)


def normalize_image_url(url: Optional[str]) -> Optional[str]:
    """Strip query params + fragment. Used only for de-duplication; the
    original URL is still what we send through the proxy for display."""
    if not url:
        return url
    from urllib.parse import urlparse, urlunparse
    try:
        p = urlparse(url)
    except ValueError:
        return url
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def _looks_blocked(soup: BeautifulSoup) -> bool:
    title = (_txt(soup.title) or "").lower()
    body = soup.find("body")
    body_text = (_txt(body) or "")[:2000].lower()
    blocked_signals = (
        "just a moment", "attention required", "checking your browser",
        "log in", "sign in", "create an account", "are you a robot",
        "access denied", "page not found", "rate limit",
    )
    if any(s in title for s in blocked_signals):
        return True
    if len(body_text) < 200 and any(s in body_text for s in blocked_signals):
        return True
    return False


_HANDLE_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{3,30})\b")


def _filter_personal_links(soup: BeautifulSoup, *, scope: Optional[str] = None) -> List[str]:
    """Return outbound links that pass the personal-website filter.

    `scope` is an optional CSS selector that narrows extraction to a
    sidebar / bio container — important for sites where the body has
    thousands of unrelated links."""
    container = soup
    if scope:
        found = soup.select_one(scope)
        if found:
            container = found
    out: List[str] = []
    seen: set[str] = set()
    for a in container.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("http://", "https://")) and href not in seen:
            if is_personal_website(href):
                out.append(href)
                seen.add(href)
    return out[:20]


# ---------------------------------------------------------------------------
# Per-platform parsers
# ---------------------------------------------------------------------------

def parse_github(soup: BeautifulSoup, url: str) -> FingerprintResult:
    """GitHub user profile.

    Robust selectors at time of writing:
      * display name: `<span class="p-name vcard-fullname">`
      * bio:          `<div class="p-note user-profile-bio">`
      * personal site:`<a rel="nofollow me" href="...">` in `.vcard-details`
      * social refs:  `<a class="Link--primary" data-test-selector="profile-social-link">`
    """
    res = FingerprintResult()
    res.display_name = _txt(soup.select_one("span.p-name.vcard-fullname")) \
        or _txt(soup.select_one(".vcard-names span.p-name")) \
        or _safe_og_title(soup)
    bio = _txt(soup.select_one("div.p-note.user-profile-bio")) \
        or _txt(soup.select_one(".user-profile-bio"))
    if bio and not is_generic_platform_text(bio):
        res.bio = bio

    # Personal website: vcard-detail with rel="nofollow me"
    site = soup.select_one('.vcard-details a[rel~="me"]') \
        or soup.select_one(".vcard-details a.Link--primary[rel*='nofollow']")
    if site:
        href = _attr(site, "href")
        if href and is_personal_website(href):
            res.personal_links.append(href)

    # Social profile links (twitter, linkedin etc) the user added themselves.
    for a in soup.select("a[data-test-selector='profile-social-link']"):
        href = _attr(a, "href")
        if href and href.startswith(("http://", "https://")):
            res.personal_links.append(href)

    res.avatar_url = _attr(soup.select_one("img.avatar-user"), "src") or _meta_image(soup, url)
    if res.bio:
        res.referenced_handles = sorted({m.group(1).lower() for m in _HANDLE_RE.finditer(res.bio)})
    return res


def parse_gitlab(soup: BeautifulSoup, url: str) -> FingerprintResult:
    res = FingerprintResult()
    res.display_name = _txt(soup.select_one(".user-info .name")) or _safe_og_title(soup)
    bio = _txt(soup.select_one(".user-info .user-bio")) or _txt(soup.select_one(".bio"))
    if bio and not is_generic_platform_text(bio):
        res.bio = bio
    for sel in ('.user-info a[itemprop="url"]', '.user-info .website a', '.user-bio a'):
        for a in soup.select(sel):
            href = _attr(a, "href")
            if href and is_personal_website(href):
                res.personal_links.append(href)
    res.avatar_url = _attr(soup.select_one(".user-avatar img"), "src") or _meta_image(soup, url)
    return res


def parse_devto(soup: BeautifulSoup, url: str) -> FingerprintResult:
    res = FingerprintResult()
    res.display_name = _txt(soup.select_one("h1.crayons-title")) \
        or _txt(soup.select_one(".profile-header__name")) \
        or _safe_og_title(soup)
    bio = _txt(soup.select_one(".profile-header__summary")) \
        or _txt(soup.select_one(".user-summary"))
    if bio and not is_generic_platform_text(bio):
        res.bio = bio
    # Sidebar links
    for a in soup.select(".profile-header__meta a, .profile-meta a"):
        href = _attr(a, "href")
        if href and is_personal_website(href):
            res.personal_links.append(href)
    res.avatar_url = _attr(soup.select_one(".profile-header__avatar img"), "src") or _meta_image(soup, url)
    return res


def parse_medium(soup: BeautifulSoup, url: str) -> FingerprintResult:
    res = FingerprintResult()
    name = _safe_og_title(soup)
    # Medium pages OG-title is "Real Name – Medium"
    if name:
        name = re.sub(r"\s*[–-]\s*medium\s*$", "", name, flags=re.I)
    res.display_name = name
    bio = _meta(soup, "og:description") or _meta(soup, "description")
    if bio and not is_generic_platform_text(bio):
        res.bio = bio
    res.avatar_url = _meta_image(soup, url)
    return res


def parse_reddit(soup: BeautifulSoup, url: str) -> FingerprintResult:
    """Reddit user 'about' is JSON; the HTML profile page has minimal info."""
    res = FingerprintResult()
    name = _safe_og_title(soup)
    if name:
        # "u/handle" — strip prefix
        name = re.sub(r"^u/", "", name).strip()
    res.display_name = name
    bio = _meta(soup, "og:description")
    if bio and not is_generic_platform_text(bio):
        res.bio = bio
    res.avatar_url = _meta_image(soup, url)
    return res


def parse_youtube(soup: BeautifulSoup, url: str) -> FingerprintResult:
    """YouTube channel page. Often gates behind consent — fall back to OG."""
    res = FingerprintResult()
    name = _meta(soup, "og:title") or _safe_og_title(soup)
    if name and not is_generic_platform_text(name):
        res.display_name = name
    desc = _meta(soup, "og:description")
    if desc and not is_generic_platform_text(desc):
        res.bio = desc
    res.avatar_url = _meta_image(soup, url)
    return res


def parse_about_me(soup: BeautifulSoup, url: str) -> FingerprintResult:
    res = FingerprintResult()
    res.display_name = _txt(soup.select_one("h1")) or _safe_og_title(soup)
    bio = _meta(soup, "og:description") or _txt(soup.select_one(".bio"))
    if bio and not is_generic_platform_text(bio):
        res.bio = bio
    # about.me users typically link out to all their socials
    for a in soup.select("a[rel='me'], .links a, .user-links a"):
        href = _attr(a, "href")
        if href and is_personal_website(href):
            res.personal_links.append(href)
    res.avatar_url = _meta_image(soup, url)
    return res


def parse_keybase(soup: BeautifulSoup, url: str) -> FingerprintResult:
    res = FingerprintResult()
    res.display_name = _txt(soup.select_one(".display_name")) or _safe_og_title(soup)
    bio = _txt(soup.select_one(".bio"))
    if bio and not is_generic_platform_text(bio):
        res.bio = bio
    for a in soup.select(".proofs a"):
        href = _attr(a, "href")
        if href and is_personal_website(href):
            res.personal_links.append(href)
    res.avatar_url = _meta_image(soup, url)
    return res


def parse_generic_og(soup: BeautifulSoup, url: str) -> FingerprintResult:
    """Last-resort parser: use OG metadata, but reject generic platform text."""
    res = FingerprintResult()
    title = _meta(soup, "og:title") or _txt(soup.title)
    desc = _meta(soup, "og:description") or _meta(soup, "description")
    if title and not is_generic_platform_text(title):
        res.display_name = title
    if desc and not is_generic_platform_text(desc):
        res.bio = desc
    res.avatar_url = _meta_image(soup, url)
    res.confidence = 0.5  # we trust OG less than per-site selectors
    return res


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

PARSERS: Dict[str, Callable[[BeautifulSoup, str], FingerprintResult]] = {
    "github": parse_github,
    "gitlab": parse_gitlab,
    "dev.to": parse_devto,
    "medium": parse_medium,
    "reddit": parse_reddit,
    "youtube": parse_youtube,
    "about.me": parse_about_me,
    "keybase": parse_keybase,
}


def parse_profile(html: str, url: str, platform: str) -> FingerprintResult:
    """Run the right fingerprint for `platform`, falling back to generic OG.

    If the page looks blocked (login wall / captcha) we mark the result
    as such so the engine knows not to use the (probably generic) text."""
    soup = BeautifulSoup(html, "lxml")
    if _looks_blocked(soup):
        res = FingerprintResult(is_blocked=True, confidence=0.2)
        # Even when blocked, OG image is often still present and valid.
        res.avatar_url = _meta_image(soup, url)
        return res

    parser = PARSERS.get(platform.lower(), parse_generic_og)
    res = parser(soup, url)

    # Final sanity: bio must not be generic, display name must look like a name/handle.
    if res.bio and is_generic_platform_text(res.bio):
        res.bio = None
    if res.display_name and is_generic_platform_text(res.display_name):
        res.display_name = None
    if res.avatar_url and _is_platform_default_image(res.avatar_url):
        # The page yielded only the platform's branding, not a real avatar
        res.avatar_url = None

    # Capture @handles from bio (cross-platform corroboration signal).
    if res.bio:
        res.referenced_handles = sorted(set(res.referenced_handles)
                                        | {m.group(1).lower() for m in _HANDLE_RE.finditer(res.bio)})

    # Deduplicate personal links + final relevance gate.
    seen: set[str] = set()
    out_links: List[str] = []
    for href in res.personal_links:
        if href in seen:
            continue
        seen.add(href)
        if is_personal_website(href):
            out_links.append(href)
    res.personal_links = out_links

    return res


def _safe_og_title(soup: BeautifulSoup) -> Optional[str]:
    raw = _meta(soup, "og:title") or _txt(soup.title)
    if raw and is_generic_platform_text(raw):
        return None
    return raw

"""Relevance gate — the single chokepoint that decides whether a candidate
identifier is worth turning into a Finding, or is just platform noise.

The current pipeline used to extract every outbound link from a profile
page and emit it as a "related website" — which dragged in github.com,
about/legal/privacy/help pages, CDN URLs, and platform chrome. This
module rejects those at the source, before they ever reach the
correlation engine.

Three filters are exposed:

  * `is_noise_url(url)`           — block platform infrastructure / static / chrome
  * `is_generic_platform_text(t)` — block known platform-generated bios
  * `relevance_to_seed(value, seed_handle, seed_name)`
        → returns (delta, reason) — how strongly this finding is tied to
        the original seed. Used to apply the user-spec'd ±deltas.

Anything that does not pass `is_noise_url` is silently dropped. Anything
that passes but doesn't tie back to the seed gets a relevance penalty.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Domain denylists
# ---------------------------------------------------------------------------

# Platform-OWNED domains. A link to these is almost never the user's own
# identity — it is platform chrome (footer, help, blog, terms, marketing,
# CDN, etc.). We MUST NOT promote these into "related website" Findings.
PLATFORM_OWNED_DOMAINS = {
    # GitHub
    "github.com", "github.io", "githubusercontent.com", "githubassets.com",
    "github.blog", "github.dev", "github.community", "githubstatus.com",
    "docs.github.com", "support.github.com", "education.github.com",
    "resources.github.com", "enterprise.github.com",
    # GitLab
    "gitlab.com", "gitlab.io", "gitlab-static.net", "about.gitlab.com",
    "docs.gitlab.com",
    # Twitter / X
    "twitter.com", "x.com", "t.co", "twimg.com", "help.twitter.com",
    "business.twitter.com", "developer.twitter.com",
    # Meta family
    "facebook.com", "fb.com", "fbcdn.net", "instagram.com", "cdninstagram.com",
    "messenger.com", "whatsapp.com", "wa.me", "threads.net",
    "about.meta.com", "about.fb.com",
    # LinkedIn
    "linkedin.com", "licdn.com", "lnkd.in",
    # Google / YouTube
    "google.com", "google.co.uk", "googleusercontent.com", "youtube.com",
    "youtu.be", "ytimg.com", "googleapis.com", "gstatic.com",
    "policies.google.com", "support.google.com", "about.google",
    # TikTok / ByteDance
    "tiktok.com", "tiktokcdn.com", "bytedance.com", "musical.ly",
    # Reddit
    "reddit.com", "redd.it", "redditmedia.com", "redditstatic.com",
    "redditinc.com",
    # Medium / Substack
    "medium.com", "medium.statuspage.io", "policy.medium.com",
    "substack.com", "substackcdn.com",
    # Dev.to / Forem
    "dev.to", "forem.com",
    # Pinterest / Snapchat / Vimeo
    "pinterest.com", "pinimg.com", "snapchat.com", "snap.com",
    "vimeo.com", "vhx.tv",
    # Stack Exchange
    "stackoverflow.com", "stackexchange.com", "imgur.com",
    # Misc developer ecosystem
    "npmjs.com", "hub.docker.com", "docker.com", "keybase.io",
    "hackerone.com", "bitbucket.org", "atlassian.com",
    "dribbble.com", "behance.net", "about.me",
    # Generic CDN / cookie / consent
    "cookielaw.org", "onetrust.com", "trustarc.com",
    "fastly.net", "cloudflare.com", "cloudfront.net", "akamaihd.net",
    "jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
    # Email providers — the domain alone is not personal identity
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com",
    "hotmail.com", "icloud.com", "proton.me", "protonmail.com",
    "live.com", "aol.com", "yandex.com", "mail.ru",
}

# Path patterns that indicate a non-identity page on a platform.
# (Used in addition to the domain denylist so an `about.example.com`
# host with a `/legal` path is doubly rejected.)
IGNORE_PATH_PATTERNS = re.compile(
    r"(^|/)(about|terms|privacy|legal|cookies?|gdpr|dmca|copyright|"
    r"help|support|docs?|api|developers?|status|security|sitemap|"
    r"login|signin|signup|register|join|password|reset|"
    r"pricing|enterprise|business|advertis|press|jobs|careers|"
    r"blog|newsroom|news|community|events?|conferences?|"
    r"explore|trending|discover|search|browse|categor(y|ies)|tags?|"
    r"download|apps?|mobile|extension|widget|embed|share|"
    r"partners?|affiliates?|sponsors?|brand|brands?|guidelines?|"
    r"feed|rss|atom|opml|sitemap\.xml|robots\.txt|favicon\.ico|"
    r"opensearch|manifest\.json|service-worker)(/|\.|$|\?|#)",
    re.IGNORECASE,
)

# File extensions that are static assets, not identities.
STATIC_ASSET_EXT = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|ico|bmp|tiff?|heic|"
    r"css|js|mjs|map|woff2?|ttf|otf|eot|"
    r"mp4|webm|mov|m4a|mp3|wav|ogg|flac|"
    r"pdf|zip|tar|gz|bz2|xz|7z|rar)(\?.*)?$",
    re.IGNORECASE,
)

# Strings that platforms generate when no real content is present
# (rate-limited, logged-out, login-walled). NEVER use these as a bio
# or display name.
GENERIC_PLATFORM_TEXT = (
    re.compile(r"^tiktok\b.*make your day", re.I),
    re.compile(r"^github(\s*[·\-:|])?\s*(let'?s build from here|where the world builds software)", re.I),
    re.compile(r"^linkedin\b.*log\s*in", re.I),
    re.compile(r"^join linkedin\b", re.I),
    re.compile(r"^sign\s*in\s*[·\-|]\s*", re.I),
    re.compile(r"^log\s*in\s*[·\-|]\s*", re.I),
    re.compile(r"^instagram\s*$", re.I),
    re.compile(r"^x\.com\b", re.I),
    re.compile(r"^twitter\s*$", re.I),
    re.compile(r"^reddit\s*[·\-|]\s*the front page of the internet", re.I),
    re.compile(r"^facebook\s*$", re.I),
    re.compile(r"^see posts, photos and more on facebook", re.I),
    re.compile(r"^youtube\s*$", re.I),
    re.compile(r"^enjoy the videos and music you love", re.I),
    re.compile(r"^pinterest\s*[·\-|]?\s*$", re.I),
    re.compile(r"^medium\s*[·\-|]?\s*where good ideas find you", re.I),
    re.compile(r"^stack overflow\s*[·\-|]\s*where developers", re.I),
    re.compile(r"^community\s*$", re.I),
    re.compile(r"^profile\s*$", re.I),
    re.compile(r"^home\s*$", re.I),
    re.compile(r"^page not found", re.I),
    re.compile(r"^access denied", re.I),
    re.compile(r"^just a moment", re.I),  # Cloudflare challenge
    re.compile(r"^attention required", re.I),
    re.compile(r"^are you a robot", re.I),
)


# ---------------------------------------------------------------------------
# Public predicates
# ---------------------------------------------------------------------------

def normalize_host(host: Optional[str]) -> str:
    if not host:
        return ""
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_platform_owned(host: str) -> bool:
    """True if `host` is a platform-infrastructure domain (or a subdomain of one)."""
    host = normalize_host(host)
    if not host:
        return False
    # Exact match
    if host in PLATFORM_OWNED_DOMAINS:
        return True
    # Suffix match (covers cdn.tiktok.com -> tiktok.com etc.)
    for d in PLATFORM_OWNED_DOMAINS:
        if host.endswith("." + d):
            return True
    return False


def is_noise_url(url: str) -> bool:
    """True if this URL is platform chrome, static asset, or a non-identity page."""
    if not url:
        return True
    try:
        p = urlparse(url)
    except ValueError:
        return True
    if p.scheme not in ("http", "https"):
        return True
    host = normalize_host(p.hostname)
    if not host:
        return True
    if is_platform_owned(host):
        return True
    if STATIC_ASSET_EXT.search(p.path or ""):
        return True
    if IGNORE_PATH_PATTERNS.search(p.path or ""):
        return True
    return False


def is_generic_platform_text(text: Optional[str]) -> bool:
    if not text:
        return True
    t = text.strip()
    if len(t) < 2:
        return True
    if len(t) > 600:
        # Most real bios are < 600 chars; a giant block is usually page text.
        return True
    for pat in GENERIC_PLATFORM_TEXT:
        if pat.search(t):
            return True
    return False


def is_personal_website(url: str) -> bool:
    """A URL that *might* be the user's personal site (not a platform / chrome)."""
    if is_noise_url(url):
        return False
    return True


# ---------------------------------------------------------------------------
# Seed-relevance scoring
# ---------------------------------------------------------------------------

def _tokens(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())


def _name_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    aa = re.sub(r"[^a-z0-9 ]", "", a.lower()).strip()
    bb = re.sub(r"[^a-z0-9 ]", "", b.lower()).strip()
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    set_a, set_b = set(aa.split()), set(bb.split())
    jacc = (len(set_a & set_b) / max(1, len(set_a | set_b))) if set_a | set_b else 0
    seq = SequenceMatcher(None, aa, bb).ratio()
    return max(jacc, seq)


def _handle_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    aa = re.sub(r"[^a-z0-9]", "", a.lower())
    bb = re.sub(r"[^a-z0-9]", "", b.lower())
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    if aa in bb or bb in aa:
        return 0.85
    return SequenceMatcher(None, aa, bb).ratio()


def relevance_to_seed(
    value: str,
    *,
    seed_handles: Iterable[str] = (),
    seed_names: Iterable[str] = (),
    seed_domains: Iterable[str] = (),
) -> Tuple[float, str]:
    """Score how strongly `value` is tied to the seed. Returns (0..1, reason).

    Used to apply the relevance penalty when a Finding has none of the
    expected identifiers in its provenance."""
    seed_handles = [s.lower() for s in seed_handles if s]
    seed_names = [s for s in seed_names if s]
    seed_domains = [normalize_host(s) for s in seed_domains if s]

    v = (value or "").strip()
    if not v:
        return 0.0, "empty"

    # Handle-vs-handle
    best_h = 0.0
    best_h_src = ""
    for h in seed_handles:
        s = _handle_similarity(v, h)
        if s > best_h:
            best_h, best_h_src = s, h

    # Name-vs-anything
    best_n = 0.0
    best_n_src = ""
    for n in seed_names:
        s = _name_similarity(v, n)
        if s > best_n:
            best_n, best_n_src = s, n

    # Domain proximity (for website / domain findings)
    host = normalize_host(urlparse(v).hostname) if "://" in v else normalize_host(v)
    domain_match = 0.0
    domain_src = ""
    for d in seed_domains:
        if not d:
            continue
        if host == d or host.endswith("." + d) or d.endswith("." + host):
            domain_match = 1.0
            domain_src = d
            break

    score = max(best_h, best_n, domain_match)
    if domain_match:
        return 1.0, f"shares domain with seed ({domain_src})"
    if best_h >= 0.85:
        return best_h, f"handle ≈ seed handle '{best_h_src}'"
    if best_n >= 0.85:
        return best_n, f"name ≈ seed name '{best_n_src}'"
    if score >= 0.5:
        return score, f"weak match against seed (best {score:.2f})"
    return score, "no direct tie to seed"

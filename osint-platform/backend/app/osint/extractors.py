"""Regex extractors for emails, phones, usernames, and social URLs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Set
from urllib.parse import urlparse

import phonenumbers

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24})"
)

# very loose international form — we validate hits with `phonenumbers`
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")

USERNAME_HANDLE_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{3,30})\b")

SOCIAL_HOSTS = {
    "twitter.com": "twitter",
    "x.com": "twitter",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "github.com": "github",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "reddit.com": "reddit",
    "medium.com": "medium",
    "pinterest.com": "pinterest",
    "snapchat.com": "snapchat",
    "vimeo.com": "vimeo",
    "stackoverflow.com": "stackoverflow",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
    "dribbble.com": "dribbble",
    "behance.net": "behance",
}


@dataclass(frozen=True)
class SocialLink:
    platform: str
    url: str
    handle: str | None = None


def extract_emails(text: str) -> List[str]:
    found = {m.group(1).lower() for m in EMAIL_RE.finditer(text or "")}
    return sorted(found)


def extract_phones(text: str, default_region: str = "US") -> List[str]:
    out: Set[str] = set()
    if not text:
        return []
    for m in PHONE_RE.finditer(text):
        raw = m.group(1)
        try:
            num = phonenumbers.parse(raw, None)
        except phonenumbers.NumberParseException:
            try:
                num = phonenumbers.parse(raw, default_region)
            except phonenumbers.NumberParseException:
                continue
        if phonenumbers.is_possible_number(num) and phonenumbers.is_valid_number(num):
            out.add(phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164))
    return sorted(out)


def extract_handles(text: str) -> List[str]:
    return sorted({m.group(1).lower() for m in USERNAME_HANDLE_RE.finditer(text or "")})


def extract_social_links(urls: Iterable[str]) -> List[SocialLink]:
    seen: Set[str] = set()
    out: List[SocialLink] = []
    for url in urls:
        if not url:
            continue
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            continue
        if host.startswith("www."):
            host = host[4:]
        platform = SOCIAL_HOSTS.get(host)
        if not platform or url in seen:
            continue
        seen.add(url)
        handle = _extract_handle_from_path(url)
        out.append(SocialLink(platform=platform, url=url, handle=handle))
    return out


def _extract_handle_from_path(url: str) -> str | None:
    try:
        path = urlparse(url).path.strip("/")
    except ValueError:
        return None
    if not path:
        return None
    first = path.split("/")[0]
    if first.lower() in {"in", "company", "pages", "groups", "user", "u", "people"}:
        parts = path.split("/")
        if len(parts) >= 2 and parts[1]:
            return parts[1].lower()
        return None
    return first.lower() if first else None

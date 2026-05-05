"""Google dork query generator.

Returns shareable search-engine URLs. The platform does NOT itself
hammer Google's results page — it produces the dork queries so the
analyst can open them, and (optionally) hands them to a configured
public search API such as SerpAPI.
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import List, Literal

QueryKind = Literal["name", "email", "phone", "username"]


@dataclass(frozen=True)
class Dork:
    label: str          # human-readable description
    query: str          # raw dork string
    google_url: str     # opens directly in Google
    bing_url: str       # alternative engine
    duckduckgo_url: str  # privacy-respecting engine


def _url(engine: str, q: str) -> str:
    quoted = urllib.parse.quote_plus(q)
    if engine == "google":
        return f"https://www.google.com/search?q={quoted}"
    if engine == "bing":
        return f"https://www.bing.com/search?q={quoted}"
    if engine == "duckduckgo":
        return f"https://duckduckgo.com/?q={quoted}"
    raise ValueError(engine)


def _dork(label: str, q: str) -> Dork:
    return Dork(
        label=label,
        query=q,
        google_url=_url("google", q),
        bing_url=_url("bing", q),
        duckduckgo_url=_url("duckduckgo", q),
    )


def _q(value: str) -> str:
    """Quote a value if it contains whitespace."""
    return f'"{value}"' if " " in value else f'"{value}"'


def generate_for_name(name: str) -> List[Dork]:
    name_q = _q(name)
    return [
        _dork("LinkedIn profile", f'site:linkedin.com/in {name_q}'),
        _dork("Twitter / X mentions", f'site:twitter.com OR site:x.com {name_q}'),
        _dork("Facebook profile", f'site:facebook.com {name_q}'),
        _dork("GitHub user pages", f'site:github.com {name_q}'),
        _dork("Public CVs / resumes", f'{name_q} (filetype:pdf OR filetype:doc OR filetype:docx) (resume OR cv)'),
        _dork("Conference / talk listings", f'{name_q} (speaker OR talk OR conference)'),
        _dork("News mentions", f'{name_q} (news OR press OR interview)'),
        _dork("Public mentions", f'intext:{name_q}'),
    ]


def generate_for_email(email: str) -> List[Dork]:
    email_q = f'"{email}"'
    domain = email.split("@", 1)[-1]
    local = email.split("@", 1)[0]
    return [
        _dork("Direct mentions", email_q),
        _dork("Pastebin / paste sites", f'{email_q} (site:pastebin.com OR site:paste.ee OR site:ghostbin.com)'),
        _dork("GitHub commits / configs", f'site:github.com {email_q}'),
        _dork("LinkedIn", f'site:linkedin.com {email_q}'),
        _dork("Local-part as username", f'"{local}" (site:twitter.com OR site:github.com OR site:instagram.com)'),
        _dork("Other addresses on same domain", f'"@{domain}" -site:{domain}'),
        _dork("Indexed documents", f'{email_q} (filetype:pdf OR filetype:doc OR filetype:xls)'),
    ]


def generate_for_phone(phone: str) -> List[Dork]:
    digits = "".join(ch for ch in phone if ch.isdigit())
    plain = f'"{phone}"'
    digit = f'"{digits}"'
    return [
        _dork("Direct mentions", plain),
        _dork("Digits only", digit),
        _dork("Business listings", f'{plain} (contact OR phone OR tel)'),
        _dork("Pastes", f'{plain} (site:pastebin.com OR site:paste.ee)'),
        _dork("Public directories", f'{plain} (whitepages OR yellowpages OR directory)'),
        _dork("Indexed PDFs", f'{plain} filetype:pdf'),
    ]


def generate_for_username(username: str) -> List[Dork]:
    u = f'"{username}"'
    return [
        _dork("GitHub", f'site:github.com {u}'),
        _dork("Twitter / X", f'site:twitter.com OR site:x.com {u}'),
        _dork("Instagram", f'site:instagram.com {u}'),
        _dork("Reddit", f'site:reddit.com/user {u}'),
        _dork("LinkedIn", f'site:linkedin.com/in {u}'),
        _dork("Profile pages", f'intitle:profile {u}'),
        _dork("Forum bios", f'{u} (about OR bio OR profile)'),
        _dork("Cross-platform mentions", u),
    ]


def generate(kind: QueryKind, value: str) -> List[Dork]:
    value = value.strip()
    if not value:
        return []
    if kind == "name":
        return generate_for_name(value)
    if kind == "email":
        return generate_for_email(value)
    if kind == "phone":
        return generate_for_phone(value)
    if kind == "username":
        return generate_for_username(value)
    raise ValueError(f"unknown query kind: {kind}")

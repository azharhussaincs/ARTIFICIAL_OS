"""Email validation + lightweight enrichment.

Hard rules:
  * we never attempt account takeover, password reset abuse, or login probing
  * we DO NOT call HIBP without an explicit API key
  * gravatar lookup uses the public hash endpoint (RFC-compliant, no auth)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

import httpx
from email_validator import EmailNotValidError, validate_email

from app.config import get_settings


@dataclass
class EmailReport:
    email: str
    is_valid: bool
    normalized: Optional[str]
    domain: Optional[str]
    gravatar_url: Optional[str]
    gravatar_exists: bool = False
    breach_count: Optional[int] = None  # populated only if HIBP key is set
    breach_note: Optional[str] = None


async def analyze_email(email: str) -> EmailReport:
    s = get_settings()
    try:
        v = validate_email(email, check_deliverability=False)
        normalized = v.normalized
        domain = v.domain
        is_valid = True
    except EmailNotValidError:
        return EmailReport(email=email, is_valid=False, normalized=None, domain=None, gravatar_url=None)

    gravatar_hash = hashlib.md5(normalized.lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{gravatar_hash}?d=404"

    gravatar_exists = False
    try:
        async with httpx.AsyncClient(timeout=6, headers={"User-Agent": s.user_agent}) as client:
            r = await client.get(gravatar_url)
            gravatar_exists = r.status_code == 200
    except httpx.HTTPError:
        pass

    breach_count = None
    breach_note = None
    if s.hibp_api_key:
        # HaveIBeenPwned requires an API key. We only call it if explicitly
        # configured by the operator.
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"https://haveibeenpwned.com/api/v3/breachedaccount/{normalized}",
                    headers={
                        "hibp-api-key": s.hibp_api_key,
                        "User-Agent": s.user_agent,
                    },
                    params={"truncateResponse": "true"},
                )
            if r.status_code == 200:
                breach_count = len(r.json() or [])
            elif r.status_code == 404:
                breach_count = 0
            else:
                breach_note = f"HIBP returned {r.status_code}"
        except httpx.HTTPError as e:
            breach_note = f"HIBP error: {e}"
    else:
        breach_note = "HIBP key not configured (skipped)"

    return EmailReport(
        email=email,
        is_valid=is_valid,
        normalized=normalized,
        domain=domain,
        gravatar_url=gravatar_url if gravatar_exists else None,
        gravatar_exists=gravatar_exists,
        breach_count=breach_count,
        breach_note=breach_note,
    )

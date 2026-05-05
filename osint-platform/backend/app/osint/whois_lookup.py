"""Public RDAP (Registration Data Access Protocol) lookup.

We use rdap.org as a transport — it's the IETF-blessed JSON replacement
for raw whois and routes to the authoritative RDAP server for each TLD.
No API key, no scraping; just a single public HTTPS GET.

Returns a normalized dict the correlation engine can fold into Findings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.core.logger import logger


@dataclass
class WhoisRecord:
    domain: str
    found: bool = False
    registrar: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    expires: Optional[str] = None
    nameservers: List[str] = field(default_factory=list)
    status: List[str] = field(default_factory=list)
    contacts: List[Dict[str, str]] = field(default_factory=list)
    raw_url: Optional[str] = None
    error: Optional[str] = None


def _date_for(events: list, action: str) -> Optional[str]:
    for e in events or []:
        if e.get("eventAction") == action:
            return e.get("eventDate")
    return None


def _vcard_to_contact(vcard: list) -> Dict[str, str]:
    """Parse a jCard array (RDAP entity[].vcardArray)."""
    out: Dict[str, str] = {}
    if not isinstance(vcard, list) or len(vcard) < 2:
        return out
    for entry in vcard[1]:
        if not isinstance(entry, list) or len(entry) < 4:
            continue
        prop, _params, _type, value = entry[0], entry[1], entry[2], entry[3]
        if prop == "fn":
            out["name"] = str(value)
        elif prop == "email":
            out["email"] = str(value)
        elif prop == "tel":
            tel = value if isinstance(value, str) else (value[0] if value else "")
            out["phone"] = str(tel)
        elif prop == "org":
            org = value if isinstance(value, str) else " ".join(value or [])
            out["org"] = str(org)
        elif prop == "adr":
            parts = [p for p in (value or []) if p]
            if parts:
                out["address"] = ", ".join(parts)
    return out


async def lookup_domain(domain: str, timeout: int = 8) -> WhoisRecord:
    s = get_settings()
    domain = (domain or "").strip().lower().lstrip(".")
    if not domain or "/" in domain or " " in domain:
        return WhoisRecord(domain=domain, found=False, error="invalid domain")

    url = f"https://rdap.org/domain/{quote(domain)}"
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": s.user_agent, "Accept": "application/rdap+json,application/json"},
            follow_redirects=True,
        ) as client:
            r = await client.get(url)
    except httpx.HTTPError as e:
        return WhoisRecord(domain=domain, error=f"network: {e}", raw_url=url)

    if r.status_code == 404:
        return WhoisRecord(domain=domain, found=False, raw_url=url)
    if r.status_code >= 400:
        return WhoisRecord(domain=domain, error=f"rdap http {r.status_code}", raw_url=url)

    try:
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return WhoisRecord(domain=domain, error=f"bad rdap json: {e}", raw_url=url)

    rec = WhoisRecord(domain=domain, found=True, raw_url=url)
    rec.status = list(data.get("status") or [])
    rec.created = _date_for(data.get("events"), "registration")
    rec.updated = _date_for(data.get("events"), "last changed")
    rec.expires = _date_for(data.get("events"), "expiration")
    rec.nameservers = [
        (ns.get("ldhName") or "").lower()
        for ns in (data.get("nameservers") or [])
        if ns.get("ldhName")
    ]
    for ent in data.get("entities") or []:
        roles = ent.get("roles") or []
        if "registrar" in roles:
            for v in (ent.get("vcardArray") or [None, []])[1] or []:
                if isinstance(v, list) and v and v[0] == "fn":
                    rec.registrar = str(v[3])
                    break
        contact = _vcard_to_contact(ent.get("vcardArray") or [])
        if contact:
            contact["roles"] = ",".join(roles) if roles else ""
            rec.contacts.append(contact)

    logger.debug("rdap %s -> registrar=%s contacts=%d", domain, rec.registrar, len(rec.contacts))
    return rec

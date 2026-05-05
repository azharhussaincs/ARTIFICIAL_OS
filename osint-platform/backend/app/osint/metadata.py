"""Page metadata extraction (Open Graph, Twitter Cards, schema.org JSON-LD)."""
from __future__ import annotations

import json
from typing import Dict, List

from bs4 import BeautifulSoup


def extract_page_metadata(html: str) -> Dict[str, object]:
    """Return Open Graph / Twitter Card / JSON-LD metadata."""
    soup = BeautifulSoup(html, "lxml")
    out: Dict[str, object] = {"og": {}, "twitter": {}, "jsonld": []}

    for tag in soup.find_all("meta"):
        prop = (tag.get("property") or "").lower()
        name = (tag.get("name") or "").lower()
        content = tag.get("content")
        if not content:
            continue
        if prop.startswith("og:"):
            out["og"][prop[3:]] = content
        elif name.startswith("twitter:"):
            out["twitter"][name[8:]] = content

    blocks: List[object] = []
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        if not s.string:
            continue
        try:
            blocks.append(json.loads(s.string))
        except Exception:  # noqa: BLE001
            continue
    out["jsonld"] = blocks
    return out

"""Endpoint: generate dork queries without crawling."""
from __future__ import annotations

from fastapi import APIRouter

from app.osint import dorks as dork_mod
from app.schemas import DorkOnlyRequest

router = APIRouter(prefix="/dorks", tags=["dorks"])


@router.post("")
async def generate_dorks(req: DorkOnlyRequest):
    ds = dork_mod.generate(req.kind, req.value)
    return {
        "kind": req.kind,
        "value": req.value,
        "count": len(ds),
        "dorks": [
            {
                "label": d.label,
                "query": d.query,
                "google": d.google_url,
                "bing": d.bing_url,
                "duckduckgo": d.duckduckgo_url,
            }
            for d in ds
        ],
    }

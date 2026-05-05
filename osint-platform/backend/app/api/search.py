"""Search endpoints: one-shot POST and live SSE stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import IPRateLimiter
from app.database import SessionLocal, get_session
from app.models import SearchRecord
from app.osint.correlation import CorrelationEngine, SearchBundle
from app.osint.email_check import analyze_email
from app.osint.phone_check import analyze_phone
from app.schemas import SearchBundleRequest, SearchRequest, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])

_engine = CorrelationEngine()
_limiter = IPRateLimiter(max_requests=get_settings().rate_limit_per_minute)


def _client_ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else req.client.host) or "unknown"


async def _enrich(payload: dict, kind: str, value: str) -> dict:
    if kind == "email":
        rep = await analyze_email(value)
        payload["email_report"] = rep.__dict__
    elif kind == "phone":
        rep = analyze_phone(value)
        payload["phone_report"] = rep.__dict__
    return payload


async def _persist(result_payload: dict, kind: str, value: str) -> int:
    """Persist a finished search and return its DB id."""
    async with SessionLocal() as session:
        rec = SearchRecord(
            query_kind=kind,
            query_value=value,
            confidence=result_payload.get("confidence_score", 0),
            confidence_label=result_payload.get("confidence_label", "weak"),
            summary=result_payload.get("summary", {}),
            payload=result_payload,
        )
        session.add(rec)
        await session.commit()
        await session.refresh(rec)
        return rec.id


@router.post("", response_model=SearchResponse)
async def run_search(
    body: SearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    short_circuit_on_db_hit: bool = Query(
        False,
        description=(
            "When true and the local Elasticsearch DB returns ≥1 hit, the "
            "external OSINT pipeline (dorks/crawl/social/RDAP/image) is "
            "skipped entirely — the DB result is returned as the "
            "authoritative-and-final answer. Default false (always run both)."
        ),
    ),
):
    if not await _limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    result = await _engine.run(
        body.kind, body.value,
        short_circuit_on_db_hit=short_circuit_on_db_hit,
    )
    payload = result.to_dict()
    payload = await _enrich(payload, body.kind, body.value)

    record = SearchRecord(
        query_kind=result.query_kind,
        query_value=result.query_value,
        confidence=result.confidence_score,
        confidence_label=result.confidence_label,
        summary=result.summary,
        payload=payload,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    payload["id"] = record.id
    return payload


@router.post("/bundle", response_model=SearchResponse)
async def run_search_bundle(
    body: SearchBundleRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    short_circuit_on_db_hit: bool = Query(
        False,
        description=(
            "When true and the local Elasticsearch DB returns ≥1 hit, the "
            "external OSINT pipeline is skipped. Default false."
        ),
    ),
):
    """Multi-input identity resolution. Pass any subset of name/email/phone/username."""
    if not await _limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    bundle = SearchBundle(
        name=body.name or None,
        email=body.email or None,
        phone=body.phone or None,
        username=body.username or None,
    )
    if bundle.is_empty():
        raise HTTPException(status_code=422, detail="at least one field is required")

    result = await _engine.run_bundle(
        bundle,
        short_circuit_on_db_hit=short_circuit_on_db_hit,
    )
    payload = result.to_dict()
    if bundle.email:
        payload["email_report"] = (await analyze_email(bundle.email)).__dict__
    if bundle.phone:
        payload["phone_report"] = analyze_phone(bundle.phone).__dict__

    record = SearchRecord(
        query_kind=result.query_kind,
        query_value=result.query_value,
        confidence=result.confidence_score,
        confidence_label=result.confidence_label,
        summary=result.summary,
        payload=payload,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    payload["id"] = record.id
    return payload


@router.get("/stream")
async def run_search_stream(
    request: Request,
    kind: str = Query(..., regex="^(name|email|phone|username)$"),
    value: str = Query(..., min_length=1, max_length=256),
    short_circuit_on_db_hit: bool = Query(
        False,
        description=(
            "When true and the local Elasticsearch DB returns ≥1 hit, "
            "the external OSINT pipeline is skipped. Default false."
        ),
    ),
):
    """Server-Sent Events stream of correlation events.

    Emits a series of `event: stage|finding|snapshot|result` messages so
    the dashboard can render findings as they're discovered."""
    if not await _limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    queue: asyncio.Queue = asyncio.Queue()
    DONE = object()

    async def sink(event: dict) -> None:
        await queue.put(event)

    async def runner() -> None:
        try:
            result = await _engine.run(
                kind, value,
                event_sink=sink,
                short_circuit_on_db_hit=short_circuit_on_db_hit,
            )
            payload = result.to_dict()
            payload = await _enrich(payload, kind, value)
            try:
                payload["id"] = await _persist(payload, kind, value)
            except Exception:  # noqa: BLE001
                pass
            await queue.put({"type": "complete", "payload": payload})
        except Exception as e:  # noqa: BLE001
            await queue.put({"type": "error", "detail": str(e)})
        finally:
            await queue.put(DONE)

    async def event_gen():
        task = asyncio.create_task(runner())
        try:
            while True:
                if await request.is_disconnected():
                    task.cancel()
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is DONE:
                    break
                event_type = item.get("type", "message")
                data = json.dumps(item, default=str)
                yield f"event: {event_type}\ndata: {data}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

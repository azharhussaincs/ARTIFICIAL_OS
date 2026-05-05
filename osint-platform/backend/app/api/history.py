"""Endpoint: search history (list / get / delete)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import SearchRecord
from app.schemas import HistoryItem, HistoryList

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=HistoryList)
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    total = (await session.execute(select(func.count()).select_from(SearchRecord))).scalar_one()
    rows = (
        await session.execute(
            select(SearchRecord).order_by(SearchRecord.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return HistoryList(
        total=total,
        items=[
            HistoryItem(
                id=r.id,
                created_at=r.created_at,
                query_kind=r.query_kind,
                query_value=r.query_value,
                confidence=r.confidence,
                confidence_label=r.confidence_label,
                summary=r.summary,
            )
            for r in rows
        ],
    )


@router.get("/{record_id}")
async def get_record(record_id: int, session: AsyncSession = Depends(get_session)):
    r = (await session.execute(select(SearchRecord).where(SearchRecord.id == record_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="not found")
    return r.payload


@router.delete("/{record_id}")
async def delete_record(record_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(delete(SearchRecord).where(SearchRecord.id == record_id))
    await session.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": record_id}

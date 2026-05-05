"""SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SearchRecord(Base):
    __tablename__ = "search_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    query_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    query_value: Mapped[str] = mapped_column(String(512), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(16), default="weak", nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

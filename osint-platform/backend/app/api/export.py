"""Endpoint: export a stored search as CSV or PDF."""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import SearchRecord

router = APIRouter(prefix="/export", tags=["export"])


async def _load(record_id: int, session: AsyncSession) -> SearchRecord:
    r = (await session.execute(select(SearchRecord).where(SearchRecord.id == record_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="not found")
    return r


@router.get("/{record_id}/csv")
async def export_csv(record_id: int, session: AsyncSession = Depends(get_session)):
    r = await _load(record_id, session)
    payload: Dict[str, Any] = r.payload or {}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "key", "value"])
    w.writerow(["meta", "query_kind", r.query_kind])
    w.writerow(["meta", "query_value", r.query_value])
    w.writerow(["meta", "confidence", f"{r.confidence} ({r.confidence_label})"])

    for u in payload.get("related_usernames", []):
        w.writerow(["related_username", "", u])
    for e in payload.get("related_emails", []):
        w.writerow(["related_email", "", e])
    for p in payload.get("related_phones", []):
        w.writerow(["related_phone", "", p])
    for sp in payload.get("social_profiles", []):
        w.writerow(["social_profile", sp.get("platform", ""), sp.get("url", "")])
    for site in payload.get("websites", []):
        w.writerow(["website", site.get("title", ""), site.get("url", "")])
    for d in payload.get("dorks", []):
        w.writerow(["dork", d.get("label", ""), d.get("query", "")])

    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="osint-{record_id}.csv"'}
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers=headers)


@router.get("/{record_id}/pdf")
async def export_pdf(record_id: int, session: AsyncSession = Depends(get_session)):
    r = await _load(record_id, session)
    payload: Dict[str, Any] = r.payload or {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=f"OSINT Report #{record_id}")
    styles = getSampleStyleSheet()
    story: List[Any] = []

    story.append(Paragraph(f"OSINT Report — #{record_id}", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Query:</b> {r.query_kind} — <code>{r.query_value}</code>", styles["Normal"]))
    story.append(Paragraph(f"<b>Confidence:</b> {r.confidence} ({r.confidence_label})", styles["Normal"]))
    story.append(Paragraph(f"<b>Generated:</b> {r.created_at}", styles["Normal"]))
    story.append(Spacer(1, 12))

    def section(title: str, rows: List[List[str]]):
        if not rows:
            return
        story.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
        t = Table([["#", *([] if len(rows[0]) == 1 else [""])]] + rows, hAlign="LEFT", colWidths=[40, 460])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

    def numbered(items: List[str]) -> List[List[str]]:
        return [[str(i + 1), v] for i, v in enumerate(items)]

    section("Related Usernames", numbered(payload.get("related_usernames", [])))
    section("Related Emails", numbered(payload.get("related_emails", [])))
    section("Related Phones", numbered(payload.get("related_phones", [])))
    section(
        "Social Profiles",
        [[str(i + 1), f"{sp.get('platform','')}: {sp.get('url','')}"]
         for i, sp in enumerate(payload.get("social_profiles", []))],
    )
    section(
        "Public Websites",
        [[str(i + 1), f"{(s.get('title') or '')[:60]} — {s.get('url','')}"]
         for i, s in enumerate(payload.get("websites", []))],
    )
    section(
        "Dorks Generated",
        [[str(i + 1), d.get("query", "")] for i, d in enumerate(payload.get("dorks", []))],
    )

    doc.build(story)
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="osint-{record_id}.pdf"'}
    return StreamingResponse(buf, media_type="application/pdf", headers=headers)

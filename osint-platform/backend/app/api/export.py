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

    # Verified Local Database (Elasticsearch tc_index) — authoritative records.
    # Always emitted first so analysts see the trusted layer before unverified
    # OSINT signals. Reads from `payload["local_db"]["records"]` per the
    # dual-layer design; keys are UPPERCASE to mirror the index document shape.
    local_db = payload.get("local_db") or {}
    db_records = local_db.get("records") or []
    for rec in db_records:
        tags = rec.get("TAGS")
        if isinstance(tags, list):
            tags_str = ", ".join(t for t in tags if t)
        else:
            tags_str = (tags or "") if isinstance(tags, str) else ""
        w.writerow(["local_db", "name",     rec.get("NAME") or ""])
        w.writerow(["local_db", "phone",    rec.get("PHONE") or ""])
        w.writerow(["local_db", "email",    rec.get("EMAIL") or ""])
        w.writerow(["local_db", "tags",     tags_str])
        w.writerow(["local_db", "as_of",    rec.get("ASONDATE") or ""])
        w.writerow(["local_db", "matched",  f"{rec.get('matched_field') or ''} ({rec.get('match_reason') or ''})"])

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

    # ---- Verified Local Database (authoritative tc_index records) ----
    # Rendered FIRST so the trusted layer is visible before unverified OSINT
    # signals. Each record gets its own per-record table (Name / Phone / Email /
    # Tags / Date / Match) which is far more readable than a flat list.
    local_db = payload.get("local_db") or {}
    db_records = local_db.get("records") or []
    if db_records:
        story.append(Paragraph(
            f"<b>🟢 Verified Local Database (100% trust) — {len(db_records)} record(s)</b>",
            styles["Heading2"],
        ))
        story.append(Spacer(1, 6))
        for i, rec in enumerate(db_records, 1):
            tags_raw = rec.get("TAGS")
            if isinstance(tags_raw, list):
                tags = ", ".join(t for t in tags_raw if t) or "—"
            elif isinstance(tags_raw, str) and tags_raw.strip():
                tags = tags_raw.strip()
            else:
                tags = "—"
            date_str = (rec.get("ASONDATE") or "").split(" ")[0] or "—"
            match_str = rec.get("matched_field") or "—"
            reason = rec.get("match_reason") or rec.get("reason") or ""
            if reason:
                match_str = f"{match_str} ({reason})"
            data = [
                ["#", f"Record {i}"],
                ["Name",  rec.get("NAME")  or "—"],
                ["Phone", rec.get("PHONE") or "—"],
                ["Email", rec.get("EMAIL") or "—"],
                ["Tags",  tags],
                ["Date",  date_str],
                ["Match", match_str],
            ]
            t = Table(data, hAlign="LEFT", colWidths=[60, 440])
            t.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#16a34a")),
                ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
                ("BACKGROUND",  (0, 1), (0, -1), colors.HexColor("#f1f5f9")),
                ("TEXTCOLOR",   (0, 1), (0, -1), colors.HexColor("#475569")),
                ("LINEBEFORE",  (0, 0), (0, -1), 3, colors.HexColor("#22c55e")),
                ("GRID",        (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE",    (0, 0), (-1, -1), 9),
                ("VALIGN",      (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING",  (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))
        story.append(Spacer(1, 6))

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

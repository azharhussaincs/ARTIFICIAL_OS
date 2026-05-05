"""Pydantic schemas for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

QueryKind = Literal["name", "email", "phone", "username"]


class SearchRequest(BaseModel):
    kind: QueryKind
    value: str = Field(min_length=1, max_length=256)


class SearchBundleRequest(BaseModel):
    """Multi-input identity bundle. At least one field required."""
    name:     Optional[str] = Field(default=None, max_length=256)
    email:    Optional[str] = Field(default=None, max_length=256)
    phone:    Optional[str] = Field(default=None, max_length=64)
    username: Optional[str] = Field(default=None, max_length=64)


class DorkOnlyRequest(BaseModel):
    kind: QueryKind
    value: str = Field(min_length=1, max_length=256)


class TimelineEntryOut(BaseModel):
    timestamp: str
    stage: str
    detail: str


class SourceOut(BaseModel):
    url: str
    title: Optional[str] = None
    source_type: str
    # The Source dataclass in verification.py does not carry a weight,
    # so this is optional/default 0.0. Kept in the schema for forward
    # compatibility with weighted-evidence experiments.
    weight: float = 0.0
    extracted_at: str


class FindingOut(BaseModel):
    key: str
    type: str
    value: str
    confidence: int
    verified: bool
    label: str
    match_reasons: List[str]
    sources: List[SourceOut]
    related_to: List[str]
    first_seen: str
    last_seen: str


class SearchResponse(BaseModel):
    id: Optional[int] = None
    query_kind: QueryKind
    query_value: str
    started_at: str
    finished_at: Optional[str]
    summary: Dict[str, Any]
    findings: List[FindingOut]
    related_usernames: List[str]
    related_emails: List[str]
    related_phones: List[str]
    related_websites: List[str] = []
    related_domains: List[str] = []
    social_profiles: List[Dict[str, str]]
    websites: List[Dict[str, str]]
    dorks: List[Dict[str, str]]
    metadata_snippets: List[Dict[str, Any]]
    profile_snapshots: List[Dict[str, Any]] = []
    whois_records: List[Dict[str, Any]] = []
    image_clusters: List[Dict[str, Any]] = []
    evidence_ledger: List[Dict[str, Any]] = []
    # Dual-layer separation — these blocks are NEVER merged. The local DB
    # is the authoritative trusted source; external OSINT is supplementary.
    local_db: Dict[str, Any] = {}
    external_osint: Dict[str, Any] = {}
    final_summary: Dict[str, Any] = {}
    text_report: str = ""
    # v1 back-compat: flat list of ES hits (already part of `local_db.records`)
    elasticsearch_results: List[Dict[str, Any]] = []
    elasticsearch_summary: Dict[str, Any] = {}
    timeline: List[TimelineEntryOut]
    confidence_score: int
    confidence_label: str
    graph: Dict[str, Any]


class HistoryItem(BaseModel):
    id: int
    created_at: datetime
    query_kind: str
    query_value: str
    confidence: int
    confidence_label: str
    summary: Dict[str, Any]


class HistoryList(BaseModel):
    items: List[HistoryItem]
    total: int

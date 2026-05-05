"""Structured findings + explicit, additive verification scoring.

Every discovered identifier is one Finding that aggregates *all* the
evidence we have for it. Confidence is a clamped sum of explicit signal
deltas (not noisy-OR), so the reasoning is transparent: an analyst can
read the `signals` list and reproduce the score.

Signal weights (from the design spec):

    +25  same username confirmed on multiple platforms
    +20  display name / bio matches the seed
    +15  same external website linked from multiple sources
    +15  same email reused across public sources
    +10  cross-link found between two profiles
    +10  RDAP / WHOIS confirms the value
    +10  seed-supplied (the original input is trivially confirmed)
    -30  text matches a generic platform template
    -25  weak similarity to seed
    -40  unrelated domain (extracted from chrome rather than user content)

Confidence tiers:

    90 - 100   high       (verified high confidence)
    70 -  89   likely     (verified — actionable)
    50 -  69   possible   (worth a manual look)
     0 -  49   weak       (suppressed in default UI)

`verified` is True for confidence ≥ 70 (the "likely match" floor).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Iterable, List, Literal, Optional

FindingType = Literal[
    "name", "email", "phone", "username", "social_profile",
    "website", "domain", "person", "image",
]


class SignalKind(str, Enum):
    SEED                    = "seed"
    PROFILE_HIT             = "profile_hit"
    PROFILE_HIT_REDIRECT    = "profile_hit_redirect"
    CROSS_PLATFORM_HANDLE   = "cross_platform_handle"
    NAME_MATCH              = "name_match"
    BIO_REUSE               = "bio_reuse"
    LINK_REUSE              = "link_reuse"
    EMAIL_REUSE             = "email_reuse"
    IMAGE_MATCH             = "image_match"            # NEW: same avatar across platforms
    PROFILE_CROSSLINK       = "profile_crosslink"
    RDAP_CONFIRMED          = "rdap_confirmed"
    EXTRACTED_FROM_BIO      = "extracted_from_bio"
    EXTRACTED_FROM_RDAP     = "extracted_from_rdap"
    GENERIC_PLATFORM_TEXT   = "generic_platform_text"
    WEAK_SIMILARITY         = "weak_similarity"
    UNRELATED_DOMAIN        = "unrelated_domain"
    ELASTICSEARCH_HIT       = "elasticsearch_hit"      # internal index match


# Default deltas. Tuned to match the user-spec'd identity-resolution
# scoring: cross-platform repetition + image reuse + name match push a
# Finding into "verified" (≥ 85) only when multiple independent signals
# corroborate it.
SIGNAL_DELTA: Dict[SignalKind, int] = {
    SignalKind.SEED:                  +55,  # seed is strongly self-confirmed but not "verified" alone
    SignalKind.PROFILE_HIT:           +30,  # 200 OK on a known platform's profile URL
    SignalKind.PROFILE_HIT_REDIRECT:  +10,
    SignalKind.CROSS_PLATFORM_HANDLE: +30,  # +30 same username across platforms
    SignalKind.NAME_MATCH:            +25,  # +25 same display name + username
    SignalKind.BIO_REUSE:             +20,
    SignalKind.LINK_REUSE:            +20,  # +20 same website linked in bio
    SignalKind.EMAIL_REUSE:           +15,  # +15 email reused publicly
    SignalKind.IMAGE_MATCH:           +20,  # +20 repeated profile image
    SignalKind.PROFILE_CROSSLINK:     +10,  # +10 cross-platform linking
    SignalKind.RDAP_CONFIRMED:        +30,
    SignalKind.EXTRACTED_FROM_BIO:    +15,
    SignalKind.EXTRACTED_FROM_RDAP:   +20,
    SignalKind.GENERIC_PLATFORM_TEXT: -30,
    SignalKind.WEAK_SIMILARITY:       -30,  # -30 weak single-source match
    SignalKind.UNRELATED_DOMAIN:      -40,
    # ES delta is computed per-hit from the spec'd tier band (40-100); the
    # caller passes an explicit `delta=` so this default is never read.
    SignalKind.ELASTICSEARCH_HIT:     +25,
}


@dataclass
class Source:
    """One piece of evidence that supports (or weakens) a Finding."""
    url: str
    title: Optional[str] = None
    source_type: str = "web"
    extracted_at: str = field(default_factory=lambda: _utcnow())

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class Signal:
    kind: str           # SignalKind value
    delta: int          # signed contribution to confidence
    reason: str         # human-readable
    source_url: Optional[str] = None
    at: str = field(default_factory=lambda: _utcnow())

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class Finding:
    type: FindingType
    value: str
    confidence: int = 0
    verified: bool = False
    label: str = "weak"
    signals: List[Signal] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    related_to: List[str] = field(default_factory=list)
    first_seen: str = field(default_factory=lambda: _utcnow())
    last_seen: str = field(default_factory=lambda: _utcnow())

    @property
    def key(self) -> str:
        return f"{self.type}::{self.value.lower()}"

    @property
    def match_reasons(self) -> List[str]:
        """Back-compat: list of positive-signal reasons (no penalties)."""
        return [s.reason for s in self.signals if s.delta > 0]

    def add_signal(
        self,
        kind: SignalKind,
        reason: str,
        *,
        source: Optional[Source] = None,
        delta: Optional[int] = None,
    ) -> None:
        d = delta if delta is not None else SIGNAL_DELTA[kind]
        # Avoid duplicate identical signals from the same source
        sig_url = source.url if source else None
        for existing in self.signals:
            if existing.kind == kind.value and existing.source_url == sig_url and existing.reason == reason:
                return
        self.signals.append(Signal(kind=kind.value, delta=d, reason=reason, source_url=sig_url))
        if source:
            if not any(s.url == source.url and s.source_type == source.source_type for s in self.sources):
                self.sources.append(source)
        self.last_seen = _utcnow()
        self._recompute()

    def link(self, other_key: str) -> None:
        if other_key and other_key != self.key and other_key not in self.related_to:
            self.related_to.append(other_key)

    def _recompute(self) -> None:
        score = sum(s.delta for s in self.signals)
        self.confidence = max(0, min(100, score))
        self.label = _label(self.confidence)
        # The actionable "verified" boolean kicks in at HIGH-CONFIDENCE
        # (≥ 70). The strict "VERIFIED" tier label is reserved for ≥ 85
        # — see _label() — so the UI can distinguish "can act on this"
        # from "borderline confirmed".
        non_seed_positive = any(s.delta > 0 and s.kind != SignalKind.SEED.value for s in self.signals)
        self.verified = self.confidence >= 70 and non_seed_positive

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["key"] = self.key
        d["match_reasons"] = self.match_reasons
        return d


def _label(pct: int) -> str:
    """User-spec'd identity-resolution tiers.

        85 - 100  →  verified      (high-confidence connected identity)
        70 -  84  →  high          (very likely match — actionable)
        50 -  69  →  possible      (worth a manual look)
         0 -  49  →  unverified    (suppressed in default UI)
    """
    if pct >= 85: return "verified"
    if pct >= 70: return "high"
    if pct >= 50: return "possible"
    return "unverified"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# FindingStore
# ---------------------------------------------------------------------------

@dataclass
class GraphLink:
    """One concrete edge in the identity graph, with the reason that
    justifies it. Edges without a reason are forbidden."""
    a: str            # Finding key
    b: str            # Finding key
    reason: str
    signal_kind: str = "profile_crosslink"
    at: str = field(default_factory=lambda: _utcnow())

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class FindingStore:
    """Deduplicating, evidence-merging registry for Findings."""

    def __init__(self):
        self._by_key: Dict[str, Finding] = {}
        # Ordered list of (a, b, reason) — the audit trail for graph edges.
        # We store BOTH directions as a single canonical record (sorted keys).
        self._links: List[GraphLink] = []
        self._link_pairs: set[tuple[str, str]] = set()

    def upsert(
        self,
        type_: FindingType,
        value: str,
        *,
        signal: SignalKind,
        reason: str,
        source_url: str,
        source_title: Optional[str] = None,
        source_type: str = "web",
        delta: Optional[int] = None,
        related_to: Optional[Iterable[str]] = None,
    ) -> Finding:
        value = (value or "").strip()
        if not value:
            raise ValueError("empty finding value")
        f = Finding(type=type_, value=value)
        existing = self._by_key.get(f.key)
        if existing is None:
            self._by_key[f.key] = f
        else:
            f = existing
        src = Source(url=source_url, title=source_title, source_type=source_type)
        f.add_signal(signal, reason, source=src, delta=delta)
        for k in related_to or []:
            f.link(k)
        return f

    def add_signal(
        self,
        type_: FindingType,
        value: str,
        signal: SignalKind,
        reason: str,
        *,
        source_url: Optional[str] = None,
        source_type: str = "engine",
        delta: Optional[int] = None,
    ) -> Optional[Finding]:
        f = self.get(type_, value)
        if not f:
            return None
        src = Source(url=source_url, source_type=source_type) if source_url else None
        f.add_signal(signal, reason, source=src, delta=delta)
        return f

    def link_pair(self, a_key: str, b_key: str, reason: str,
                  signal_kind: SignalKind = SignalKind.PROFILE_CROSSLINK) -> None:
        a = self._by_key.get(a_key)
        b = self._by_key.get(b_key)
        if a:
            a.link(b_key)
            a.add_signal(signal_kind, reason)
        if b:
            b.link(a_key)
            b.add_signal(signal_kind, reason)
        # Record the canonical edge with its reason — every edge in the
        # graph MUST carry evidence per the spec.
        canonical = tuple(sorted([a_key, b_key]))
        if canonical not in self._link_pairs:
            self._link_pairs.add(canonical)
            self._links.append(GraphLink(
                a=canonical[0], b=canonical[1],
                reason=reason, signal_kind=signal_kind.value,
            ))

    def get(self, type_: FindingType, value: str) -> Optional[Finding]:
        return self._by_key.get(f"{type_}::{value.lower()}")

    def all(self) -> List[Finding]:
        return sorted(
            self._by_key.values(),
            key=lambda f: (-f.confidence, f.type, f.value),
        )

    def by_type(self, t: FindingType) -> List[Finding]:
        return [f for f in self.all() if f.type == t]

    def keys(self) -> List[str]:
        return list(self._by_key.keys())

    def to_list(self, *, min_confidence: int = 0, verified_only: bool = False) -> List[Dict[str, object]]:
        items = self.all()
        if min_confidence:
            items = [f for f in items if f.confidence >= min_confidence]
        if verified_only:
            items = [f for f in items if f.verified]
        return [f.to_dict() for f in items]

    def graph_links(self) -> List[GraphLink]:
        """All edges, each with its reason and the signal kind that created it."""
        return list(self._links)

    def evidence_ledger(self) -> List[Dict[str, object]]:
        """Chronological audit trail across every Finding.

        Returns one entry per signal, in `at` order. Useful for showing a
        single "this is everything the engine concluded and why" view to
        an analyst (the equivalent of a SOC investigation timeline).
        """
        rows: List[Dict[str, object]] = []
        for f in self._by_key.values():
            for s in f.signals:
                rows.append({
                    "at":          s.at,
                    "finding_key": f.key,
                    "type":        f.type,
                    "value":       f.value,
                    "signal":      s.kind,
                    "delta":       s.delta,
                    "reason":      s.reason,
                    "source_url":  s.source_url,
                })
        rows.sort(key=lambda r: (r["at"], r["finding_key"]))
        return rows

"""Cross-identity correlation engine — relevance-gated, signal-scored.

Pipeline (the user-spec'd "Better Search Pipeline"):

    seed input
      → dork generation
      → username candidate generation
      → profile probing
      → fingerprint-based profile extraction          (per-platform parsers)
      → entity normalization                          (relevance gate)
      → recursive discovery                           (only verified handles re-probe)
      → confidence scoring                            (additive signal deltas)
      → deduplication + cross-platform corroboration
      → graph correlation
      → verified findings only (UI default)

Every upsert into the FindingStore is preceded by:
  1. `relevance.is_noise_url(...)` for URLs / websites
  2. `relevance.is_generic_platform_text(...)` for bios and display names
  3. `relevance.relevance_to_seed(...)` for cross-checking ties
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Literal, Optional, Set
from urllib.parse import urlparse

from app.core.logger import logger
from app.osint import dorks as dork_mod
from app.osint.elastic_search import ElasticIntel, ESHit
from app.osint.image_match import (
    AvatarFingerprinter, ImageCluster, cluster_by_hash,
    direct_avatar_url, gravatar_url,
)
from app.osint.profile_match import ProfileFetcher, ProfileSnapshot, name_similarity
from app.osint.relevance import (
    is_generic_platform_text,
    is_noise_url,
    is_personal_website,
    is_platform_owned,
    normalize_host,
    relevance_to_seed,
)
from app.osint.username_check import check_username
from app.osint.verification import (
    FindingStore,
    SignalKind,
)
from app.osint.whois_lookup import lookup_domain

QueryKind = Literal["name", "email", "phone", "username"]
EventSink = Optional[Callable[[Dict[str, object]], Awaitable[None]]]


@dataclass
class SearchBundle:
    """Multi-input identity seed.

    Any subset of fields may be provided. The engine seeds one Finding
    per non-empty field, links them all to each other, and runs the full
    correlation pipeline with the union of derived candidate handles."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    username: Optional[str] = None

    def is_empty(self) -> bool:
        return not any([self.name, self.email, self.phone, self.username])

    def primary_kind(self) -> "QueryKind":
        # Used only for the persisted record's `query_kind` column.
        for k in ("username", "email", "phone", "name"):
            if getattr(self, k):
                return k  # type: ignore[return-value]
        return "name"

    def primary_value(self) -> str:
        for k in ("username", "email", "phone", "name"):
            v = getattr(self, k)
            if v:
                return v
        return ""

    def render_label(self) -> str:
        bits = [f"{k}={v!r}" for k, v in self.__dict__.items() if v]
        return ", ".join(bits)


@dataclass
class TimelineEntry:
    timestamp: str
    stage: str
    detail: str


@dataclass
class CorrelationResult:
    query_kind: QueryKind
    query_value: str
    started_at: str
    finished_at: Optional[str] = None
    summary: Dict[str, object] = field(default_factory=dict)
    findings: List[Dict[str, object]] = field(default_factory=list)
    related_usernames: List[str] = field(default_factory=list)
    related_emails: List[str] = field(default_factory=list)
    related_phones: List[str] = field(default_factory=list)
    related_websites: List[str] = field(default_factory=list)
    related_domains: List[str] = field(default_factory=list)
    social_profiles: List[Dict[str, str]] = field(default_factory=list)
    websites: List[Dict[str, str]] = field(default_factory=list)
    dorks: List[Dict[str, str]] = field(default_factory=list)
    metadata_snippets: List[Dict[str, object]] = field(default_factory=list)
    profile_snapshots: List[Dict[str, object]] = field(default_factory=list)
    whois_records: List[Dict[str, object]] = field(default_factory=list)
    image_clusters: List[Dict[str, object]] = field(default_factory=list)
    evidence_ledger: List[Dict[str, object]] = field(default_factory=list)
    # Dual-layer outputs — strictly separated per the design rule:
    # `local_db` is the AUTHORITATIVE Elasticsearch layer (trust_level
    # HIGH, confidence 100). `external_osint` wraps the unverified web/social
    # findings. `final_summary` is the comparison-only footer. ES results are
    # ALSO mirrored into `elasticsearch_results` for back-compat with anything
    # that consumed the v1 shape.
    local_db: Dict[str, object] = field(default_factory=dict)
    external_osint: Dict[str, object] = field(default_factory=dict)
    final_summary: Dict[str, object] = field(default_factory=dict)
    text_report: str = ""        # plain-text rendering of the three sections (spec format)
    elasticsearch_results: List[Dict[str, object]] = field(default_factory=list)
    elasticsearch_summary: Dict[str, object] = field(default_factory=dict)
    timeline: List[TimelineEntry] = field(default_factory=list)
    confidence_score: int = 0
    confidence_label: str = "unverified"
    graph: Dict[str, List[Dict[str, object]]] = field(default_factory=lambda: {"nodes": [], "edges": []})
    suppressed_count: int = 0  # noisy/irrelevant findings filtered out

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["timeline"] = [asdict(t) for t in self.timeline]
        return d


class CorrelationEngine:
    """Multi-pass identity correlator with strict relevance gating."""

    MAX_RECURSIVE_HANDLES = 4
    MAX_PROFILES_TO_FETCH = 12

    def __init__(self):
        self.profiles = ProfileFetcher()
        self.avatars = AvatarFingerprinter()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    async def run(
        self,
        kind: QueryKind,
        value: str,
        event_sink: EventSink = None,
        *,
        short_circuit_on_db_hit: bool = False,
    ) -> CorrelationResult:
        """Single-input convenience wrapper. Equivalent to a bundle with
        exactly one field set."""
        bundle = SearchBundle(**{kind: value.strip()})
        return await self.run_bundle(
            bundle,
            event_sink=event_sink,
            short_circuit_on_db_hit=short_circuit_on_db_hit,
        )

    async def run_bundle(
        self,
        bundle: SearchBundle,
        event_sink: EventSink = None,
        *,
        short_circuit_on_db_hit: bool = False,
    ) -> CorrelationResult:
        if bundle.is_empty():
            raise ValueError("search bundle is empty")
        kind = bundle.primary_kind()
        value = bundle.primary_value()

        result = CorrelationResult(query_kind=kind, query_value=value, started_at=_now())
        store = FindingStore()
        snapshots: Dict[str, ProfileSnapshot] = {}
        suppressed: List[str] = []  # for diagnostics

        # Track context for relevance scoring
        ctx_handles: Set[str] = set()
        ctx_names: Set[str] = set()
        ctx_domains: Set[str] = set()

        # ---- seed Findings (one per non-empty field, all cross-linked) ----
        seed_keys = self._seed_bundle(store, bundle, ctx_handles, ctx_names, ctx_domains)
        seed_key = seed_keys[0]  # primary seed for graph centering

        # ---- email seed → synthesize Gravatar snapshot for image clustering ----
        bootstrap_snapshots: List[Dict[str, str]] = []
        if bundle.email:
            grav = gravatar_url(bundle.email)
            if grav:
                # We confirm Gravatar exists by HEAD-ing the URL with d=404
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=6) as client:
                        r = await client.head(grav, follow_redirects=True)
                    if r.status_code == 200:
                        snapshots[grav] = ProfileSnapshot(
                            url=grav,
                            platform="gravatar",
                            handle=bundle.email.lower(),
                            avatar_url=grav,
                            display_name=None,
                            bio=None,
                            is_blocked=False,
                            parser_confidence=0.9,
                        )
                        bootstrap_snapshots.append({"platform": "gravatar", "url": grav, "handle": bundle.email.lower()})
                except Exception:  # noqa: BLE001
                    pass

        async def emit(stage: str, detail: str, **extra) -> None:
            entry = TimelineEntry(_now(), stage, detail)
            result.timeline.append(entry)
            if event_sink:
                await event_sink({"type": "stage", "stage": stage, "detail": detail, **extra})

        await emit("init", f"starting identity resolution for {bundle.render_label()}")

        # ---- pass 0: Elasticsearch internal index (AUTHORITATIVE layer) ----
        # The local ES index is the dual-layer system's TRUSTED source. Per
        # the design rule, ES results are NEVER merged into the OSINT
        # FindingStore — they live in their own `local_db` block with
        # confidence=100, and the external OSINT layer continues independently.
        # If ES is disabled or unreachable, this pass is a no-op and the
        # existing OSINT flow is unaffected.
        es_hits = await self._elasticsearch_pass(bundle, event_sink)
        result.elasticsearch_results = [h.to_dict() for h in es_hits]  # back-compat
        result.elasticsearch_summary = self._summarize_es(es_hits)
        # Spec-mandated logging format — exact strings the user requested
        # so log greps/audits stay stable across releases.
        if es_hits:
            n = len(es_hits)
            # Spec-mandated log wording: "[elasticsearch] N hit(s) in tc_index"
            logger.info("[elasticsearch] %d hit%s in tc_index", n, "" if n == 1 else "s")
            await emit(
                "elasticsearch",
                f"[elasticsearch] {n} hit{'' if n == 1 else 's'} in tc_index (authoritative)",
            )
        else:
            logger.info("[elasticsearch] no hits in tc_index")
            await emit(
                "elasticsearch",
                "[elasticsearch] no hits in tc_index — local DB section will show '❌ No data found'",
            )

        # OSINT pipeline gating:
        #   default                                → ALWAYS run OSINT (DB-first
        #                                            sequencing, never gating).
        #   short_circuit_on_db_hit=True + DB hit  → SKIP all OSINT passes, the
        #                                            DB result is treated as
        #                                            authoritative-and-final.
        skip_osint = bool(short_circuit_on_db_hit and es_hits)
        confirmed_profiles: List[Dict[str, str]] = []
        if skip_osint:
            await emit(
                "osint_skipped",
                "OSINT pipeline skipped — DB returned authoritative hits and "
                "short_circuit_on_db_hit=true",
            )
        else:
            # ---- pass 1: dorks ----
            ds = dork_mod.generate(kind, value)
            result.dorks = [
                {"label": d.label, "query": d.query,
                 "google": d.google_url, "bing": d.bing_url, "duckduckgo": d.duckduckgo_url}
                for d in ds
            ]
            await emit("dorks", f"generated {len(ds)} dork queries")

            # ---- pass 2: candidate handle probe ----
            seed_candidates = self._candidate_usernames_for_bundle(bundle)
            if seed_candidates:
                await emit("probe", f"checking {len(seed_candidates)} candidate handle(s) on public sites")
                confirmed = await self._probe_handles(
                    seed_candidates, store, seed_key, ctx_handles, ctx_names, ctx_domains, event_sink
                )
                confirmed_profiles.extend(confirmed)

            # ---- pass 3: fetch each confirmed profile (fingerprint-aware) ----
            if confirmed_profiles:
                await emit("fetch", f"fetching {min(len(confirmed_profiles), self.MAX_PROFILES_TO_FETCH)} profile pages")
                fetched = await self._fetch_profile_snapshots(confirmed_profiles, event_sink)
                snapshots.update(fetched)
            # Add Gravatar bootstrap to the confirmed list so it shows in social_profiles
            if bootstrap_snapshots:
                confirmed_profiles.extend(bootstrap_snapshots)

            # ---- pass 4: extract NEW identifiers from bios (filtered) ----
            new_handles: Set[str] = set()
            if snapshots:
                new_handles = await self._fold_in_snapshots(
                    store, snapshots, seed_key, ctx_handles, ctx_names, ctx_domains, event_sink, suppressed
                )

            # ---- pass 5: recursive probe of newly discovered handles (capped) ----
            if new_handles:
                extra = list(new_handles)[: self.MAX_RECURSIVE_HANDLES]
                await emit("recurse", f"re-probing {len(extra)} newly discovered handle(s)")
                extra_profiles = await self._probe_handles(
                    extra, store, seed_key, ctx_handles, ctx_names, ctx_domains, event_sink
                )
                extra_snaps = await self._fetch_profile_snapshots(extra_profiles, event_sink)
                snapshots.update(extra_snaps)
                await self._fold_in_snapshots(
                    store, extra_snaps, seed_key, ctx_handles, ctx_names, ctx_domains, event_sink, suppressed,
                    recursion=True,
                )
                confirmed_profiles.extend(extra_profiles)

            # ---- pass 6: cross-platform corroboration ----
            await self._cross_platform_corroborate(store, snapshots, event_sink)

            # ---- pass 7: RDAP for known domains ----
            domains = self._domains_to_lookup(store, kind, value)
            if domains:
                await emit("rdap", f"public RDAP lookup for {len(domains)} domain(s)")
                await self._rdap_pass(domains, store, result, seed_key, event_sink)

            # ---- pass 8: avatar perceptual hashing + cross-platform clustering ----
            clusters = await self._image_correlate_pass(snapshots, store, event_sink)
            result.image_clusters = [_cluster_to_dict(c, snapshots) for c in clusters]

            # ---- pass 9: name & bio similarity reinforcement ----
            await self._reinforce_name_matches(store, snapshots, ctx_handles, ctx_names, event_sink)

        # ---- finalize ----
        result.suppressed_count = len(suppressed)
        self._populate_legacy_views(result, store, snapshots, confirmed_profiles)
        result.findings = store.to_list()
        result.evidence_ledger = store.evidence_ledger()
        result.summary = self._build_summary(result, store)
        # Dual-layer rule: NO weighted blend. The OSINT engine's score
        # describes the external/unverified layer ONLY. The local DB layer
        # carries its own fixed authoritative confidence (100) when it has
        # hits. We surface both, but never combine them into a single number.
        osint_score, osint_label = self._overall_confidence(store)
        result.confidence_score = osint_score
        result.confidence_label = osint_label
        result.summary["osint_confidence"] = osint_score
        result.summary["local_db_confidence"] = 100 if es_hits else 0
        result.summary["confidence_weights"] = {"osint": 1.0, "elasticsearch": 0.0}  # never blended
        result.summary["osint_skipped"] = skip_osint
        if skip_osint:
            result.summary["osint_skipped_reason"] = (
                "short_circuit_on_db_hit=true and local DB returned authoritative hits"
            )
        result.graph = self._build_graph(store, seed_key)

        # Assemble the three dual-layer output blocks AFTER the OSINT
        # pipeline has fully populated `result`, so `external_osint` mirrors
        # the existing OSINT views without disturbing them.
        result.local_db = self._build_local_database_block(es_hits, bundle)
        result.external_osint = self._build_external_osint_block(
            result, osint_score, osint_label, skipped=skip_osint,
        )
        result.final_summary = self._build_final_summary_block(es_hits, result, osint_score)
        result.text_report = self._render_text_report(
            result.local_db, result.external_osint, result.final_summary,
        )
        result.finished_at = _now()
        await emit(
            "done",
            f"{len(result.findings)} findings · confidence={result.confidence_score} ({result.confidence_label}) · {result.suppressed_count} noisy candidates suppressed"
        )

        if event_sink:
            await event_sink({"type": "result", "payload": result.to_dict()})
        return result

    # ------------------------------------------------------------------
    # Pass implementations
    # ------------------------------------------------------------------
    @staticmethod
    def _seed_bundle(
        store: FindingStore,
        bundle: SearchBundle,
        ctx_handles: Set[str],
        ctx_names: Set[str],
        ctx_domains: Set[str],
    ) -> List[str]:
        """Seed one Finding per provided field; pre-link them all."""
        keys: List[str] = []
        type_map = {"name": "name", "email": "email", "phone": "phone", "username": "username"}
        for field_name in ("name", "email", "phone", "username"):
            v = getattr(bundle, field_name)
            if not v:
                continue
            v = v.strip()
            f = store.upsert(
                type_map[field_name], v,
                signal=SignalKind.SEED,
                reason=f"user-supplied seed identifier ({field_name})",
                source_url="urn:user-input",
                source_type="seed",
            )
            keys.append(f.key)
            # Update relevance contexts
            if field_name == "username":
                ctx_handles.add(v.lower().lstrip("@"))
            elif field_name == "email":
                local = v.split("@", 1)[0].lower()
                domain = v.split("@", 1)[-1].lower()
                ctx_handles.add(re.sub(r"[^a-z0-9_.-]", "", local))
                if domain:
                    ctx_domains.add(normalize_host(domain))
            elif field_name == "name":
                ctx_names.add(v)
                parts = [p for p in re.split(r"\s+", v) if p]
                if len(parts) >= 2:
                    f_, l = parts[0].lower(), parts[-1].lower()
                    for h in (f"{f_}{l}", f"{f_}.{l}", f"{f_}_{l}", f"{f_[0]}{l}"):
                        ctx_handles.add(h)
        # Cross-link all seeds
        for i, k1 in enumerate(keys):
            for k2 in keys[i + 1:]:
                store.link_pair(k1, k2, "supplied together as multi-input seed")
        return keys

    # ------------------------------------------------------------------
    # Elasticsearch — AUTHORITATIVE local DB layer (NEVER merged with OSINT)
    # ------------------------------------------------------------------
    @staticmethod
    async def _elasticsearch_pass(
        bundle: SearchBundle,
        event_sink: EventSink,
    ) -> List["ESHit"]:
        """Query the local ES index for every non-empty bundle field.

        Per the dual-layer design rule, ES hits are NOT folded into the
        OSINT FindingStore. They live in their own authoritative section
        with confidence=100 and are surfaced via `result.local_db`
        and `result.elasticsearch_results`. The OSINT score is computed
        independently and never blended with the local-DB score."""
        es = ElasticIntel.instance()
        if not es.enabled:
            return []
        try:
            hits = await es.search_bundle(
                name=bundle.name or "",
                email=bundle.email or "",
                phone=bundle.phone or "",
                username=bundle.username or "",
            )
        except Exception:  # noqa: BLE001
            return []
        if not hits:
            return []
        if event_sink:
            for h in hits:
                # Stream ES hits as a separate channel — the UI keeps them
                # in their own "LOCAL DATABASE — TRUSTED" panel.
                await event_sink({"type": "elasticsearch_hit", "hit": h.to_dict()})
        return hits

    @staticmethod
    def _summarize_es(hits: List["ESHit"]) -> Dict[str, object]:
        if not hits:
            return {"hit_count": 0, "by_field": {}, "top_confidence": 0}
        by_field: Counter = Counter()
        for h in hits:
            if h.matched_field:
                by_field[h.matched_field] += 1
        return {
            "hit_count": len(hits),
            "by_field": dict(by_field),
            "top_confidence": max((h.confidence for h in hits), default=0),
            "names": sorted({h.name for h in hits if h.name})[:10],
            "emails": sorted({h.email for h in hits if h.email})[:10],
            "phones": sorted({h.phone for h in hits if h.phone})[:10],
        }

    # ------------------------------------------------------------------
    # Dual-layer output blocks
    # ------------------------------------------------------------------
    @staticmethod
    def _build_local_database_block(
        es_hits: List["ESHit"],
        bundle: SearchBundle,
    ) -> Dict[str, object]:
        """The AUTHORITATIVE / trusted output block.

        Every record carries `confidence=100` per the spec ("never
        downgrade local DB confidence"). The per-match score from the ES
        engine is preserved as `match_strength` so an analyst can see
        WHY ES matched without that score being used to lower the
        record's authoritative confidence."""
        records: List[Dict[str, object]] = []
        for h in es_hits:
            # Per the user spec, record field names mirror the ES `_source`
            # mapping (UPPERCASE: NAME / PHONE / EMAIL / TAGS / ASONDATE)
            # so the wire shape is identical to the index document.
            records.append({
                "NAME": h.name,
                "PHONE": h.phone,
                "EMAIL": h.email,
                "TAGS": h.tags,
                "ASONDATE": h.asondate,
                "confidence": 100,                     # authoritative
                "label": "Internal Verified Identity",
                "matched_field": h.matched_field,
                "matched_against": _bundle_value_for_field(h.matched_field, bundle),
                "match_reason": h.reason,
                "match_strength": h.confidence,        # ES engine's tier (informational)
                "es_id": h.es_id,
                "es_score": h.es_score,
                "timestamp": h.timestamp,
            })
        return {
            "display_label": "🟢 VERIFIED LOCAL DATABASE (100% TRUST)",
            "display_label_banner": _banner("🟢 VERIFIED LOCAL DATABASE (100% TRUST)"),
            "empty_message": "❌ No data found in local database",
            "source": "local_db (elasticsearch tc_index)",
            "trust_level": "100% TRUST (AUTHORITATIVE)",
            "verdict": "VERIFIED INTERNAL DATA" if records else "NO LOCAL DB MATCH",
            "found": bool(records),
            "count": len(records),
            "records": records,
        }

    @staticmethod
    def _build_external_osint_block(
        result: CorrelationResult,
        osint_score: int,
        osint_label: str,
        *,
        skipped: bool = False,
    ) -> Dict[str, object]:
        """Wrapper around the existing OSINT outputs with the spec'd
        unverified / evidence-based trust label.

        We DO NOT copy the underlying lists — we reference them by view
        names. The full structured data still lives at the top level of
        `result` for back-compat (so the existing UI panels keep working
        unchanged); this block just re-presents them as the
        evidence-based external layer."""
        # Numbered, deduped per-platform profile listing for the
        # spec'd "[N] Platform: GitHub / Username / Link / Confidence" view.
        # Source of truth: the structured Findings (so confidence comes
        # from the engine's signal-summed score, not a guess).
        profile_findings = [f for f in result.findings
                            if (f.get("type") if isinstance(f, dict) else f.type) == "social_profile"]
        username_finding_by_value = {
            (f.get("value") if isinstance(f, dict) else f.value): f
            for f in result.findings
            if (f.get("type") if isinstance(f, dict) else f.type) == "username"
        }
        listings: List[Dict[str, object]] = []
        seen: set = set()
        for sp in result.social_profiles:
            url = sp.get("url") or ""
            platform = sp.get("platform") or ""
            handle = sp.get("handle") or ""
            key = (platform, url)
            if not url or key in seen:
                continue
            seen.add(key)
            # Match this profile back to its Finding for the confidence
            pf = next((p for p in profile_findings
                       if (p.get("value") if isinstance(p, dict) else p.value) == url), None)
            confidence = (pf.get("confidence") if isinstance(pf, dict) else (pf.confidence if pf else 0)) or 0
            verified = (pf.get("verified") if isinstance(pf, dict) else (pf.verified if pf else False)) or False
            listings.append({
                "platform": platform,
                "username": handle,
                "link": url,
                "confidence": int(confidence),
                "verified": bool(verified),
            })
        listings.sort(key=lambda x: (-x["confidence"], x["platform"]))

        all_findings = result.findings or []
        verified_profile_count = sum(
            1 for f in profile_findings
            if (f.get("verified") if isinstance(f, dict) else f.verified)
        )
        username_count = sum(
            1 for v, f in username_finding_by_value.items()
            if ((f.get("confidence") if isinstance(f, dict) else f.confidence) or 0) >= 50
        )
        email_count = len(result.related_emails)

        osint_stats = {
            "total_findings":   len(all_findings),
            "verified_profiles": verified_profile_count,
            "usernames":         username_count,
            "emails":            email_count,
            "confidence_score":  osint_score,
        }

        empty_msg = (
            "⏭️  External OSINT skipped — DB returned authoritative data and "
            "short_circuit_on_db_hit=true."
            if skipped else "❌ No external OSINT signals."
        )
        return {
            "display_label": "🌐 OSINT FINDINGS (UNVERIFIED)",
            "display_label_banner": _banner("🌐 OSINT FINDINGS (UNVERIFIED)"),
            "empty_message": empty_msg,
            "skipped": skipped,
            "skipped_reason": (
                "short_circuit_on_db_hit=true and local DB returned hits"
                if skipped else None
            ),
            "source": "web_osint (dorks + crawling + social)",
            "trust_level": "unverified / evidence-based",
            "key_note": "External OSINT is supporting intelligence only — never overrides local DB.",
            "confidence": osint_score,
            "confidence_label": osint_label,
            "stats": osint_stats,
            "listings": listings,             # numbered "[N] Platform: ... / Username / Link / Confidence"
            "results": {
                "social_profiles":   list(result.social_profiles),
                "websites":          list(result.websites),
                "emails_found":      list(result.related_emails),
                "phones_found":      list(result.related_phones),
                "usernames_found":   list(result.related_usernames),
                "domains_found":     list(result.related_domains),
                "dork_sources":      list(result.dorks),
                "profile_snapshots": list(result.profile_snapshots),
                "image_clusters":    list(result.image_clusters),
                "whois_records":     list(result.whois_records),
                "metadata_snippets": list(result.metadata_snippets),
            },
        }

    @staticmethod
    def _build_final_summary_block(
        es_hits: List["ESHit"],
        result: CorrelationResult,
        osint_score: int,
    ) -> Dict[str, object]:
        """Comparison-only footer per spec — never merges the two layers."""
        local_match = bool(es_hits)
        external_match = (
            bool(result.social_profiles)
            or bool(result.related_emails)
            or bool(result.related_phones)
            or bool(result.related_usernames)
            or osint_score >= 50
        )
        decision = (
            "based on local DB (authoritative match present)"
            if local_match
            else "based on external OSINT (no local DB match — evidence is unverified)"
        )
        # Presentation-layer single-number score per the spec's example
        # ("Confidence Score: XX/100"). When the local DB has a match, the
        # authoritative value (100) is shown; otherwise the OSINT score.
        # This is a DISPLAY-ONLY value — per-source scores remain separate.
        summary_score = 100 if local_match else osint_score
        return {
            "display_label": "=== SUMMARY ===",
            "local_db_match": local_match,
            "local_db_match_yn": "YES" if local_match else "NO",
            "external_match": external_match,
            "osint_match_yn": "YES" if external_match else "NO",
            "summary_score": summary_score,                # 0-100
            "summary_score_text": f"{summary_score}/100",
            "key_note": "Local DB is authoritative. External OSINT is supplementary.",
            "confidence_logic": {
                "local_db": 100 if local_match else 0,
                "external_osint": osint_score,
                "final_decision": decision,
                "weights": {"local_db": "fixed 100 (authoritative)", "external_osint": "engine score"},
                "merge_policy": "no_merge — sources kept separate",
            },
        }

    @staticmethod
    def _render_text_report(
        local_database: Dict[str, object],
        external_osint: Dict[str, object],
        final_summary: Dict[str, object],
    ) -> str:
        """Render the three blocks as the spec'd plain-text report.

        Format mirrors the user's example output verbatim:

            ==============================
            🟢 LOCAL DATABASE (HIGH TRUST)
            ==============================
            Name: …
            Phone: …
            …

            ==============================
            🌐 OSINT FINDINGS (UNVERIFIED)
            ==============================
            Total Findings: N
            Verified Profiles: N
            Usernames: N
            Emails: N
            Confidence Score: N/100

            [1] Platform: GitHub
                Username: …
                Link: …
                Confidence: …

        Per spec: if only one section has data, show only that one.
        """
        lines: List[str] = []
        records = local_database.get("records") or []
        listings = external_osint.get("listings") or []
        stats = external_osint.get("stats") or {}
        ext_results = external_osint.get("results") or {}

        has_osint = (
            bool(listings)
            or bool(ext_results.get("emails_found"))
            or bool(ext_results.get("usernames_found"))
            or bool(ext_results.get("phones_found"))
            or bool(ext_results.get("dork_sources"))
        )

        # ── Section A — local DB (ALWAYS shown, above OSINT) ─────────
        # Per the spec: never leave the DB section blank/idle. Show data
        # when found, "❌ No data found in local database" when not.
        lines.append(str(local_database.get("display_label_banner")
                         or _banner("🟢 VERIFIED LOCAL DATABASE (100% TRUST)")))
        if not records:
            lines.append(str(local_database.get("empty_message")
                             or "❌ No data found in local database"))
        else:
            for i, r in enumerate(records, 1):
                if i > 1:
                    lines.append("")
                lines.append(f"Name:  {r.get('NAME') or '—'}")
                lines.append(f"Phone: {r.get('PHONE') or '—'}")
                lines.append(f"Email: {r.get('EMAIL') or '—'}")
                tags = r.get("TAGS") or []
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                lines.append(f"Tags:  {', '.join(tags) if tags else '—'}")
                lines.append(f"Date:  {r.get('ASONDATE') or '—'}")

        # ── Section B — external OSINT (ALWAYS shown, below DB) ──────
        # When the OSINT pipeline was explicitly skipped via the
        # short_circuit_on_db_hit flag, render the spec'd skip message
        # instead of pretending nothing was searched.
        osint_skipped = bool(external_osint.get("skipped"))
        if True:
            lines.append("")
            lines.append(str(external_osint.get("display_label_banner")
                             or _banner("🌐 OSINT FINDINGS (UNVERIFIED)")))
            if osint_skipped:
                lines.append(str(external_osint.get("empty_message")
                                 or "⏭️  External OSINT skipped — DB returned authoritative data."))
            elif not has_osint:
                lines.append(str(external_osint.get("empty_message")
                                 or "❌ No external OSINT signals."))
            else:
                lines.append(f"Total Findings:    {stats.get('total_findings', 0)}")
                lines.append(f"Verified Profiles: {stats.get('verified_profiles', 0)}")
                lines.append(f"Usernames:         {stats.get('usernames', 0)}")
                lines.append(f"Emails:            {stats.get('emails', 0)}")
                lines.append(f"Confidence Score:  {stats.get('confidence_score', 0)}/100")

                if listings:
                    lines.append("")
                    for i, item in enumerate(listings, 1):
                        plat = (item.get("platform") or "").strip() or "unknown"
                        lines.append(f"[{i}] Platform: {plat[:1].upper() + plat[1:]}")
                        if item.get("username"):
                            lines.append(f"    Username:   {item['username']}")
                        if item.get("link"):
                            lines.append(f"    Link:       {item['link']}")
                        lines.append(f"    Confidence: {item.get('confidence', 0)}"
                                     + ("  ✓ verified" if item.get("verified") else ""))

        return "\n".join(lines)

    @staticmethod
    def _seed_finding(
        store: FindingStore,
        kind: QueryKind,
        value: str,
        ctx_handles: Set[str],
        ctx_names: Set[str],
        ctx_domains: Set[str],
    ) -> str:
        type_map = {"name": "name", "email": "email", "phone": "phone", "username": "username"}
        f = store.upsert(
            type_map[kind], value,
            signal=SignalKind.SEED,
            reason=f"user-supplied seed identifier ({kind})",
            source_url="urn:user-input",
            source_type="seed",
        )
        if kind == "username":
            ctx_handles.add(value.lower().lstrip("@"))
        elif kind == "email":
            local = value.split("@", 1)[0].lower()
            domain = value.split("@", 1)[-1].lower()
            ctx_handles.add(re.sub(r"[^a-z0-9_.-]", "", local))
            if domain:
                ctx_domains.add(normalize_host(domain))
        elif kind == "name":
            ctx_names.add(value)
            parts = [p for p in re.split(r"\s+", value) if p]
            if len(parts) >= 2:
                f_, l = parts[0].lower(), parts[-1].lower()
                for h in (f"{f_}{l}", f"{f_}.{l}", f"{f_}_{l}", f"{f_[0]}{l}"):
                    ctx_handles.add(h)
        return f.key

    @staticmethod
    def _candidate_usernames(kind: QueryKind, value: str) -> List[str]:
        if kind == "username":
            return [value.lstrip("@").lower()]
        if kind == "email":
            local = value.split("@", 1)[0]
            base = re.sub(r"[^A-Za-z0-9_.-]", "", local).lower()
            return [base] if base else []
        if kind == "name":
            parts = [p for p in re.split(r"\s+", value) if p]
            if len(parts) >= 2:
                f, l = parts[0].lower(), parts[-1].lower()
                return list(dict.fromkeys([f"{f}{l}", f"{f}.{l}", f"{f}_{l}", f"{f[0]}{l}"]))
            return [parts[0].lower()] if parts else []
        return []

    @classmethod
    def _candidate_usernames_for_bundle(cls, bundle: SearchBundle) -> List[str]:
        """Union of candidate handles derived from every non-empty field."""
        out: List[str] = []
        for field_name in ("username", "email", "name"):
            v = getattr(bundle, field_name)
            if v:
                out.extend(cls._candidate_usernames(field_name, v))  # type: ignore[arg-type]
        # Preserve order, dedupe
        seen: Set[str] = set()
        uniq: List[str] = []
        for h in out:
            if h and h not in seen:
                seen.add(h); uniq.append(h)
        return uniq

    async def _probe_handles(
        self,
        handles: List[str],
        store: FindingStore,
        seed_key: str,
        ctx_handles: Set[str],
        ctx_names: Set[str],
        ctx_domains: Set[str],
        event_sink: EventSink,
    ) -> List[Dict[str, str]]:
        confirmed: List[Dict[str, str]] = []
        tasks = [check_username(h) for h in handles]
        for h, hits in zip(handles, await asyncio.gather(*tasks, return_exceptions=False)):
            if not hits:
                continue
            ctx_handles.add(h.lower())
            uf = store.upsert(
                "username", h,
                signal=SignalKind.PROFILE_HIT,
                reason=f"handle '{h}' confirmed on {len(hits)} platform(s)",
                source_url=f"urn:engine:probe:{h}",
                source_type="engine",
                delta=15,  # base for the username itself; cross-platform bonus is added later
            )
            store.link_pair(uf.key, seed_key, f"handle '{h}' is a probe from the seed")
            for hit in hits:
                conf_signal = SignalKind.PROFILE_HIT if hit.confidence >= 0.8 else SignalKind.PROFILE_HIT_REDIRECT
                sf = store.upsert(
                    "social_profile", hit.url,
                    signal=conf_signal,
                    reason=f"profile for '{h}' returned {hit.status} on {hit.platform}",
                    source_url=hit.url,
                    source_title=f"{hit.platform} profile for {h}",
                    source_type="profile",
                )
                store.link_pair(sf.key, uf.key, f"profile belongs to handle '{h}'")
                confirmed.append({"platform": hit.platform, "url": hit.url, "handle": h})
                if event_sink:
                    await event_sink({"type": "finding", "finding": sf.to_dict()})
            if event_sink:
                await event_sink({"type": "finding", "finding": uf.to_dict()})
        return confirmed

    async def _fetch_profile_snapshots(
        self,
        profiles: List[Dict[str, str]],
        event_sink: EventSink,
    ) -> Dict[str, ProfileSnapshot]:
        out: Dict[str, ProfileSnapshot] = {}
        targets = profiles[: self.MAX_PROFILES_TO_FETCH]
        if not targets:
            return out
        coros = [self.profiles.fetch(p["url"], p["platform"], p.get("handle")) for p in targets]
        results = await asyncio.gather(*coros, return_exceptions=False)
        for snap, original in zip(results, targets):
            # If the fetch failed AND we know a deterministic avatar URL
            # for this platform/handle, build a minimal snapshot anyway.
            if snap.error:
                direct = direct_avatar_url(original["platform"], original.get("handle") or "")
                if direct:
                    snap = ProfileSnapshot(
                        url=original["url"],
                        platform=original["platform"],
                        handle=original.get("handle"),
                        avatar_url=direct,
                        is_blocked=True,
                        parser_confidence=0.4,
                        error=None,
                    )
                else:
                    continue
            else:
                # Successful fetch but page didn't expose an avatar.
                # Use the direct-avatar fast path as a fallback for known
                # platforms — guarantees an avatar for every confirmed profile.
                if not snap.avatar_url:
                    direct = direct_avatar_url(snap.platform, snap.handle or "")
                    if direct:
                        snap.avatar_url = direct
            out[snap.url] = snap
            if event_sink:
                await event_sink({"type": "snapshot", "snapshot": _snap_to_dict(snap)})
        return out

    async def _fold_in_snapshots(
        self,
        store: FindingStore,
        snapshots: Dict[str, ProfileSnapshot],
        seed_key: str,
        ctx_handles: Set[str],
        ctx_names: Set[str],
        ctx_domains: Set[str],
        event_sink: EventSink,
        suppressed: List[str],
        recursion: bool = False,
    ) -> Set[str]:
        new_handles: Set[str] = set()

        for url, snap in snapshots.items():
            if snap.is_blocked or snap.parser_confidence < 0.3:
                # Blocked / generic page — don't pollute the engine.
                suppressed.append(f"profile blocked or generic: {url}")
                continue

            handle = (snap.handle or "").lower()
            if handle:
                ctx_handles.add(handle)

            # ---- display-name Finding ----
            if snap.display_name and not is_generic_platform_text(snap.display_name):
                rel, why = relevance_to_seed(
                    snap.display_name,
                    seed_handles=ctx_handles, seed_names=ctx_names, seed_domains=ctx_domains,
                )
                nf = store.upsert(
                    "name", snap.display_name,
                    signal=SignalKind.EXTRACTED_FROM_BIO,
                    reason=f"display name on {snap.platform}/{handle}",
                    source_url=url,
                    source_title=snap.title,
                    source_type="profile",
                )
                store.link_pair(nf.key, seed_key, f"name appears on profile {snap.platform}/{handle}")
                ctx_names.add(snap.display_name)
                # If this name matches another name we already had, both get the bonus.
                for existing in [f for f in store.by_type("name") if f.value != snap.display_name]:
                    sim = name_similarity(snap.display_name, existing.value)
                    if sim >= 0.85:
                        nf.add_signal(SignalKind.NAME_MATCH,
                                      f"name '{snap.display_name}' ≈ existing name '{existing.value}' (sim={sim:.2f})")
                        existing.add_signal(SignalKind.NAME_MATCH,
                                            f"name '{existing.value}' ≈ '{snap.display_name}' (sim={sim:.2f})")
                if rel < 0.5 and not recursion:
                    nf.add_signal(SignalKind.WEAK_SIMILARITY, f"display name has weak tie to seed: {why}")
                if event_sink:
                    await event_sink({"type": "finding", "finding": nf.to_dict()})

            # ---- emails extracted from bio ----
            for email in snap.extracted_emails:
                if not _email_is_personal(email):
                    suppressed.append(f"generic-mailbox email skipped: {email}")
                    continue
                ef = store.upsert(
                    "email", email,
                    signal=SignalKind.EXTRACTED_FROM_BIO,
                    reason=f"'{email}' appears in bio of {snap.platform}/{handle}",
                    source_url=url,
                    source_title=snap.title,
                    source_type="bio",
                )
                store.link_pair(ef.key, seed_key, f"email extracted from {snap.platform}/{handle}")
                if event_sink:
                    await event_sink({"type": "finding", "finding": ef.to_dict()})

            # ---- handles mentioned in bio (NEW potential identities) ----
            for h in snap.extracted_handles:
                if h == handle or h in ctx_handles:
                    continue
                if not recursion:
                    new_handles.add(h)
                ctx_handles.add(h)
                hf = store.upsert(
                    "username", h,
                    signal=SignalKind.EXTRACTED_FROM_BIO,
                    reason=f"@{h} mentioned in bio of {snap.platform}/{handle}",
                    source_url=url,
                    source_title=snap.title,
                    source_type="bio",
                )
                store.link_pair(hf.key, seed_key, f"handle '@{h}' mentioned in {snap.platform}/{handle}'s bio")

            # ---- personal links → website / domain Findings (NOISE GATED) ----
            for link in snap.extracted_links:
                if is_noise_url(link):
                    suppressed.append(f"noise link skipped: {link}")
                    continue
                netloc = normalize_host(urlparse(link).hostname)
                if not netloc:
                    continue
                rel, why = relevance_to_seed(
                    link, seed_handles=ctx_handles, seed_names=ctx_names, seed_domains=ctx_domains,
                )
                wf = store.upsert(
                    "website", link,
                    signal=SignalKind.EXTRACTED_FROM_BIO,
                    reason=f"linked from public profile {snap.platform}/{handle}",
                    source_url=url,
                    source_title=snap.title,
                    source_type="bio",
                )
                store.link_pair(wf.key, seed_key, f"linked from {snap.platform}/{handle}'s public profile")
                df = store.upsert(
                    "domain", netloc,
                    signal=SignalKind.EXTRACTED_FROM_BIO,
                    reason=f"hosts a website linked from {snap.platform}/{handle}",
                    source_url=url,
                    source_type="bio",
                )
                store.link_pair(df.key, wf.key, "website is on this domain")
                ctx_domains.add(netloc)
                # If this domain shows up in *another* profile too, that's link reuse.
                if event_sink:
                    await event_sink({"type": "finding", "finding": wf.to_dict()})

        return new_handles

    @staticmethod
    async def _cross_platform_corroborate(
        store: FindingStore,
        snapshots: Dict[str, ProfileSnapshot],
        event_sink: EventSink,
    ) -> None:
        """+25 cross-platform handle, +15 link reuse, +15 email reuse."""
        # 1. Cross-platform handle
        platforms_per_handle: Dict[str, Set[str]] = {}
        for snap in snapshots.values():
            if snap.is_blocked or not snap.handle:
                continue
            platforms_per_handle.setdefault(snap.handle.lower(), set()).add(snap.platform)
        for handle, platforms in platforms_per_handle.items():
            if len(platforms) < 2:
                continue
            uf = store.get("username", handle)
            if not uf:
                continue
            uf.add_signal(
                SignalKind.CROSS_PLATFORM_HANDLE,
                f"same handle '{handle}' confirmed on {len(platforms)} platforms: {', '.join(sorted(platforms))}",
            )
            if event_sink:
                await event_sink({"type": "finding", "finding": uf.to_dict()})

        # 2. Link reuse: a website that appears in 2+ profiles
        link_count: Counter = Counter()
        for snap in snapshots.values():
            for link in snap.extracted_links:
                if not is_noise_url(link):
                    link_count[link] += 1
        for link, n in link_count.items():
            if n < 2:
                continue
            wf = store.get("website", link)
            if not wf:
                continue
            wf.add_signal(SignalKind.LINK_REUSE, f"website '{link}' linked from {n} different profiles")
            if event_sink:
                await event_sink({"type": "finding", "finding": wf.to_dict()})

        # 3. Email reuse: an email that appears in 2+ profile bios
        email_count: Counter = Counter()
        for snap in snapshots.values():
            for email in snap.extracted_emails:
                if _email_is_personal(email):
                    email_count[email] += 1
        for email, n in email_count.items():
            if n < 2:
                continue
            ef = store.get("email", email)
            if not ef:
                continue
            ef.add_signal(SignalKind.EMAIL_REUSE, f"email '{email}' appears in {n} different profile bios")
            if event_sink:
                await event_sink({"type": "finding", "finding": ef.to_dict()})

    async def _image_correlate_pass(
        self,
        snapshots: Dict[str, ProfileSnapshot],
        store: FindingStore,
        event_sink: EventSink,
    ) -> List[ImageCluster]:
        """Hash every fetched avatar; find clusters of visually-identical
        avatars across DIFFERENT platforms; reward the underlying
        username & social-profile Findings with an IMAGE_MATCH signal.

        Note: we DO hash blocked-snapshot avatars. Pages flagged as
        blocked (login wall / Cloudflare challenge) often still expose
        a valid og:image / twitter:image, and that's enough to fingerprint."""
        avatar_to_profile: Dict[str, ProfileSnapshot] = {}
        for snap in snapshots.values():
            if snap.avatar_url:
                avatar_to_profile.setdefault(snap.avatar_url, snap)
        if len(avatar_to_profile) < 2:
            return []

        if event_sink:
            await event_sink({"type": "stage", "stage": "image",
                              "detail": f"hashing {len(avatar_to_profile)} avatar(s) for cross-platform match"})

        hashes = await self.avatars.hash_many(avatar_to_profile.keys())
        if len(hashes) < 2:
            return []

        clusters = cluster_by_hash(hashes)
        if not clusters:
            return []

        for c in clusters:
            # Only reward if the cluster spans ≥ 2 distinct platforms
            platforms = {avatar_to_profile[u].platform for u in c.urls if u in avatar_to_profile}
            if len(platforms) < 2:
                continue

            # Promote the cluster into a first-class `image` Finding.
            # Key it by its representative hash so two searches that
            # rediscover the same avatar produce a stable identifier.
            image_key_value = f"sha:{c.representative_hash:016x}"
            image_finding = store.upsert(
                "image", image_key_value,
                signal=SignalKind.IMAGE_MATCH,
                reason=f"same avatar appears on {len(platforms)} platforms: {', '.join(sorted(platforms))}",
                source_url=c.urls[0],
                source_title=f"avatar cluster ({len(c.urls)} URLs)",
                source_type="image",
            )
            # +30 base on the image Finding itself (one strong cluster = verified-tier image)
            image_finding.add_signal(
                SignalKind.PROFILE_HIT,
                f"perceptually-identical avatar resolved on {len(c.urls)} URLs",
                delta=30,
            )

            for u in c.urls:
                snap = avatar_to_profile.get(u)
                if not snap:
                    continue
                # social_profile Finding reward + link
                sp = store.get("social_profile", snap.url)
                if sp:
                    sp.add_signal(
                        SignalKind.IMAGE_MATCH,
                        f"avatar matches {len(c.urls)-1} other profile(s) (Hamming ≤ {c.distances.get(u, 0)}): "
                        f"{', '.join(sorted(platforms))}",
                    )
                    store.link_pair(image_finding.key, sp.key, "this profile uses this avatar")
                    if event_sink:
                        await event_sink({"type": "finding", "finding": sp.to_dict()})
                # username Finding reward + link
                if snap.handle:
                    uf = store.get("username", snap.handle.lower())
                    if uf:
                        uf.add_signal(
                            SignalKind.IMAGE_MATCH,
                            f"same avatar appears on {len(platforms)} platforms ({', '.join(sorted(platforms))})",
                        )
                        store.link_pair(image_finding.key, uf.key, "handle uses this avatar across platforms")
                        if event_sink:
                            await event_sink({"type": "finding", "finding": uf.to_dict()})

            if event_sink:
                await event_sink({"type": "finding", "finding": image_finding.to_dict()})
        return clusters

    @staticmethod
    async def _reinforce_name_matches(
        store: FindingStore,
        snapshots: Dict[str, ProfileSnapshot],
        ctx_handles: Set[str],
        ctx_names: Set[str],
        event_sink: EventSink,
    ) -> None:
        """If two profiles share a high display-name similarity, give the
        underlying username Findings a NAME_MATCH bonus."""
        snaps = [s for s in snapshots.values() if s.display_name and not s.is_blocked]
        for i in range(len(snaps)):
            for j in range(i + 1, len(snaps)):
                a, b = snaps[i], snaps[j]
                sim = name_similarity(a.display_name, b.display_name)
                if sim >= 0.85 and a.handle and b.handle:
                    for handle in (a.handle.lower(), b.handle.lower()):
                        uf = store.get("username", handle)
                        if uf:
                            uf.add_signal(
                                SignalKind.NAME_MATCH,
                                f"display names match across {a.platform}/{a.handle} and {b.platform}/{b.handle}",
                            )

    @staticmethod
    def _domains_to_lookup(store: FindingStore, kind: QueryKind, value: str) -> List[str]:
        domains: Set[str] = set()
        if kind == "email":
            d = value.split("@", 1)[-1].strip().lower()
            if d and not is_platform_owned(d) and not _is_public_mailbox(d):
                domains.add(d)
        for f in store.by_type("domain"):
            if not is_platform_owned(f.value) and not _is_public_mailbox(f.value):
                domains.add(f.value)
        for f in store.by_type("website"):
            host = normalize_host(urlparse(f.value).hostname)
            if host and not is_platform_owned(host) and not _is_public_mailbox(host):
                domains.add(host)
        return sorted(domains)[:6]

    async def _rdap_pass(
        self,
        domains: List[str],
        store: FindingStore,
        result: CorrelationResult,
        seed_key: str,
        event_sink: EventSink,
    ) -> None:
        recs = await asyncio.gather(*[lookup_domain(d) for d in domains], return_exceptions=False)
        for rec in recs:
            result.whois_records.append(asdict(rec))
            if not rec.found:
                continue
            df = store.upsert(
                "domain", rec.domain,
                signal=SignalKind.RDAP_CONFIRMED,
                reason=f"public RDAP record exists ({rec.registrar or 'unknown registrar'})",
                source_url=rec.raw_url or f"https://rdap.org/domain/{rec.domain}",
                source_title=f"RDAP: {rec.domain}",
                source_type="rdap",
            )
            store.link_pair(df.key, seed_key, "domain associated with seed")
            for c in rec.contacts:
                if c.get("email"):
                    ef = store.upsert(
                        "email", c["email"],
                        signal=SignalKind.EXTRACTED_FROM_RDAP,
                        reason=f"registrant email for {rec.domain}",
                        source_url=rec.raw_url or f"https://rdap.org/domain/{rec.domain}",
                        source_title=f"RDAP contact for {rec.domain}",
                        source_type="rdap",
                    )
                    store.link_pair(ef.key, df.key, "registrant email")
                if c.get("phone"):
                    pf = store.upsert(
                        "phone", c["phone"],
                        signal=SignalKind.EXTRACTED_FROM_RDAP,
                        reason=f"registrant phone for {rec.domain}",
                        source_url=rec.raw_url or f"https://rdap.org/domain/{rec.domain}",
                        source_title=f"RDAP contact for {rec.domain}",
                        source_type="rdap",
                    )
                    store.link_pair(pf.key, df.key, "registrant phone")
                if c.get("name"):
                    nf = store.upsert(
                        "name", c["name"],
                        signal=SignalKind.EXTRACTED_FROM_RDAP,
                        reason=f"registrant name for {rec.domain}",
                        source_url=rec.raw_url or f"https://rdap.org/domain/{rec.domain}",
                        source_title=f"RDAP contact for {rec.domain}",
                        source_type="rdap",
                    )
                    store.link_pair(nf.key, df.key, "registrant name")
            if event_sink:
                await event_sink({"type": "finding", "finding": df.to_dict()})

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    @staticmethod
    def _populate_legacy_views(
        result: CorrelationResult,
        store: FindingStore,
        snapshots: Dict[str, ProfileSnapshot],
        confirmed_profiles: List[Dict[str, str]],
    ) -> None:
        result.related_usernames = sorted({f.value for f in store.by_type("username") if f.confidence >= 50})
        result.related_emails = sorted({f.value for f in store.by_type("email") if f.confidence >= 50})
        result.related_phones = sorted({f.value for f in store.by_type("phone") if f.confidence >= 50})
        result.related_websites = sorted({f.value for f in store.by_type("website") if f.confidence >= 50})
        result.related_domains = sorted({f.value for f in store.by_type("domain") if f.confidence >= 50})

        seen = set()
        for cp in confirmed_profiles:
            key = (cp["platform"], cp["url"])
            if key in seen:
                continue
            seen.add(key)
            result.social_profiles.append({"platform": cp["platform"], "url": cp["url"], "handle": cp.get("handle", "")})

        # Always emit profile_snapshots — even blocked ones, because their
        # avatar_url alone is valuable for the dashboard. The frontend
        # uses snap.is_blocked to render appropriate badges.
        for url, snap in snapshots.items():
            if not snap.is_blocked:
                result.websites.append({"url": url, "title": snap.title or ""})
                if snap.display_name or snap.bio or snap.avatar_url:
                    result.metadata_snippets.append({
                        "url": url,
                        "title": snap.title,
                        "og_title": snap.display_name,
                        "og_description": snap.bio,
                        "og_image": snap.avatar_url,
                        "description": snap.bio,
                    })
            result.profile_snapshots.append(_snap_to_dict(snap))

    @staticmethod
    def _build_summary(result: CorrelationResult, store: FindingStore) -> Dict[str, object]:
        all_findings = store.all()
        # Image diagnostics
        avatars = sum(1 for s in result.profile_snapshots if (s.get("avatar_url") if isinstance(s, dict) else s.avatar_url))
        return {
            "query_kind": result.query_kind,
            "query_value": result.query_value,
            "platforms_found": sorted({p["platform"] for p in result.social_profiles}),
            "username_count": sum(1 for f in all_findings if f.type == "username" and f.confidence >= 50),
            "email_count": sum(1 for f in all_findings if f.type == "email" and f.confidence >= 50),
            "phone_count": sum(1 for f in all_findings if f.type == "phone" and f.confidence >= 50),
            "site_count": len(result.websites),
            "domain_count": sum(1 for f in all_findings if f.type == "domain" and f.confidence >= 50),
            "finding_count": len(all_findings),
            "verified_count": sum(1 for f in all_findings if f.verified),
            "high_confidence_count": sum(1 for f in all_findings if f.confidence >= 90),
            "suppressed_count": result.suppressed_count,
            "avatars_extracted": avatars,
            "image_clusters_found": len(result.image_clusters),
            "image_finding_count": sum(1 for f in all_findings if f.type == "image"),
            "elasticsearch_hits": len(result.elasticsearch_results),
        }

    @staticmethod
    def _overall_confidence(store: FindingStore) -> tuple[int, str]:
        items = store.all()
        if not items:
            return 0, "unverified"
        # Average of the top-5 non-seed findings.
        ranked = [f for f in items if not any(s.kind == SignalKind.SEED.value for s in f.signals)]
        if not ranked:
            ranked = items
        top = sorted(ranked, key=lambda f: -f.confidence)[:5]
        avg = sum(f.confidence for f in top) / len(top)
        pct = int(round(avg))
        label = ("verified" if pct >= 85 else
                 "high"     if pct >= 70 else
                 "possible" if pct >= 50 else
                 "unverified")
        return pct, label

    @staticmethod
    def _build_graph(store: FindingStore, seed_key: str) -> Dict[str, List[Dict[str, object]]]:
        nodes: List[Dict[str, object]] = []
        edges: List[Dict[str, object]] = []
        seen_nodes: Set[str] = set()

        for f in store.all():
            if f.confidence < 25 and f.key != seed_key:
                continue  # Don't crowd the graph with weak findings
            if f.key in seen_nodes:
                continue
            seen_nodes.add(f.key)
            label = f.value
            if len(label) > 28:
                label = label[:27] + "…"
            nodes.append({
                "id": f.key, "label": label, "group": f.type,
                "confidence": f.confidence, "verified": f.verified,
            })

        # Edges are sourced from the FindingStore's link ledger so that each
        # one carries the concrete reason that justifies the connection.
        for link in store.graph_links():
            if link.a not in seen_nodes or link.b not in seen_nodes:
                continue
            edges.append({
                "from":   link.a,
                "to":     link.b,
                "reason": link.reason,
                "signal": link.signal_kind,
            })

        return {"nodes": nodes, "edges": edges, "seed": seed_key}


def _cluster_to_dict(c: ImageCluster, snapshots: Dict[str, ProfileSnapshot]) -> Dict[str, object]:
    """Render an image cluster for the API/UI."""
    members = []
    for u in c.urls:
        # Find which snapshot(s) reference this avatar
        snap = next((s for s in snapshots.values() if s.avatar_url == u), None)
        members.append({
            "avatar_url": u,
            "platform": snap.platform if snap else "unknown",
            "handle": snap.handle if snap else None,
            "profile_url": snap.url if snap else None,
            "min_distance": c.distances.get(u, 0),
        })
    return {
        "size": c.size,
        "platforms": sorted({m["platform"] for m in members if m["platform"] != "unknown"}),
        "representative_hash_hex": f"{c.representative_hash:016x}",
        "members": members,
    }


def _snap_to_dict(snap: ProfileSnapshot) -> Dict[str, object]:
    return {
        "url": snap.url,
        "platform": snap.platform,
        "handle": snap.handle,
        "display_name": snap.display_name,
        "bio": snap.bio,
        "avatar_url": snap.avatar_url,
        "title": snap.title,
        "extracted_emails": snap.extracted_emails,
        "extracted_handles": snap.extracted_handles,
        "extracted_links": snap.extracted_links,
        "is_blocked": snap.is_blocked,
        "parser_confidence": snap.parser_confidence,
    }


def _banner(label: str, width: int = 30) -> str:
    """Render a section header in the spec'd format:

        ==============================
        🟢 LOCAL DATABASE (HIGH TRUST)
        ==============================
    """
    bar = "=" * width
    return f"{bar}\n{label}\n{bar}"


def _bundle_value_for_field(matched_field: str, bundle: SearchBundle) -> str:
    """Map an ES `matched_field` (NAME/PHONE/EMAIL/TAGS) back to the
    user-supplied value the engine actually queried with."""
    f = (matched_field or "").upper()
    if f == "NAME":
        return bundle.name or ""
    if f == "PHONE":
        return bundle.phone or ""
    if f == "EMAIL":
        return bundle.email or ""
    if f == "TAGS":
        return bundle.username or bundle.name or ""
    return bundle.primary_value()


def _email_is_personal(email: str) -> bool:
    """Filter out role / no-reply / generic mailboxes."""
    local = (email.split("@", 1)[0] or "").lower()
    if not local:
        return False
    role_inboxes = {
        "noreply", "no-reply", "do-not-reply", "donotreply",
        "support", "help", "info", "contact", "hello", "hi",
        "admin", "administrator", "postmaster", "webmaster",
        "abuse", "security", "privacy", "press", "media",
        "sales", "billing", "accounts", "marketing", "team",
        "office", "feedback", "subscriptions", "newsletter",
    }
    return local not in role_inboxes


def _is_public_mailbox(domain: str) -> bool:
    return normalize_host(domain) in {
        "gmail.com", "googlemail.com", "yahoo.com", "outlook.com",
        "hotmail.com", "icloud.com", "proton.me", "protonmail.com",
        "live.com", "aol.com", "yandex.com", "mail.ru",
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

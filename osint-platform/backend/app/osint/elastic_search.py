"""Elasticsearch enrichment layer.

This module is an OPTIONAL companion to the OSINT pipeline. When
`ES_ENABLED=true`, every search additionally queries a local Elasticsearch
index (default `tc_index`) using input-type-aware queries:

    NAME      → exact + fuzzy + partial match on NAME, TAGS
    PHONE     → exact + last-4-digit fallback on PHONE
    EMAIL     → exact + domain match on EMAIL
    USERNAME  → fuzzy on NAME, exact on TAGS

Hits are normalized into the spec format:

    {
      "source": "elasticsearch",
      "name": "...",
      "phone": "...",
      "email": "...",
      "confidence": 0-100,
      "matched_field": "NAME | PHONE | EMAIL | TAGS",
      "reason": "exact match | fuzzy match | partial match | domain match | last4 match",
      "timestamp": "..."
    }

Confidence tiers (from the user spec):
    exact          → 95–100
    strong fuzzy   →  80–94
    partial        →  60–79
    weak           →  40–59

Safety: If the ES cluster is unreachable, mis-configured, or
`ES_ENABLED=false`, every public function returns an empty list and the
rest of the pipeline runs unaffected.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from app.config import get_settings
from app.core.logger import logger

QueryKind = Literal["name", "email", "phone", "username"]

# Lazy import — `elasticsearch` is an optional dep at runtime, and importing
# it eagerly would slow cold start for users who don't use ES.
_AsyncElasticsearch = None  # type: ignore[assignment]


def _load_es_client_class():
    global _AsyncElasticsearch
    if _AsyncElasticsearch is not None:
        return _AsyncElasticsearch
    try:
        from elasticsearch import AsyncElasticsearch  # type: ignore
        _AsyncElasticsearch = AsyncElasticsearch
        return AsyncElasticsearch
    except ImportError:
        logger.warning("elasticsearch package not installed — ES enrichment disabled")
        return None


@dataclass
class ESHit:
    """One normalized Elasticsearch document, ready for the API/UI."""
    source: str = "elasticsearch"
    name: str = ""
    phone: str = ""
    email: str = ""
    tags: List[str] = field(default_factory=list)
    asondate: str = ""
    confidence: int = 0
    matched_field: str = ""
    reason: str = ""
    timestamp: str = ""
    es_score: float = 0.0
    es_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "tags": self.tags,
            "asondate": self.asondate,
            "confidence": self.confidence,
            "matched_field": self.matched_field,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "es_score": round(self.es_score, 3),
            "es_id": self.es_id,
        }


class ElasticIntel:
    """Singleton-ish async ES client with input-type-aware querying.

    Holds one `AsyncElasticsearch` instance for the process; reconnects
    lazily on first query."""

    _instance: Optional["ElasticIntel"] = None

    def __init__(self):
        self.s = get_settings()
        self._client = None  # type: ignore[assignment]
        self._init_lock = asyncio.Lock()
        self._healthy: Optional[bool] = None
        self._last_error: Optional[str] = None

    @classmethod
    def instance(cls) -> "ElasticIntel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Connection / health
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.s.es_enabled and self.s.es_password)

    async def _ensure_client(self):
        if self._client is not None:
            return self._client
        async with self._init_lock:
            if self._client is not None:
                return self._client
            cls = _load_es_client_class()
            if cls is None:
                self._healthy = False
                self._last_error = "elasticsearch package missing"
                return None
            try:
                kwargs: Dict[str, Any] = {
                    "hosts": [self.s.es_url],
                    "basic_auth": (self.s.es_user, self.s.es_password),
                    "verify_certs": self.s.es_verify_certs,
                    "request_timeout": self.s.es_timeout,
                }
                if self.s.es_ca_cert:
                    kwargs["ca_certs"] = self.s.es_ca_cert
                # urllib3 prints a noisy warning if verify_certs=False; suppress.
                if not self.s.es_verify_certs:
                    try:
                        import urllib3
                        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    except Exception:  # noqa: BLE001
                        pass
                self._client = cls(**kwargs)
                logger.info("Elasticsearch client initialized for %s", self.s.es_url)
                return self._client
            except Exception as e:  # noqa: BLE001
                self._healthy = False
                self._last_error = str(e)
                logger.warning("Failed to init Elasticsearch client: %s", e)
                return None

    async def health(self) -> Dict[str, Any]:
        """Return a small health snapshot (used by /api/health)."""
        if not self.enabled:
            return {"enabled": False, "reachable": False, "reason": "ES_ENABLED=false or no password"}
        client = await self._ensure_client()
        if client is None:
            return {"enabled": True, "reachable": False, "reason": self._last_error or "client init failed"}
        try:
            info = await client.info()
            self._healthy = True
            return {
                "enabled": True,
                "reachable": True,
                "version": (info.get("version") or {}).get("number"),
                "cluster": info.get("cluster_name"),
                "index": self.s.es_index,
            }
        except Exception as e:  # noqa: BLE001
            self._healthy = False
            self._last_error = str(e)
            return {"enabled": True, "reachable": False, "reason": self._last_error}

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    # ------------------------------------------------------------------
    # Public search
    # ------------------------------------------------------------------
    async def search(self, kind: QueryKind, value: str) -> List[ESHit]:
        """Run the right ES query for the given input kind.

        Returns a normalized list of ESHit objects. Returns empty list on
        any failure (network / auth / mapping) — never raises."""
        if not self.enabled:
            return []
        value = (value or "").strip()
        if not value:
            return []
        client = await self._ensure_client()
        if client is None:
            return []

        try:
            if kind == "name":
                return await self._search_name(client, value)
            if kind == "email":
                return await self._search_email(client, value)
            if kind == "phone":
                return await self._search_phone(client, value)
            if kind == "username":
                return await self._search_username(client, value)
        except Exception as e:  # noqa: BLE001
            self._last_error = str(e)
            logger.warning("ES search failed (%s=%r): %s", kind, value, e)
            return []
        return []

    async def search_bundle(self, *, name: str = "", email: str = "",
                            phone: str = "", username: str = "") -> List[ESHit]:
        """Spec'd strict local-DB search.

        Per the user spec, search rules are PER-FIELD, not universal:
            NAME     → match_phrase (case-insensitive) on NAME
            PHONE    → exact term match on PHONE
            EMAIL    → partial / wildcard match on EMAIL
            USERNAME → tag match on TAGS (also fuzzy NAME as a fallback)

        Each provided field dispatches to its own typed query. Inputs are
        TRIMMED before search. Hits from all per-field queries are deduped
        by ES `_id`, keeping the highest-confidence variant."""
        # Trim every value upfront — the universal contract for ES queries
        # is "no leading/trailing whitespace ever reaches Elasticsearch".
        name     = (name or "").strip()
        email    = (email or "").strip()
        phone    = (phone or "").strip()
        username = (username or "").strip()

        if not any([name, email, phone, username]):
            return []

        client = await self._ensure_client()
        if client is None:
            return []

        coros = []
        if name:
            coros.append(self._search_name(client, name))
        if email:
            coros.append(self._search_email(client, email))
        if phone:
            coros.append(self._search_phone(client, phone))
        if username:
            coros.append(self._search_username(client, username))

        try:
            results = await asyncio.gather(*coros, return_exceptions=False)
        except Exception as e:  # noqa: BLE001
            self._last_error = str(e)
            logger.warning("ES bundle search failed: %s", e)
            return []

        # Dedupe by es_id — keep highest-confidence variant.
        best: Dict[str, ESHit] = {}
        for hits in results:
            for h in hits:
                key = h.es_id or f"{h.name}|{h.phone}|{h.email}"
                cur = best.get(key)
                if cur is None or h.confidence > cur.confidence:
                    best[key] = h
        merged = list(best.values())

        # Suppress fuzzy noise when an exact match already resolved the
        # same field. If the input "Madavi Jangu Jangu" lands an exact NAME
        # hit, the dozen "Jangu Madavi" fuzzy NAME hits dilute the result
        # without adding signal — same surname, different person. Filter
        # is scoped per field, so an exact NAME hit never suppresses
        # fuzzy hits on EMAIL/PHONE/TAGS.
        exact_reasons = {"exact match", "exact tag match"}
        exact_fields = {h.matched_field for h in merged if h.reason in exact_reasons}
        if exact_fields:
            merged = [
                h for h in merged
                if h.matched_field not in exact_fields or h.reason != "fuzzy match"
            ]

        merged.sort(key=lambda x: -x.confidence)
        return merged[: self.s.es_max_hits]

    async def search_universal(self, value: str) -> List[ESHit]:
        """Public wrapper around the spec's universal multi_match query.

        Useful if a caller wants to bypass the typed bundle interface
        and just hand a single input string. Returns normalized ESHit
        objects (or [] on any failure)."""
        if not self.enabled or not (value or "").strip():
            return []
        client = await self._ensure_client()
        if client is None:
            return []
        try:
            return await self._universal_query(client, value.strip())
        except Exception as e:  # noqa: BLE001
            self._last_error = str(e)
            logger.warning("ES universal_query failed for %r: %s", value, e)
            return []

    async def _universal_query(self, client, value: str) -> List[ESHit]:
        """The spec's exact query, run against `tc_index`:

            {
              "query": {
                "multi_match": {
                  "query": "<input>",
                  "fields": ["NAME", "PHONE", "EMAIL", "TAGS"],
                  "fuzziness": "AUTO"
                }
              }
            }

        After receiving hits, classify each by which field matched
        most strongly so we can stamp `matched_field` and `reason` on
        the ESHit (used for the per-record audit trail)."""
        body = {
            "size": self.s.es_max_hits,
            "query": {
                "multi_match": {
                    "query": value,
                    "fields": ["NAME", "PHONE", "EMAIL", "TAGS"],
                    "fuzziness": "AUTO",
                }
            },
        }
        resp = await client.search(index=self.s.es_index, body=body)
        return [self._classify_universal_hit(h, value) for h in _get_hits(resp)]

    def _classify_universal_hit(self, hit: Dict[str, Any], query: str) -> ESHit:
        """Decide which field actually matched the universal query."""
        es_hit = _hit_to_eshit(hit)
        q = (query or "").strip()
        ql = q.lower()

        n = (es_hit.name or "").lower()
        p = (es_hit.phone or "")
        p_digits = re.sub(r"\D", "", p)
        e = (es_hit.email or "").lower()
        tags_lower = [(t or "").lower() for t in es_hit.tags]
        q_digits = re.sub(r"\D", "", q)

        # Pick the strongest matched field, in priority order.
        if ql and (ql == n):
            es_hit.matched_field = "NAME"; es_hit.reason = "exact match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif ql and ql in n and n:
            es_hit.matched_field = "NAME"; es_hit.reason = "partial match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        elif ql and (ql == e):
            es_hit.matched_field = "EMAIL"; es_hit.reason = "exact match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif ql and ql in e and e:
            es_hit.matched_field = "EMAIL"; es_hit.reason = "partial match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        elif q_digits and (q_digits == p_digits or q == p):
            es_hit.matched_field = "PHONE"; es_hit.reason = "exact match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif q_digits and q_digits in p_digits and p_digits:
            es_hit.matched_field = "PHONE"; es_hit.reason = "partial match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        elif ql and ql in tags_lower:
            es_hit.matched_field = "TAGS"; es_hit.reason = "exact tag match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif ql and any(ql in t for t in tags_lower):
            es_hit.matched_field = "TAGS"; es_hit.reason = "partial tag match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        else:
            # Elasticsearch's fuzziness AUTO accepted this hit but no
            # exact/partial substring landed — record as fuzzy.
            es_hit.matched_field = "NAME" if n else ("EMAIL" if e else ("PHONE" if p else "TAGS"))
            es_hit.reason = "fuzzy match"
            es_hit.confidence = _conf_from_score(hit, base_lo=40, base_hi=94)
        return es_hit

    # ------------------------------------------------------------------
    # Per-kind query builders
    # ------------------------------------------------------------------
    async def _search_name(self, client, value: str) -> List[ESHit]:
        """Name → match_phrase on NAME (per spec).

        Per the user spec ("Use match_phrase for NAME"), the primary
        operator is `match_phrase` against the NAME field — preserves
        token order and is case-insensitive via the standard analyzer.
        We also probe TAGS so that a name supplied as a tag still
        resolves, but NAME is the source of truth and gets the highest
        boost. Fuzziness is added as a low-boost fallback to keep light
        typos resolvable without overriding the strict phrase intent."""
        value = (value or "").strip()
        body = {
            "size": self.s.es_max_hits,
            "query": {
                "bool": {
                    "should": [
                        # Spec-mandated case-insensitive phrase match on NAME.
                        {"match_phrase": {"NAME": {"query": value, "boost": 6.0}}},
                        # Phrase match against TAGS (names sometimes filed there).
                        {"match_phrase": {"TAGS": {"query": value, "boost": 2.0}}},
                        # Light token-level fallback so single-token typos still
                        # surface a hit — kept at low boost so it never beats
                        # a true phrase match.
                        {"match": {
                            "NAME": {
                                "query": value,
                                "operator": "and",
                                "fuzziness": "AUTO",
                                "boost": 1.5,
                            }
                        }},
                        # Prefix on NAME (handles "Az" → "Azhar")
                        {"prefix": {"NAME.keyword": {"value": value, "boost": 1.0}}}
                            if _has_keyword_subfield() else None,
                    ],
                    "minimum_should_match": 1,
                }
            },
        }
        body["query"]["bool"]["should"] = [c for c in body["query"]["bool"]["should"] if c]
        resp = await client.search(index=self.s.es_index, body=body)
        return [self._classify_name_hit(h, value) for h in _get_hits(resp)]

    async def _search_email(self, client, value: str) -> List[ESHit]:
        """Email → exact term match on EMAIL (per spec: "term for email").

        EMAIL is stored as a `keyword` field in tc_index, so a single
        `term` clause on the lowercased input is the authoritative match.
        We do NOT use wildcards here: this query feeds the AUTHORITATIVE
        local-DB layer (records get confidence=100), so any partial-match
        clause would silently promote unrelated emails to "100% trust"."""
        normalized = (value or "").strip().lower()
        domain = normalized.split("@", 1)[-1] if "@" in normalized else ""

        body = {
            "size": self.s.es_max_hits,
            "query": {"term": {"EMAIL": {"value": normalized}}},
        }
        resp = await client.search(index=self.s.es_index, body=body)
        return [self._classify_email_hit(h, normalized, domain) for h in _get_hits(resp)]

    async def _search_phone(self, client, value: str) -> List[ESHit]:
        """Phone → exact term match on PHONE (per spec: "term for phone").

        PHONE is a `keyword` field in tc_index. We match the raw input AND
        its digits-only normalization (so "+91 90630-41294" still finds
        "9063041294") — both via `term`. No wildcard / last-4 fallback:
        this feeds the AUTHORITATIVE layer (confidence=100) and last-4
        substring matches would mass-promote unrelated phones."""
        value  = (value or "").strip()
        digits = re.sub(r"\D", "", value)

        terms = [value]
        if digits and digits != value:
            terms.append(digits)

        body = {
            "size": self.s.es_max_hits,
            "query": {"terms": {"PHONE": terms}},
        }
        resp = await client.search(index=self.s.es_index, body=body)
        return [self._classify_phone_hit(h, value, digits, "") for h in _get_hits(resp)]

    async def _search_username(self, client, value: str) -> List[ESHit]:
        """Username → fuzzy on NAME (handles like 'jdoe' → 'John Doe' is unlikely
        without explicit storage, so we also probe TAGS where username may be
        indexed)."""
        handle = value.lstrip("@")
        body = {
            "size": self.s.es_max_hits,
            "query": {
                "bool": {
                    "should": [
                        {"term": {"TAGS": {"value": handle, "boost": 5.0}}},
                        {"match": {"TAGS": {"query": handle, "fuzziness": "AUTO", "boost": 3.0}}},
                        {"match": {"NAME": {"query": handle, "fuzziness": "AUTO", "boost": 1.5}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
        }
        resp = await client.search(index=self.s.es_index, body=body)
        return [self._classify_username_hit(h, handle) for h in _get_hits(resp)]

    # ------------------------------------------------------------------
    # Hit classification (assigns confidence + matched_field + reason)
    # ------------------------------------------------------------------
    def _classify_name_hit(self, hit: Dict[str, Any], query: str) -> ESHit:
        es_hit = _hit_to_eshit(hit)
        src_name = (es_hit.name or "").strip()
        q_norm = query.strip().lower()
        n_norm = src_name.lower()
        if n_norm == q_norm:
            es_hit.matched_field = "NAME"
            es_hit.reason = "exact match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif q_norm and (q_norm in n_norm or n_norm in q_norm):
            es_hit.matched_field = "NAME"
            es_hit.reason = "partial match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        elif q_norm and any(q_norm in (t or "").lower() for t in es_hit.tags):
            es_hit.matched_field = "TAGS"
            es_hit.reason = "tag match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        else:
            # Fuzzy fallback — Elasticsearch decided this was a hit, but it
            # didn't pass our exact/partial checks above.
            es_hit.matched_field = "NAME"
            es_hit.reason = "fuzzy match"
            es_hit.confidence = _conf_from_score(hit, base_lo=40, base_hi=94)
        return es_hit

    def _classify_email_hit(self, hit: Dict[str, Any], query: str, domain: str) -> ESHit:
        es_hit = _hit_to_eshit(hit)
        e_norm = (es_hit.email or "").strip().lower()
        if e_norm == query:
            es_hit.matched_field = "EMAIL"
            es_hit.reason = "exact match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif domain and e_norm.endswith("@" + domain):
            es_hit.matched_field = "EMAIL"
            es_hit.reason = f"domain match (@{domain})"
            es_hit.confidence = _conf_from_score(hit, base_lo=40, base_hi=59)
        elif query and (query in e_norm or e_norm in query):
            es_hit.matched_field = "EMAIL"
            es_hit.reason = "partial match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        else:
            es_hit.matched_field = "EMAIL"
            es_hit.reason = "fuzzy match"
            es_hit.confidence = _conf_from_score(hit, base_lo=40, base_hi=94)
        return es_hit

    def _classify_phone_hit(self, hit: Dict[str, Any], query: str,
                            digits: str, last4: str) -> ESHit:
        es_hit = _hit_to_eshit(hit)
        p = (es_hit.phone or "").strip()
        p_digits = re.sub(r"\D", "", p)
        if p == query or (digits and p_digits == digits):
            es_hit.matched_field = "PHONE"
            es_hit.reason = "exact match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif digits and digits in p_digits:
            es_hit.matched_field = "PHONE"
            es_hit.reason = "partial match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        elif last4 and p_digits.endswith(last4):
            es_hit.matched_field = "PHONE"
            es_hit.reason = f"last-4-digit match ({last4})"
            es_hit.confidence = _conf_from_score(hit, base_lo=40, base_hi=59)
        else:
            es_hit.matched_field = "PHONE"
            es_hit.reason = "fuzzy match"
            es_hit.confidence = _conf_from_score(hit, base_lo=40, base_hi=94)
        return es_hit

    def _classify_username_hit(self, hit: Dict[str, Any], handle: str) -> ESHit:
        es_hit = _hit_to_eshit(hit)
        h = handle.lower()
        tags_lower = [(t or "").lower() for t in es_hit.tags]
        if h in tags_lower:
            es_hit.matched_field = "TAGS"
            es_hit.reason = "exact tag match"
            es_hit.confidence = _conf_from_score(hit, base_lo=95, base_hi=100)
        elif any(h in t or t in h for t in tags_lower):
            es_hit.matched_field = "TAGS"
            es_hit.reason = "partial tag match"
            es_hit.confidence = _conf_from_score(hit, base_lo=60, base_hi=79)
        else:
            es_hit.matched_field = "NAME"
            es_hit.reason = "fuzzy name match"
            es_hit.confidence = _conf_from_score(hit, base_lo=40, base_hi=94)
        return es_hit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_keyword_subfield() -> bool:
    """We can't introspect the index mapping cheaply at every query, so we
    optimistically assume `NAME.keyword` exists (default for dynamic
    string mappings in ES 8.x). If it doesn't, the prefix clause silently
    matches nothing — no error."""
    return True


def _get_hits(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        # AsyncElasticsearch >=8 returns ObjectApiResponse — both .body and
        # dict-style access work; .get() works for both forms.
        return list(resp.get("hits", {}).get("hits", []) or [])
    except Exception:  # noqa: BLE001
        return []


def _hit_to_eshit(hit: Dict[str, Any]) -> ESHit:
    src = hit.get("_source", {}) or {}
    tags_raw = src.get("TAGS")
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    elif isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        tags = []
    return ESHit(
        source="elasticsearch",
        name=str(src.get("NAME") or "").strip(),
        phone=str(src.get("PHONE") or "").strip(),
        email=str(src.get("EMAIL") or "").strip(),
        tags=tags,
        asondate=str(src.get("ASONDATE") or "").strip(),
        es_score=float(hit.get("_score") or 0.0),
        es_id=str(hit.get("_id") or ""),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _conf_from_score(hit: Dict[str, Any], *, base_lo: int, base_hi: int) -> int:
    """Map an ES `_score` into the user-spec'd tier band [base_lo, base_hi].

    ES scores are unbounded; we squash with a soft saturation around
    score=10. Within the band the relative ordering by ES score is
    preserved, but every hit in this tier stays inside the band."""
    score = float(hit.get("_score") or 0.0)
    # 0 → 0.0, 1 → ~0.5, 5 → ~0.83, 10+ → ~0.95
    sat = score / (score + 1.0) if score > 0 else 0.0
    span = max(0, base_hi - base_lo)
    return int(round(base_lo + sat * span))


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------

async def search_es(kind: QueryKind, value: str) -> List[Dict[str, Any]]:
    """One-shot helper: run an ES search and return dicts in the spec format."""
    hits = await ElasticIntel.instance().search(kind, value)
    return [h.to_dict() for h in hits]


async def search_es_bundle(*, name: str = "", email: str = "",
                           phone: str = "", username: str = "") -> List[Dict[str, Any]]:
    hits = await ElasticIntel.instance().search_bundle(
        name=name, email=email, phone=phone, username=username,
    )
    return [h.to_dict() for h in hits]


async def es_health() -> Dict[str, Any]:
    return await ElasticIntel.instance().health()
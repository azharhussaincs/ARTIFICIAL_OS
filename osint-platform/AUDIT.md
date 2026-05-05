# Platform Audit

**Aim of this document:** a single up-to-date map of which spec
capabilities are implemented and where they live, so future iterations
don't re-implement what's already there.

---

## Capability matrix

| # | Spec capability | Status | File(s) |
|---|---|---|---|
|  1 | Multi-input identity bundle (name / email / phone / username) | ✅ | `correlation.py:SearchBundle`, `_seed_bundle`, `_candidate_usernames_for_bundle` |
|  2 | Per-input expansion (handle variations, email patterns, etc.) | ✅ | `correlation._candidate_usernames` |
|  3 | Public-only access (no login bypass, no private APIs) | ✅ enforced | `core/ethics.py`, `osint/scraper.py`, `osint/profile_match.py` |
|  4 | Google-style dorking | ✅ | `osint/dorks.py` (Google + Bing + DuckDuckGo URLs) |
|  5 | Async crawling + robots.txt + per-host throttle | ✅ | `osint/scraper.py`, `core/ethics.py:RobotsCache`, `core/rate_limit.py:HostThrottle` |
|  6 | URL deduplication + canonical normalization | ✅ | `osint/relevance.py:normalize_host`, `FindingStore` keyed lowercased values |
|  7 | Footer/nav/privacy/static-asset filtering | ✅ | `osint/relevance.py` (~80 platform-owned hosts + `IGNORE_PATH_PATTERNS` + `STATIC_ASSET_EXT`) |
|  8 | Per-platform fingerprint parsers | ✅ | `osint/fingerprints.py` (GitHub, GitLab, Dev.to, Medium, Reddit, YouTube, About.me, Keybase + OG fallback) |
|  9 | Avatar extraction (img tags, og:image, twitter:image, JSON-LD, link rel="image_src") | ✅ | `fingerprints.py:_meta_image()` |
| 10 | Direct-avatar fast path (deterministic CDN URLs) | ✅ | `image_match.py:DIRECT_AVATAR_BUILDERS` (GitHub, GitLab) |
| 11 | Email seed → Gravatar promotion | ✅ | `correlation.run_bundle` synthesizes a `gravatar` snapshot |
| 12 | Platform-default share-image filter | ✅ | `fingerprints.py:_is_platform_default_image()` (~20 fragments) |
| 13 | Salvage avatars from non-200 responses | ✅ | `profile_match.py:fetch()` parses error-page bodies for og:image |
| 14 | Image proxy (server-side fetch + LRU cache + SSRF guard) | ✅ | `api/image_proxy.py` |
| 15 | Perceptual hashing of avatars (dHash, 64-bit) | ✅ | `image_match.py:dhash` |
| 16 | Cross-platform avatar clustering (Hamming ≤ 12) | ✅ | `image_match.py:cluster_by_hash` (single-link union-find) |
| 17 | `image` Finding type — keyed by `image::sha:<hash>` | ✅ | `verification.py:FindingType`, `correlation._image_correlate_pass` |
| 18 | RDAP / WHOIS for non-mailbox domains | ✅ | `osint/whois_lookup.py` (rdap.org transport) |
| 19 | Username probe (anonymous GET) across 21 platforms | ✅ | `osint/username_check.py` — github, gitlab, twitter/x, reddit, medium, dev.to, stackoverflow, youtube, tiktok, instagram, pinterest, vimeo, about.me, keybase, hackerone, npmjs, dockerhub, **facebook**, **threads**, **bluesky**, **mastodon-social** |
| 20 | Iterative recursive-handle discovery (capped) | ✅ | `correlation._fold_in_snapshots` + `MAX_RECURSIVE_HANDLES = 4` |
| 21 | Cross-platform corroboration bonuses | ✅ | `correlation._cross_platform_corroborate` (handle/link/email reuse) |
| 22 | Name-similarity reinforcement | ✅ | `correlation._reinforce_name_matches` + `profile_match.name_similarity` |
| 23 | Additive signal-based confidence (clamped 0–100) | ✅ | `verification.py:SIGNAL_DELTA` |
| 24 | Tier labels: verified ≥ 85 / high ≥ 70 / possible ≥ 50 / unverified < 50 | ✅ | `verification._label()` |
| 25 | Per-Finding evidence trail (signals[] with delta + reason + source) | ✅ | `Finding.signals[]` + `Finding.sources[]` |
| 26 | Edge-level evidence in identity graph | ✅ | `verification.py:GraphLink`, `FindingStore.graph_links()` — every edge carries `reason` and `signal_kind` |
| 27 | Unified chronological evidence ledger | ✅ | `FindingStore.evidence_ledger()` → `SearchResponse.evidence_ledger` |
| 28 | Per-IP rate limiting | ✅ | `core/rate_limit.py:IPRateLimiter` (sliding window) |
| 29 | Real-time SSE stream (`stage` / `finding` / `snapshot` / `complete`) | ✅ | `api/search.py:/search/stream` |
| 30 | Multi-input bundle endpoint | ✅ | `POST /api/search/bundle` |
| 31 | History persistence + replay + delete | ✅ | `models.py:SearchRecord`, `api/history.py` |
| 32 | CSV / PDF export | ✅ | `api/export.py` |
| 33 | Premium Next.js dashboard (Tailwind + Framer Motion + Cytoscape + Lucide) | ✅ | `frontend/` |
| 34 | Findings cards with signal trail + sources | ✅ | `FindingCard.tsx`, `SignalTrail.tsx` |
| 35 | Identity graph with neon styling, verified-pulse, edge tooltips with reason | ✅ | `IdentityGraph.tsx` |
| 36 | Live SSE terminal | ✅ | `LiveTerminal.tsx` |
| 37 | Image cluster panel (side-by-side avatar comparison + hover-zoom) | ✅ | `ImageClustersPanel.tsx` |
| 38 | Evidence ledger panel | ✅ | `EvidenceLedger.tsx` |
| 39 | Diagnostics strip (avatars / clusters / image findings) | ✅ | `page.tsx` |
| 40 | ⌘K command palette + keyboard shortcuts (`/`, `Esc`, `⌘K`) | ✅ | `CommandPalette.tsx`, `useKeyboard.ts` |
| 41 | Static fallback dashboard (no Node required) | ✅ | `backend/app/static/` |
| 42 | Docker Compose (web + api + db) | ✅ | `docker-compose.yml` |

---

## Excluded by design

| Item | Reason |
|---|---|
| **WhatsApp** profile probes | No public profile surface. `wa.me/<phone>` returns a generic page for any input — probing it would only generate noise. Numbers can only be looked up through the contact API which requires a phone permission grant. Not OSINT. |
| **Headless-browser rendering** (Playwright) of every profile | Most profile pages we care about expose `og:image` / `twitter:image` in their SSR HTML. The combination of multi-source `_meta_image` extraction + direct-avatar URL fallback (GitHub `/USER.png`) gets us avatars without spinning up Chromium. Listed as a roadmap item in the README — add it when corpus or scale demands it. |
| **Embeddings-based bio matching** | `difflib.SequenceMatcher` + tokenset Jaccard is sufficient for the current handle and bio comparison. Sentence-transformers would help for multi-language paraphrased bios but is heavy infra. Future work. |
| **Synthesizing emails from a name** | Spec said "ONLY discovery from public sources." We never invent emails; we only extract them from public bios / RDAP records. |

---

## Net-new in this iteration

1. **`GraphLink` ledger inside `FindingStore`** — every `link_pair()` records a canonical `(a, b, reason, signal_kind, at)` entry. The graph in `SearchResponse.graph.edges` now carries `{from, to, reason, signal}` for every connection.
2. **`evidence_ledger()` method** — flattens every signal across every Finding into a chronologically-sorted audit trail (one row per signal; columns: time, type, value, signal, delta, reason, source_url). Surfaced as `SearchResponse.evidence_ledger`.
3. **`EvidenceLedger.tsx`** — new dashboard panel with sign / type filters; renders the ledger as a compact monospace table with delta colour coding and click-through source links.
4. **Cytoscape edge tooltip** — hovering any edge in `IdentityGraph.tsx` now shows the recorded `signal` + `reason`, so analysts can drill into "why is this connected to that?" without leaving the graph view.
5. **Four new platform probes** — `facebook`, `threads`, `bluesky`, `mastodon.social` (all anonymous GET only, with calibrated confidence levels per the soft-404 risk).
6. **WhatsApp explanation** in `username_check.py` for future maintainers who'll inevitably ask "why isn't WhatsApp here?"

---

## Smoke-test reproducer

```bash
source onve/bin/activate
cd osint-platform/backend
python3 -c "
import sys; sys.path.insert(0, '.')
from app.osint.verification import FindingStore, SignalKind
s = FindingStore()
seed = s.upsert('username', 'janedoe', signal=SignalKind.SEED,
    reason='user-supplied', source_url='urn:user-input', source_type='seed').key
gh = s.upsert('social_profile', 'https://github.com/janedoe', signal=SignalKind.PROFILE_HIT,
    reason='200 OK on github', source_url='https://github.com/janedoe', source_type='profile').key
yt = s.upsert('social_profile', 'https://www.youtube.com/@janedoe', signal=SignalKind.PROFILE_HIT,
    reason='200 OK on youtube', source_url='https://www.youtube.com/@janedoe', source_type='profile').key
s.link_pair(gh, seed, 'profile derived from seed handle')
s.link_pair(gh, yt,  'same handle confirmed on multiple platforms', SignalKind.CROSS_PLATFORM_HANDLE)
for l in s.graph_links():
    print(f'  edge: {l.a} ⇄ {l.b}  [{l.signal_kind}]  {l.reason}')
print(f'  ledger rows: {len(s.evidence_ledger())}')
"
```

Expected output: each edge prints with its reason and signal_kind; ledger has one row per signal in chronological order.

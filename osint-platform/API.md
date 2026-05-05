# API Reference

Base URL: `http://localhost:8000/api` (set by your reverse proxy in production).

OpenAPI is auto-generated and browsable at [`/docs`](http://localhost:8000/docs)
and [`/redoc`](http://localhost:8000/redoc).

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/search` | Run full correlation on a single identifier. |
| `POST` | `/api/search/bundle` | **NEW** — multi-input identity resolution (any combo of name/email/phone/username). |
| `GET`  | `/api/search/stream?kind=…&value=…` | **SSE** stream of correlation events as they happen. |
| `POST` | `/api/dorks` | Generate dork queries only (no crawling). |
| `GET`  | `/api/history?limit=N&offset=N` | Paginated past searches. |
| `GET`  | `/api/history/{id}` | Full payload for a single past search. |
| `DELETE`| `/api/history/{id}` | Remove a record. |
| `GET`  | `/api/export/{id}/csv` | CSV export. |
| `GET`  | `/api/export/{id}/pdf` | PDF report. |
| `GET`  | `/api/image?url=…`     | **Image proxy** — server-side fetch + cache; bypasses CDN hot-link blocks. |
| `GET`  | `/api/health` | Liveness probe. |

> Every `SearchResponse.graph.edges[]` entry now includes `reason` and
> `signal` fields, and the response carries a top-level
> `evidence_ledger[]` — a chronologically-sorted audit trail of every
> signal across every Finding (columns: `at`, `finding_key`, `type`,
> `value`, `signal`, `delta`, `reason`, `source_url`). See
> [AUDIT.md](AUDIT.md) for the complete capability map.

---

## `POST /api/search`

### Request
```json
{ "kind": "name|email|phone|username", "value": "Jane Doe" }
```

### Response (abridged)
```json
{
  "id": 42,
  "query_kind": "name",
  "query_value": "Jane Doe",
  "started_at": "2026-04-30T10:11:12+00:00",
  "finished_at": "2026-04-30T10:11:18+00:00",
  "confidence_score": 88,
  "confidence_label": "likely",
  "summary": {
    "platforms_found": ["github", "youtube", "instagram"],
    "username_count": 1,
    "email_count": 1,
    "phone_count": 0,
    "site_count": 2,
    "domain_count": 1,
    "finding_count": 6,
    "verified_count": 3,
    "high_confidence_count": 2,
    "suppressed_count": 17
  },
  "findings":            [ /* see Finding schema below */ ],
  "related_usernames":   ["janedoe"],
  "related_emails":      ["azhar@azhar.dev"],
  "related_phones":      [],
  "related_websites":    ["https://azhar.dev"],
  "related_domains":     ["azhar.dev"],
  "social_profiles":     [...],
  "websites":            [...],
  "dorks":               [...],
  "metadata_snippets":   [...],
  "profile_snapshots":   [...],
  "whois_records":       [...],
  "timeline":            [...],
  "graph":               { "nodes": [...], "edges": [...], "seed": "name::azhar baloch" },
  "email_report":        null,
  "phone_report":        null
}
```

`suppressed_count` reports how many noisy candidates the relevance gate
threw out (footer links, CDN URLs, generic platform text — see
[`NOISE_MODEL.md`](NOISE_MODEL.md)).

`related_usernames` / `related_emails` / `related_phones` /
`related_websites` / `related_domains` only include findings with
**confidence ≥ 50**. The full noisy list is in `findings`.

---

## `POST /api/search/bundle` — multi-input identity resolution

Pass any subset of the four canonical identifiers — the engine seeds
one Finding per non-empty field, links them all to each other, takes
the **union** of derived candidate handles, and runs the full pipeline.

### Request
```json
{
  "name":     "Jane Doe",
  "username": "janedoe",
  "email":    "azhar@azhar.dev",
  "phone":    "+14155551212"
}
```

All four fields are optional but at least one is required. Response
shape is identical to `POST /api/search` (same `SearchResponse`).

### When to use bundle vs. single

| Scenario | Endpoint |
|---|---|
| User typed one thing | `/api/search` |
| You already have 2+ identifiers from a prior step | `/api/search/bundle` |
| Replaying from a contact-card import | `/api/search/bundle` |

The bundle path is strictly a superset — it converges to the same
result as the single-input path when only one field is provided.

---

## `GET /api/image?url=…` — image proxy

Profile avatars on most platforms (`pbs.twimg.com`, `scontent.cdninstagram.com`,
`*.tiktokcdn.com`, `lh3.googleusercontent.com`, …) are hot-link-protected
or session-bound, so an `<img src="https://…">` directly from the dashboard
fails silently. The proxy fetches them server-side, with our own
User-Agent and **no Referer**, and streams them back through your origin.

```
GET /api/image?url=https://avatars.githubusercontent.com/u/9919
→ 200 image/png  (X-Proxy-Cache: MISS)
→ Cache-Control: public, max-age=3600, immutable
```

Status codes:
- `200` — bytes streamed back
- `400` — host blocked by SSRF guard (private IPs, loopback, cloud-metadata)
- `413` — image > 4 MB
- `415` — non-`image/*` content-type
- `429` — per-IP rate limit (60/min)
- `502` — upstream error

The response is cached server-side in a 256-entry LRU for 1 hour, so
repeated dashboard loads are instant.

The frontend's `<ImageThumb>` component automatically wraps every
avatar URL through this endpoint — see
`frontend/app/components/ui/ImageThumb.tsx`.

---

## Image clusters

When the engine fetches confirmed profiles, it also computes a
**perceptual hash** (dHash, 64-bit) of every avatar URL. Avatars whose
hashes are within a Hamming distance of 12 are clustered. Clusters that
span ≥2 distinct platforms grant the underlying username and
social-profile Findings a `+20 image_match` signal — a strong
corroboration that the same human is behind both accounts.

Returned in `SearchResponse.image_clusters`:

```jsonc
[
  {
    "size": 3,
    "platforms": ["github", "twitter", "instagram"],
    "representative_hash_hex": "f0e1c3a5b2d40000",
    "members": [
      { "avatar_url": "https://avatars.githubusercontent.com/u/123",
        "platform": "github",   "handle": "janedoe",
        "profile_url": "https://github.com/janedoe",
        "min_distance": 0 },
      { "avatar_url": "https://pbs.twimg.com/profile_images/...",
        "platform": "twitter",  "handle": "janedoe",
        "profile_url": "https://x.com/janedoe",
        "min_distance": 4 },
      { "avatar_url": "https://scontent.cdninstagram.com/v/...",
        "platform": "instagram","handle": "janedoe",
        "profile_url": "https://www.instagram.com/janedoe/",
        "min_distance": 8 }
    ]
  }
]
```

`min_distance` is the Hamming distance to the closest other member of
the cluster. 0 means byte-identical, ≤ 4 is essentially the same
image, ≤ 12 is the cutoff for "very likely same image".

The clustering uses a single-link / union-find algorithm — see
`backend/app/osint/image_match.py:cluster_by_hash`.

Avatar fetches deliberately **bypass** the platform-owned domain
denylist (since legitimate avatars live on
`avatars.githubusercontent.com`, `pbs.twimg.com`, etc.) but still
respect the SSRF guard, robots.txt, the per-host throttle, and a 4 MB
hard cap.

### Promotion to `image` Findings

Each cluster spanning ≥ 2 platforms is also written into the FindingStore
as a first-class `image` Finding, keyed by `image::sha:<hash-hex>`. The
Finding is linked to every social_profile and username it ties together,
so the identity graph shows avatars as their own nodes. This means:

- Two future searches that rediscover the same avatar produce a
  **stable** image identifier (same hash → same key).
- The graph view can show "this avatar links these 3 profiles" as one
  node + three edges instead of inferred connections.
- The image Finding inherits its own confidence (≥ 75 typically — one
  PROFILE_HIT for the cluster + IMAGE_MATCH bonuses).

### Avatar source priority

The fingerprint parsers try multiple metadata sources in order, so we
get a usable avatar even when the page is blocked:

1. `og:image:secure_url` / `og:image`
2. `twitter:image` / `twitter:image:src`
3. JSON-LD `image` field (string, `{url:...}` dict, or array)
4. JSON-LD `thumbnailUrl` / `logo`
5. `<link rel="image_src">`
6. `<link rel="apple-touch-icon">` (favicons skipped)
7. Per-platform CSS selector (`img.avatar-user` for GitHub, etc.) — runs
   first when applicable, since it's the most specific signal.

---

## Finding schema (signal-scored)

The central output of the platform. Confidence is a **clamped sum of
explicit signal deltas** — interpretable, auditable, easy to tune.

```jsonc
{
  "key":  "username::janedoe",
  "type": "username",
  "value": "janedoe",
  "confidence": 75,
  "verified": true,                    // confidence >= 70 AND has a non-seed positive signal
  "label": "likely",                   // see tiers below
  "signals": [
    { "kind": "profile_hit",            "delta":  15, "reason": "handle 'janedoe' confirmed on 3 platform(s)", "source_url": "urn:engine:probe:janedoe" },
    { "kind": "cross_platform_handle",  "delta":  25, "reason": "same handle 'janedoe' confirmed on 3 platforms: github, youtube, instagram" },
    { "kind": "name_match",             "delta":  20, "reason": "display names match across github/janedoe and youtube/janedoe" },
    { "kind": "link_reuse",             "delta":  15, "reason": "website 'https://azhar.dev' linked from 2 different profiles" }
  ],
  "match_reasons": [ /* derived from signals where delta > 0 */ ],
  "sources": [
    { "url": "https://github.com/janedoe",   "title": "github profile for janedoe",   "source_type": "profile" },
    { "url": "https://www.youtube.com/@janedoe","title": "youtube profile for janedoe", "source_type": "profile" }
  ],
  "related_to":  ["name::azhar baloch", "email::azhar@azhar.dev"],
  "first_seen":  "2026-04-30T10:11:13+00:00",
  "last_seen":   "2026-04-30T10:11:17+00:00"
}
```

### Signal kinds and default deltas

Defined in `app/osint/verification.py:SIGNAL_DELTA`. Tune to taste.

| `kind` | delta | when applied |
|---|---:|---|
| `seed`                    | +55 | the original input (per provided field) |
| `profile_hit`             | +30 | 200 OK on a known platform's profile URL |
| `profile_hit_redirect`    | +10 | 3xx response from a profile probe (weaker) |
| `cross_platform_handle`   | +30 | same handle confirmed on ≥2 platforms |
| `name_match`              | +25 | display name matches another finding (≥0.85 sim) |
| `bio_reuse`               | +20 | identical bio text on multiple profiles |
| `link_reuse`              | +20 | same website linked from multiple profiles |
| `email_reuse`             | +15 | same email in multiple profile bios |
| `image_match`             | +20 | same avatar (Hamming ≤ 12) on ≥2 platforms |
| `profile_crosslink`       | +10 | one profile explicitly mentions another |
| `rdap_confirmed`          | +30 | domain has a public RDAP record |
| `extracted_from_bio`      | +15 | value parsed from a verified profile bio |
| `extracted_from_rdap`     | +20 | value came from a public RDAP contact |
| `generic_platform_text`   | -30 | text matches a known platform template |
| `weak_similarity`         | -30 | weak tie to seed (`relevance_to_seed` < 0.5) |
| `unrelated_domain`        | -40 | domain is platform-owned / not personal |

### Confidence tiers

| range | label | UI default |
|---|---|---|
| 85 – 100 | `verified`   | shown — VERIFIED tier |
| 70 –  84 | `high`       | shown — HIGH CONFIDENCE / actionable |
| 50 –  69 | `possible`   | shown — POSSIBLE MATCH |
|  0 –  49 | `unverified` | hidden by default (lower the filter to reveal) |

`verified` (boolean) is `true` when `confidence ≥ 70` AND there is at
least one positive non-`seed` signal — i.e. anything in the `verified`
or `high` label tiers that has been corroborated by something other
than the user's input.

---

## `GET /api/search/stream` (Server-Sent Events)

```js
const sse = new EventSource("/api/search/stream?kind=username&value=janedoe");
sse.addEventListener("stage",    e => console.log(JSON.parse(e.data)));
sse.addEventListener("finding",  e => console.log(JSON.parse(e.data).finding));
sse.addEventListener("snapshot", e => console.log(JSON.parse(e.data).snapshot));
sse.addEventListener("complete", e => { console.log(JSON.parse(e.data).payload); sse.close(); });
sse.addEventListener("error",    e => sse.close());
```

| event       | payload |
|-------------|---------|
| `stage`     | `{ "stage": "probe", "detail": "checking 1 candidate handle(s)" }` |
| `finding`   | `{ "finding": Finding }` — emitted as each Finding is created or updated |
| `snapshot`  | `{ "snapshot": ProfileSnapshot }` — when a profile page is fetched |
| `result`    | `{ "payload": SearchResponse }` — pre-persistence payload |
| `complete`  | `{ "payload": SearchResponse }` — final, with `id` |
| `error`     | `{ "detail": "..." }` |

The stream sends `: keepalive` comments every 15 s when idle.

---

## Pipeline overview

`POST /api/search` and the SSE endpoint share one engine
(`app/osint/correlation.py:CorrelationEngine.run`):

1. **Dorks** — `osint/dorks.py` generates per-kind dork queries (free, no crawl).
2. **Candidate handles** — derived from the seed (e.g. an email's local-part, name → `firstlast`).
3. **Probe** — `osint/username_check.py` issues one anonymous GET per known platform (~17 sites).
4. **Fetch** — `osint/profile_match.py` + `osint/fingerprints.py` extract ONLY the user's own content (display name, bio, personal links — not page chrome). Pages flagged as blocked or generic are skipped.
5. **Fold-in** — every email / handle / link / phone in those bios passes through the **relevance gate** (`osint/relevance.py`) before becoming a Finding. Anything that fails (CDN URL, footer link, generic OG text, role mailbox) is silently suppressed; the count is reported back as `suppressed_count`.
6. **Recursive probe** — newly discovered handles get one extra probe pass, capped at 4.
7. **Cross-platform corroboration** — same handle on ≥2 platforms → `+25 cross_platform_handle` bonus. Same website linked from ≥2 profiles → `+15 link_reuse`. Same email in ≥2 bios → `+15 email_reuse`.
8. **RDAP** — for any non-mailbox, non-platform domain, fetch `https://rdap.org/domain/X`; turn registrant email / phone / name into Findings.
9. **Name reinforcement** — pairs of profiles with high display-name similarity grant their underlying username Findings a `+20 name_match`.
10. **Persist + return** — Findings are deduplicated, scored, and the full payload is stored in `search_records.payload`.

All HTTP traffic is governed by:
- `core/ethics.py` — SSRF block (private IPs / loopback / cloud-metadata) + robots.txt
- `core/rate_limit.py` — per-IP sliding window + per-host throttle

---

## Errors

```json
{ "detail": "rate limit exceeded" }
```

For SSE, errors are delivered as an `event: error` (the stream itself is always HTTP 200).

 claude# OSINT Platform

A modular, ethical Open-Source Intelligence (OSINT) web application.
Enter a **name**, **email**, **phone**, or **username** and the platform
generates Google dorks, probes public profile sites, scrapes the URLs it
discovers (respecting `robots.txt`), and correlates findings into a
single identity graph.

> **For ethical, lawful intelligence work only.**
> Public sources only. No login bypass. No private API abuse. No
> exploitation. Respects `robots.txt` and per-host rate limits.

---

## Features

| Area | What's built |
|---|---|
| **Search inputs** | name, email, phone, username — single OR multi-input bundle (`POST /api/search/bundle`) |
| **Image-based correlation** | dHash perceptual fingerprint of every fetched avatar; clusters of size ≥ 2 across distinct platforms grant `+20 image_match` and become first-class `image` Findings |
| **Image proxy** | `GET /api/image?url=…` — server-side fetch + LRU cache + SSRF guard; defeats CDN hot-link / Referer blocks so avatars actually render in the browser |
| **Avatar extraction priority** | per-platform selectors → `og:image` → `twitter:image` → JSON-LD `image` → `<link rel="image_src">` → direct-avatar URL fallback (GitHub `/USER.png`, GitLab) — even login-walled pages usually expose one of these. See [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md) |
| **Platform-default filter** | rejects site-marketing share-images (GitHub social.png, Twitter sticky default, Instagram static logos, etc.) so we never poison clustering with branding |
| **Email → Gravatar promotion** | when the seed is an email, the engine synthesizes a `gravatar` snapshot up-front so it joins the avatar cluster pipeline alongside discovered social profiles |
| **Cross-identity correlation** | iterative engine — handles found in bios get re-probed on the next pass |
| **Structured Findings** | every discovered identifier becomes one `Finding` with confidence + verification + signal-trail + per-source URLs |
| **Signal-based confidence** | additive deltas (`+25 cross_platform`, `+20 name_match`, `-30 generic_text`, `-40 unrelated_domain`, …) clamped to 0–100 — auditable per Finding |
| **Verified tiers** | `verified` ≥ 85 · `high` ≥ 70 (actionable) · `possible` ≥ 50 · `unverified` < 50 (hidden by default) |
| **Noise filtering** | platform-owned domain denylist + path-pattern gate + static-asset filter + generic-text detector + role-mailbox filter — see [NOISE_MODEL.md](NOISE_MODEL.md) |
| **Per-platform fingerprints** | site-specific selectors for GitHub, GitLab, Dev.to, Medium, Reddit, YouTube, About.me, Keybase — extracts user content, not page chrome |
| **Live SSE stream** | `GET /api/search/stream` emits `stage` / `finding` / `snapshot` / `complete` events as evidence appears |
| **Dork engine** | LinkedIn, GitHub, Twitter/X, Facebook, paste sites, indexed PDFs, etc. — opens in Google / Bing / DuckDuckGo |
| **Scraping** | polite async crawler, robots.txt-aware, host throttling, depth/page caps, private-IP / SSRF block |
| **Username correlation** | 17+ public profile sites (GitHub, Reddit, Medium, dev.to, Keybase, …) |
| **Profile snapshots** | display name, bio, avatar, inline emails / handles / outbound links per platform |
| **WHOIS / RDAP** | public registry lookup (`rdap.org`) for any non-mailbox domain → registrant email/phone/name as Findings |
| **Email enrichment** | RFC validation, Gravatar lookup, optional HIBP (only if API key set) |
| **Phone enrichment** | offline `libphonenumber` — region, carrier, line type, timezone |
| **Confidence scoring** | per-Finding noisy-OR + cross-platform corroboration bonus |
| **Dashboard** | dark cybersecurity theme, Findings cards (filter by type/confidence/verified), live updates, identity graph, timeline, snapshots, RDAP panel |
| **Persistence** | SQLite by default; PostgreSQL via env switch |
| **Export** | CSV + PDF (ReportLab) per record |
| **History** | search history, replay any past search |
| **Rate limiting** | sliding-window per IP |
| **Deployment** | single Dockerfile + `docker-compose.yml` (API + Postgres) |

---

## Project structure

```
osint-platform/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI factory + static mount
│   │   ├── config.py               # Pydantic settings
│   │   ├── database.py             # async SQLAlchemy
│   │   ├── models.py               # SearchRecord ORM
│   │   ├── schemas.py              # Pydantic API contracts
│   │   ├── api/
│   │   │   ├── search.py           # POST /api/search
│   │   │   ├── dorks.py            # POST /api/dorks
│   │   │   ├── history.py          # GET/DELETE /api/history
│   │   │   └── export.py           # GET /api/export/{id}/{csv|pdf}
│   │   ├── core/
│   │   │   ├── ethics.py           # robots.txt + SSRF guard
│   │   │   ├── rate_limit.py       # IP + per-host throttle
│   │   │   └── logger.py
│   │   ├── osint/
│   │   │   ├── correlation.py      # ⭐ orchestration engine
│   │   │   ├── dorks.py            # dork generator
│   │   │   ├── scraper.py          # polite async fetcher
│   │   │   ├── username_check.py   # multi-site username probe
│   │   │   ├── email_check.py      # email enrichment
│   │   │   ├── phone_check.py      # phone parsing
│   │   │   ├── extractors.py       # regex + social link extraction
│   │   │   ├── metadata.py         # OG / JSON-LD parser
│   │   │   └── confidence.py       # scoring
│   │   └── static/                 # dark-themed dashboard (HTML/CSS/JS)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── docker-compose.yml
├── README.md
├── ARCHITECTURE.md
└── DEPLOYMENT.md
```

---

## Quick start (local)

The platform has two independent UIs — pick whichever fits:

### Option A — Premium Next.js dashboard (recommended)

```bash
# 1) Backend
cd osint-platform/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload                   # → http://localhost:8000

# 2) Frontend (in a second terminal)
cd osint-platform/frontend
cp .env.local.example .env.local
npm install                                     # ~ 90 s first time
npm run dev                                     # → http://localhost:3000
```

Open <http://localhost:3000> for the cyber-intelligence dashboard
(animated grid, glass cards, Cytoscape graph, ⌘K command palette,
live SSE terminal). API spec at <http://localhost:8000/docs>.

### Option B — Static fallback (no Node required)

The backend also serves a self-contained single-file dashboard at
<http://localhost:8000> using only Tailwind CDN + vanilla JS — useful
when you can't or don't want to run Node.

## Quick start (Docker)

```bash
cd osint-platform
cp backend/.env.example backend/.env
# edit DATABASE_URL to use the postgres service:
#   DATABASE_URL=postgresql+psycopg2://osint:osint@db:5432/osint
docker compose up --build
```

Compose brings up three services:
- `osint-web` (Next dashboard) → http://localhost:3000
- `osint-api` (FastAPI)        → http://localhost:8000
- `osint-db`  (Postgres 16)    → localhost:5432

---

## API surface

See [`API.md`](API.md) for full request/response shapes and the Finding schema.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/search` | Run full correlation. Body: `{ "kind": "name|email|phone|username", "value": "…" }` |
| `GET`  | `/api/search/stream?kind=…&value=…` | **SSE** — live stream of stages, findings, snapshots. |
| `POST` | `/api/dorks` | Just generate dorks (no crawling). |
| `GET`  | `/api/history` | Paginated history. |
| `GET`  | `/api/history/{id}` | Full payload for one search. |
| `DELETE`| `/api/history/{id}` | Remove. |
| `GET`  | `/api/export/{id}/csv` | CSV export. |
| `GET`  | `/api/export/{id}/pdf` | PDF report. |
| `GET`  | `/api/health` | Liveness probe. |

## Configuration (`backend/.env`)

See [`.env.example`](backend/.env.example). All optional API keys are off
by default — the platform works fully without them.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | sqlite | switch to `postgresql+psycopg2://…` for production |
| `RESPECT_ROBOTS_TXT` | `true` | leave on |
| `MAX_PAGES_PER_SEARCH` | `15` | cap on crawled pages |
| `RATE_LIMIT_PER_MINUTE` | `30` | per-IP |
| `HIBP_API_KEY` | empty | optional — public breach lookup |
| `SERPAPI_KEY` | empty | optional — paid SERP API for advanced dork execution |

---

## Ethics (read this)

This tool is intended for **defensive security**, **journalism**,
**recruiting**, **fraud investigation**, and **personal-data audits**
("what does the internet know about me?").

The platform refuses to:

- Authenticate to any third-party service on a user's behalf.
- Fetch from private IPs, loopback, or cloud-metadata endpoints.
- Crawl URLs disallowed by `robots.txt` (when enabled).
- Brute-force, enumerate accounts, or attempt credential guessing.

Operators are responsible for:

- Compliance with local privacy law (GDPR, CCPA, local equivalents).
- Obtaining authorization before profiling third parties.
- Not republishing scraped data in violation of the source site's ToS.

If you can't say *out loud* who authorized the search — don't run it.

---

## Roadmap (next things to build)

The current platform deliberately uses lightweight infrastructure
(SQLite/Postgres + asyncio + httpx) to keep ops simple. The next
scaling tier, when corpus or concurrency demands it:

| Component | Why |
|---|---|
| **Playwright** worker | Render JS-heavy profile pages (Instagram / TikTok / X public timelines) — current `httpx` fetch only sees the SSR shell. |
| **Selectolax** parser | 5–10× faster than BeautifulSoup; switch when crawl volume justifies the dep. |
| **Redis queue** + workers | Move probe / fetch / RDAP into background jobs; the API just returns a job id and streams results over SSE / WebSocket. |
| **Neo4j** graph DB | When the FindingStore graph grows past a few hundred nodes per search, queries like "which seeds share a domain?" want graph indexes, not JSON columns. |
| **Embeddings-based bio matching** | Replace `difflib.SequenceMatcher` with a sentence-transformers model for cross-language / paraphrased bio matching. |

These are real next steps — they are not in the current build, and
adding them requires data + scale to justify the operational cost.

## License

MIT — see source headers.
# OSI

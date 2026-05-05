# Architecture

## Overview

Three concentric layers, all in one Python process by default:

```
                  ┌──────────────────────────────────────────────┐
                  │  Frontend (HTML + Tailwind CDN + vis-network)│
                  │  served as static files by FastAPI           │
                  └──────────────────────────────────────────────┘
                                       │ JSON over HTTP
                                       ▼
                  ┌──────────────────────────────────────────────┐
                  │  FastAPI HTTP layer  (app/api/*)             │
                  │   /api/search   /api/dorks                   │
                  │   /api/history  /api/export                  │
                  └──────────────────────────────────────────────┘
                                       │ in-process calls
                                       ▼
                  ┌──────────────────────────────────────────────┐
                  │  OSINT engine  (app/osint/*)                 │
                  │   correlation • dorks • scraper • usernames  │
                  │   extractors  • email/phone analyzers        │
                  │   confidence  • metadata                     │
                  └──────────────────────────────────────────────┘
                          │                         │
                ┌─────────▼──────────┐     ┌────────▼─────────┐
                │  Public web        │     │  SQL store       │
                │  (httpx + bs4)     │     │  (SQLAlchemy)    │
                │  via robots.txt    │     │  SQLite default, │
                │  + host throttle   │     │  Postgres in prod│
                └────────────────────┘     └──────────────────┘
```

## Request flow — `POST /api/search`

1. **API layer** validates the body against `SearchRequest` and consults
   the `IPRateLimiter` (sliding-window over 60 s).
2. **Correlation engine** (`osint/correlation.py`) drives the pipeline:
   - **Dorks** are generated for the input kind/value (`osint/dorks.py`).
   - **Candidate usernames** are derived from the input (e.g. an email's
     local-part, a name's `first.last` permutations).
   - **Username probe** (`osint/username_check.py`) issues one GET per
     known site (~17 platforms) and treats 200 + missing negative
     pattern as a probable hit.
   - **Crawl** (`osint/scraper.py`) fetches the URLs we already have
     (profile pages from the previous step) — never SERPs themselves.
     Each URL is filtered by `core/ethics.py` against:
       - private/loopback IPs (SSRF guard)
       - `robots.txt` (if `RESPECT_ROBOTS_TXT=true`)
     and rate-limited per-host.
   - **Extraction** runs regex extractors over the scraped text:
     emails, phones (validated by `phonenumbers`), `@handles`, and
     social links found in `<a href="…">`.
   - **Metadata** parses OG / Twitter Cards / JSON-LD.
   - **Confidence** combines all signals with a noisy-OR aggregator.
   - **Graph** is assembled — nodes for the original query, each
     username, each email/phone, each social profile; edges back to
     the query.
3. **API layer** persists a `SearchRecord` and returns the payload.

## Side-channel enrichment

When `kind == "email"` or `kind == "phone"`, the correlation result
also includes an `email_report` or `phone_report`:

- `email_check.py`: RFC validation; Gravatar HEAD; HIBP only if a key
  is configured.
- `phone_check.py`: offline `libphonenumber` analysis (E.164, region,
  carrier, line type, timezones).

## Persistence

Single table `search_records` storing the full JSON payload along with
a normalized `confidence` and `summary` for cheap listing. SQLite is
the default (`./data/osint.db`); set `DATABASE_URL` to
`postgresql+psycopg2://…` for production.

## Frontend

A single self-contained page under `app/static/`:
- Tailwind via CDN (no build step).
- `vis-network` for the identity graph.
- Vanilla JS controller (`app.js`) — tabs, fetch, dashboard render,
  history list, export buttons.

Served by FastAPI as static files; you can deploy a separate Next.js
frontend instead and point it at `/api/*` if you prefer.

## Deployment topology

| Environment | API | DB | Notes |
|---|---|---|---|
| Local dev | uvicorn `--reload` | SQLite file | `cd backend && uvicorn app.main:app --reload` |
| Single host | Docker `osint-api` | Postgres `osint-db` | `docker compose up --build` |
| Production | API behind a reverse proxy (Caddy/Nginx) with TLS | Managed Postgres | Set `ALLOWED_ORIGINS`, raise `RATE_LIMIT_PER_MINUTE` carefully |

## Threat model the platform protects against

| Threat | Mitigation |
|---|---|
| SSRF via attacker-supplied URL | `core/ethics.is_host_allowed` blocks private IPs / loopback / cloud-metadata hosts. The crawler only follows URLs already produced by username checks; it never crawls user-controlled URLs. |
| Robots.txt violation | `RobotsCache` per-domain; configurable kill-switch. |
| Resource exhaustion | `MAX_PAGES_PER_SEARCH`, `MAX_CRAWL_DEPTH`, per-host throttle, per-IP rate limit. |
| HTML injection in dashboard | All rendered fields go through `escapeHTML`. |
| Open API abuse | Sliding-window rate limit, CORS allow-list, suggested reverse proxy auth in production. |

## Where to extend

- **More platforms** — add to `osint/username_check.py:SITES`.
- **More dork patterns** — add to `osint/dorks.py:generate_for_*`.
- **AI entity matching** — slot a model behind `correlation._build_summary`
  to score whether two profiles refer to the same person.
- **Screenshot capture** — add a Playwright worker behind a queue and
  store image URLs in `payload.metadata_snippets[].screenshot`.
- **Multi-language UI** — wrap strings in `app.js` in an i18n dict.

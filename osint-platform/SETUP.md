# OSINT Platform — Developer Setup Guide

This guide gets a new contributor from a clean machine to a running stack
(backend + frontend + optional Elasticsearch + optional Postgres) in a few
minutes. It does not change any project code — it only documents and
automates installation.

For deeper architectural / production-deployment notes see `DEPLOYMENT.md`,
`ARCHITECTURE.md`, and `API.md`.

---

## 1. Prerequisites

| Tool          | Version            | Notes |
|---------------|--------------------|-------|
| Python        | 3.10 – 3.12        | backend (FastAPI + Uvicorn) |
| Node.js       | ≥ 18 (LTS)         | frontend (Next.js 14) |
| npm           | bundled with Node  | |
| curl          | any                | health checks in setup script |
| Docker        | ≥ 24 (optional)    | only if you prefer the all-in-one `docker compose` path |
| Elasticsearch | 8.x or 9.x (optional) | only if you want the verified-DB layer (see §3) |

Quick install of system packages:

```bash
# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y \
    python3 python3-venv python3-pip nodejs npm curl

# macOS (Homebrew)
brew install python node curl
```

---

## 2. One-shot setup (recommended)

From the `osint-platform/` directory:

```bash
# Linux / macOS
./setup.sh

# Windows (cmd.exe)
setup.bat
```

What the script does (idempotent — safe to re-run):

1. Checks Python / Node / npm / curl are present.
2. Creates `backend/.venv` if missing.
3. Installs `backend/requirements.txt` into the venv.
4. Copies `backend/.env.example` → `backend/.env` if missing (never overwrites).
5. Installs `frontend/node_modules` (`npm ci` if a lockfile exists, else `npm install`).
6. Probes Elasticsearch on `https://localhost:9200` and prints whether it found one.
7. Prints the exact commands to start the backend and frontend.

The script never starts long-running services for you — that's left to you so
you can choose which terminals to bind them to.

---

## 3. Elasticsearch setup (optional but recommended)

The platform works **without** Elasticsearch — leave `ES_ENABLED=false` in
`backend/.env` and the OSINT pipeline runs on its own. ES adds the
**Verified Local Database (100% trust)** layer that surfaces internal
authoritative records alongside web findings.

### 3.1 Install Elasticsearch

| Method | Command |
|---|---|
| Docker (fastest, single-node, dev) | `docker run -d --name es -p 9200:9200 -e "discovery.type=single-node" -e "xpack.security.enabled=true" -e "ELASTIC_PASSWORD=changeme" docker.elastic.co/elasticsearch/elasticsearch:8.15.1` |
| Ubuntu / Debian (apt) | follow [https://www.elastic.co/downloads/elasticsearch](https://www.elastic.co/downloads/elasticsearch) — installs to `/etc/elasticsearch/`, manage with `sudo systemctl start elasticsearch` |
| macOS (Homebrew) | `brew tap elastic/tap && brew install elastic/tap/elasticsearch-full && brew services start elastic/tap/elasticsearch-full` |

Compatible with **Elasticsearch 8.x and 9.x** (the Python client `elasticsearch[async]==8.15.1` pinned in `requirements.txt` works against both).

### 3.2 Confirm it's running

```bash
curl -sk -u elastic:<YOUR_PASSWORD> https://localhost:9200/
# → {"name":"…","cluster_name":"elasticsearch","version":{"number":"8.x.x"…}}
```

### 3.3 Wire the platform to it

Edit `backend/.env`:

```dotenv
ES_ENABLED=true
ES_URL=https://localhost:9200
ES_USER=elastic
ES_PASSWORD=<paste the password Elasticsearch printed at first start>
ES_INDEX=tc_index           # name of the index the engine queries
ES_VERIFY_CERTS=false       # set true if you have a real CA
ES_TIMEOUT=8
ES_MAX_HITS=25
```

> ⚠ **Variable names** — the project's code uses `ES_URL` / `ES_USER` /
> `ES_PASSWORD` / `ES_INDEX`. If you've seen the convention
> `ELASTICSEARCH_HOST` / `ELASTICSEARCH_PORT` / `INDEX_NAME` elsewhere, those
> are aliases used in some docs but the **authoritative variable names are
> the `ES_*` ones above** (defined in `app/config.py`).

### 3.4 Index initialization

The platform **does not auto-create** `tc_index`. Either:

- Bring your own data — load documents into `tc_index` with fields
  `NAME`, `PHONE`, `EMAIL`, `TAGS`, `ASONDATE` (case-sensitive). Example one-off
  document:

  ```bash
  curl -sk -u elastic:<PWD> -X POST "https://localhost:9200/tc_index/_doc" \
       -H 'Content-Type: application/json' \
       -d '{"NAME":"Jane Doe","PHONE":"5551234567","EMAIL":"jane@example.com","TAGS":"","ASONDATE":"2025-03-27"}'
  ```

- Or run the platform without ES (`ES_ENABLED=false`) — every other feature
  works unchanged.

---

## 4. Environment variables (`backend/.env`)

All variables and their defaults are documented in `backend/.env.example`.
Highlights:

| Variable | Default | What it controls |
|---|---|---|
| `APP_ENV` | `development` | `development` / `production` toggles |
| `DEBUG` | `true` | Uvicorn auto-reload + verbose logs |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Backend port |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/osint.db` | App state DB. Switch to Postgres for production: `postgresql+psycopg2://user:pass@host:5432/db` |
| `USER_AGENT` | `OSINT-Platform/1.0 …` | Sent on every outbound HTTP request |
| `REQUEST_TIMEOUT` | `10` | Seconds per crawl request |
| `MAX_CRAWL_DEPTH` | `1` | How deep the polite crawler follows |
| `MAX_PAGES_PER_SEARCH` | `15` | Per-search page cap |
| `RATE_LIMIT_PER_MINUTE` | `30` | Sliding-window per-IP API limit |
| `RESPECT_ROBOTS_TXT` | `true` | Always honor `robots.txt` |
| `SERPAPI_KEY` | _empty_ | Optional — enables paid-API search results |
| `HIBP_API_KEY` | _empty_ | Optional — enables breach lookups |
| `ES_ENABLED` | `false` | Toggle the verified-DB layer (see §3) |
| `ES_*`        | see `.env.example` | ES connection details |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:8000` | CORS allowlist |

**Frontend port** is fixed at `3000` (Next.js default; configurable in
`frontend/package.json` scripts if needed). The frontend talks to the backend
through Next.js rewrites — no env var required for local dev.

### Example `backend/.env` (minimal, no ES)

```dotenv
APP_NAME="OSINT Platform"
APP_ENV=development
DEBUG=true
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./data/osint.db
ES_ENABLED=false
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
```

---

## 5. Manual run instructions

If you don't want to use `setup.sh`, the equivalent manual steps:

### Backend (FastAPI + Uvicorn)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env                 # then edit values
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs live at `http://localhost:8000/docs`.
Static dashboard (works standalone, no Next.js needed): `http://localhost:8000/`.

### Frontend (Next.js)

```bash
cd frontend
npm install      # first time
npm run dev      # http://localhost:3000
```

Production build + start:

```bash
npm run build
npm run start
```

### Docker (everything in one go)

```bash
docker compose up --build
# api → http://localhost:8000
# web → http://localhost:3000
# db  → postgres on :5432
```

The compose file does not start Elasticsearch — run it separately (§3.1) and
point `backend/.env` at it.

---

## 6. First-time initialization

| Step | When needed | How |
|---|---|---|
| App database (`osint.db` or Postgres schema) | always | the FastAPI `lifespan` hook calls `init_db()` automatically on first start. No manual migration needed. |
| Elasticsearch `tc_index` | only if `ES_ENABLED=true` | not auto-created — load your own documents (see §3.4). |
| Static dashboard assets | always | served straight from `backend/app/static/` — nothing to build. |

---

## 7. Quick verification

After both servers are up:

```bash
# Backend health (also shows ES status)
curl http://localhost:8000/api/health | python3 -m json.tool

# Run a search via the API directly
curl -X POST http://localhost:8000/api/search \
     -H 'Content-Type: application/json' \
     -d '{"kind":"name","value":"Jane Doe"}'

# Open the dashboard
xdg-open http://localhost:8000/        # Linux
open http://localhost:8000/            # macOS
start http://localhost:8000/           # Windows
```

If the dashboard renders, the search returns JSON, and `/api/health` reports
`elasticsearch.reachable: true` (when ES is enabled) — you're good.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `setup.sh` says `Missing: node` | Node not on PATH | Install Node 18+, reopen the terminal |
| `pip install` fails on `psycopg2-binary` | Missing libpq headers | `sudo apt-get install -y libpq-dev` then re-run |
| `/api/health` says `elasticsearch.reachable: false` | ES off / wrong creds | Check `ES_URL`, `ES_USER`, `ES_PASSWORD` in `backend/.env` |
| Dashboard loads but no DB records | `ES_ENABLED=false` or `tc_index` empty | Set `ES_ENABLED=true`, load data into `tc_index` |
| `address already in use` on :8000 | Old uvicorn still running | `lsof -ti:8000 \| xargs kill` (Linux/macOS) or Task Manager (Windows) |
| Frontend can't reach backend | CORS block | Make sure `ALLOWED_ORIGINS` in `.env` includes your frontend URL |

---

## 9. What this guide does NOT change

- No project source code is modified.
- No existing config files are overwritten.
- No services are started or stopped automatically.
- `DEPLOYMENT.md`, `docker-compose.yml`, `Dockerfile`, `requirements.txt`,
  `package.json`, `.env.example`, and the application code remain exactly as
  shipped.

This file plus `setup.sh` / `setup.bat` are pure additions.

# Deployment Guide

## 1. Local development

### Backend (FastAPI)

```bash
cd osint-platform/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Static fallback dashboard: <http://localhost:8000>
- OpenAPI:                   <http://localhost:8000/docs>
- Health:                    <http://localhost:8000/api/health>

### Frontend (Next.js — premium dashboard)

```bash
cd osint-platform/frontend
cp .env.local.example .env.local
npm install
npm run dev
```

- Premium dashboard: <http://localhost:3000>

The Next dev server proxies `/api/*` to the FastAPI backend (set
`NEXT_PUBLIC_API_BASE` to point at a different host).

## 2. Docker (single host)

```bash
cd osint-platform
cp backend/.env.example backend/.env
# Edit backend/.env — set DATABASE_URL to point at the bundled postgres:
# DATABASE_URL=postgresql+psycopg2://osint:osint@db:5432/osint
docker compose up --build -d
docker compose logs -f api
```

The compose file ships:
- `osint-web` – Next.js production server, port 3000
- `osint-api` – FastAPI + uvicorn, port 8000
- `osint-db`  – PostgreSQL 16 (named volume `pg-data`)

To take it down: `docker compose down` (data persists).
To wipe data:    `docker compose down -v`.

## 3. Production checklist

### TLS & reverse proxy

Run behind Caddy / Nginx / Traefik and terminate TLS there. Example
Caddyfile:

```Caddyfile
osint.example.com {
  encode zstd gzip
  reverse_proxy 127.0.0.1:8000
}
```

### Hardening

- Set `APP_ENV=production`, `DEBUG=false`.
- Restrict `ALLOWED_ORIGINS` to your real frontend origin.
- Put the dashboard behind your existing SSO via the reverse proxy
  (e.g. Caddy `forward_auth`, Nginx + oauth2-proxy). The app does not
  ship a built-in user model on purpose — auth belongs at the edge.
- Pin `RATE_LIMIT_PER_MINUTE` to a sane value for your team size.
- Run on a non-root user (the Dockerfile already does).
- Ship logs to your aggregator: uvicorn writes to stdout.

### Database

For more than a handful of operators, switch to a managed Postgres
(RDS / Cloud SQL / Neon). Schema is auto-migrated on startup
(`Base.metadata.create_all`); for non-trivial schema evolution add
Alembic migrations.

### Scaling

The OSINT engine is asyncio-bound and largely IO-heavy. A single
`uvicorn --workers 4` process on a small VM handles dozens of concurrent
searches comfortably. To scale further:

- Move the username-probe + crawl into a background worker (RQ /
  Celery / arq) and stream results to the frontend over WebSockets.
- Cache `RobotsCache` and DNS hits in Redis so workers share state.

### Backups

Just back up the database. All payloads are stored as JSON in
`search_records.payload`.

## 4. Kubernetes (sketch)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: osint-api }
spec:
  replicas: 2
  selector: { matchLabels: { app: osint } }
  template:
    metadata: { labels: { app: osint } }
    spec:
      containers:
        - name: api
          image: ghcr.io/your-org/osint-platform:1.0.0
          ports: [{ containerPort: 8000 }]
          envFrom:
            - secretRef: { name: osint-env }
          readinessProbe:
            httpGet: { path: /api/health, port: 8000 }
          resources:
            requests: { cpu: 100m, memory: 256Mi }
            limits:   { cpu: 1,    memory: 1Gi  }
```

## 5. Optional integrations

| Service | Env var | What it unlocks |
|---|---|---|
| HaveIBeenPwned | `HIBP_API_KEY` | Breach counts on email enrichment. |
| SerpAPI | `SERPAPI_KEY` | (Hook ready, not yet wired) executes dork queries against Google's indexed results from a paid, ToS-safe path. |

The platform is fully usable without either — the dorks open directly
in the analyst's browser.

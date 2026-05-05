

#!/usr/bin/env bash
# ============================================================
# OSINT Platform — local setup (Linux / macOS)
# ------------------------------------------------------------
# Idempotent: safe to re-run. Never overwrites existing .env
# or venv. Never starts/stops system services. Prints what
# you need to do next instead of black-boxing the launch.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"

c_g() { printf '\033[1;32m%s\033[0m\n' "$*"; }
c_y() { printf '\033[1;33m%s\033[0m\n' "$*"; }
c_r() { printf '\033[1;31m%s\033[0m\n' "$*"; }
c_b() { printf '\033[1;36m%s\033[0m\n' "$*"; }
hr()  { printf '%s\n' "------------------------------------------------------------"; }

c_b "OSINT Platform — setup script"
hr

# ---------- 1. system dependencies ----------
c_g "[1/6] Checking system dependencies…"
need=()
command -v python3 >/dev/null 2>&1 || need+=("python3")
command -v pip3    >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1 || need+=("python3-pip")
command -v node    >/dev/null 2>&1 || need+=("node (>=18)")
command -v npm     >/dev/null 2>&1 || need+=("npm")
command -v curl    >/dev/null 2>&1 || need+=("curl")
if [ ${#need[@]} -gt 0 ]; then
  c_r "Missing: ${need[*]}"
  c_y "Install via your OS package manager (apt / brew / dnf), then re-run this script."
  c_y "Examples:"
  c_y "  Ubuntu/Debian: sudo apt-get install -y python3 python3-venv python3-pip nodejs npm curl"
  c_y "  macOS (brew):  brew install python node curl"
  exit 1
fi
echo "  python3: $(python3 --version)"
echo "  node:    $(node --version)"
echo "  npm:     $(npm --version)"
hr

# ---------- 2. backend virtualenv ----------
c_g "[2/6] Backend virtualenv at backend/.venv"
if [ -d "$VENV" ]; then
  echo "  existing venv detected — keeping it"
else
  python3 -m venv "$VENV"
  echo "  created"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip --quiet
hr

# ---------- 3. backend dependencies ----------
c_g "[3/6] Installing backend Python dependencies"
pip install -r "$BACKEND/requirements.txt"
hr

# ---------- 4. backend .env ----------
c_g "[4/6] Backend environment file"
if [ -f "$BACKEND/.env" ]; then
  echo "  backend/.env already exists — leaving untouched"
else
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  c_y "  created backend/.env from .env.example"
  c_y "  ⚠  Open backend/.env and set ES_PASSWORD if you plan to use Elasticsearch."
fi
hr

# ---------- 5. frontend ----------
c_g "[5/6] Installing frontend dependencies"
if [ -d "$FRONTEND/node_modules" ]; then
  echo "  node_modules already present — running npm ci to lock to package-lock.json"
  ( cd "$FRONTEND" && npm ci --no-audit --no-fund )
else
  ( cd "$FRONTEND" && npm install --no-audit --no-fund )
fi
hr

# ---------- 6. optional: Elasticsearch reachability probe ----------
c_g "[6/6] Optional Elasticsearch reachability probe"
ES_URL="${ES_URL:-https://localhost:9200}"
if curl -sk -m 3 -o /dev/null -w '%{http_code}' "$ES_URL" 2>/dev/null | grep -qE '^(200|401)$'; then
  echo "  ✓ Elasticsearch reachable at $ES_URL"
else
  c_y "  ⚠  No Elasticsearch detected at $ES_URL"
  c_y "     The platform runs WITHOUT ES — leave ES_ENABLED=false in backend/.env."
  c_y "     To enable: install Elasticsearch 8.x or 9.x, set ES_ENABLED=true and ES_PASSWORD."
fi
hr

# ---------- next steps ----------
c_b "Setup complete."
echo
echo "Start the BACKEND in one terminal:"
echo "  source $VENV/bin/activate"
echo "  cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
echo
echo "Start the FRONTEND in another terminal:"
echo "  cd frontend && npm run dev    # http://localhost:3000"
echo
echo "Or use Docker for the whole stack:"
echo "  docker compose up --build     # API:8000, Web:3000, Postgres:5432"
echo
echo "Static dashboard (no Next.js needed): http://localhost:8000/"
echo "API docs:                              http://localhost:8000/docs"

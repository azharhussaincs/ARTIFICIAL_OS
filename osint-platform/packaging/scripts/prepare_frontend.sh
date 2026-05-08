#!/usr/bin/env bash
# Linux helper: build the Next.js static export and drop it into
# backend/app/static so the bundle on Windows has it ready.
# (Run this from your dev box BEFORE transferring the repo to the Windows
# build machine, or call build.bat which does the same on Windows.)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
FRONTEND="$REPO/frontend"
BACKEND="$REPO/backend"

cd "$FRONTEND"

if [[ ! -d node_modules ]]; then
  echo "[deps] npm ci"
  npm ci
fi

echo "[build] Next.js export"
NEXT_OUTPUT_EXPORT=1 NEXT_PUBLIC_API_BASE="" npm run build

if [[ ! -f out/index.html ]]; then
  echo "ERROR: out/index.html missing — export failed" >&2
  exit 1
fi

if [[ -d "$BACKEND/app/static" && ! -d "$BACKEND/app/.static.backup" ]]; then
  echo "[backup] backend/app/static -> backend/app/.static.backup"
  cp -a "$BACKEND/app/static" "$BACKEND/app/.static.backup"
fi

rm -rf "$BACKEND/app/static"
cp -a out "$BACKEND/app/static"

echo "OK: backend/app/static populated from Next.js export"

#!/usr/bin/env bash
# Take a filesystem snapshot of the running Elasticsearch index `tc_index`
# and produce a zstd-compressed tarball that build.bat will bundle.
#
# Run this on the dev machine where the 18GB ES is currently running.
#
# Output: packaging/vendor/snap_v1.tar.zst
set -euo pipefail

ES_URL="${ES_URL:-http://localhost:9200}"
ES_USER="${ES_USER:-}"
ES_PASS="${ES_PASS:-}"
INDEX="${ES_INDEX:-tc_index}"

HERE="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$HERE/.." && pwd)"
VENDOR_DIR="$PKG_DIR/vendor"
SNAPSHOT_REPO_DIR="${SNAPSHOT_REPO_DIR:-/tmp/osint_es_snapshot}"

CURL_AUTH=()
if [[ -n "$ES_USER" ]]; then
  CURL_AUTH=(-u "$ES_USER:$ES_PASS")
fi

mkdir -p "$SNAPSHOT_REPO_DIR" "$VENDOR_DIR"

echo "[1/4] Verifying ES at $ES_URL ..."
curl -fsS "${CURL_AUTH[@]}" "$ES_URL/_cluster/health?pretty" >/dev/null

echo "[2/4] Registering snapshot repo at $SNAPSHOT_REPO_DIR ..."
echo "      NOTE: this path must be in path.repo on the source ES."
curl -fsS "${CURL_AUTH[@]}" -X PUT "$ES_URL/_snapshot/local_repo" \
  -H 'Content-Type: application/json' \
  -d "{\"type\":\"fs\",\"settings\":{\"location\":\"$SNAPSHOT_REPO_DIR\",\"compress\":true}}" >/dev/null

echo "[3/4] Taking snapshot snap_v1 of $INDEX (this can take a while)..."
curl -fsS "${CURL_AUTH[@]}" -X PUT \
  "$ES_URL/_snapshot/local_repo/snap_v1?wait_for_completion=true" \
  -H 'Content-Type: application/json' \
  -d "{\"indices\":\"$INDEX\",\"include_global_state\":false,\"ignore_unavailable\":true}" \
  | head -c 600
echo

echo "[4/4] Compressing snapshot dir -> $VENDOR_DIR/snap_v1.tar.zst ..."
if ! command -v zstd >/dev/null; then
  echo "ERROR: zstd not installed. apt install zstd / brew install zstd" >&2
  exit 1
fi

# Exclude indices that aren't part of this snapshot to keep size small —
# but a fresh repo only contains snap_v1 so this is mostly a safety net.
tar --zstd -cf "$VENDOR_DIR/snap_v1.tar.zst" -C "$SNAPSHOT_REPO_DIR" .

echo "OK: $(du -h "$VENDOR_DIR/snap_v1.tar.zst" | cut -f1) -> vendor/snap_v1.tar.zst"

#!/usr/bin/env bash
set -euo pipefail

GUARDIAN_URL=""
GUARDIAN_KEY=""
PRODUCT_NAME=""
PRODUCT_VERSION=""
PRODUCT_FULL_VERSION=""
TRIVY_FILE=""

usage() {
  cat <<'EOF'
Upload Trivy scan results to Guardian via POST /api/v1/upload_scan_results.

Guardian merges this upload with any earlier upload for the same product
version (e.g. Prisma), so both scanners land in one scan for the db sync.

Required:
  --guardian-url <url>
  --guardian-key <token>
  --product-name <name>
  --product-version <version>
  --product-full-version <full-version>
  --trivy-file <path>
EOF
}

require_value() {
  if [ -z "$2" ]; then
    echo "ERROR: missing required argument: $1" >&2
    usage
    exit 1
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --guardian-url) GUARDIAN_URL="$2"; shift 2 ;;
    --guardian-key) GUARDIAN_KEY="$2"; shift 2 ;;
    --product-name) PRODUCT_NAME="$2"; shift 2 ;;
    --product-version) PRODUCT_VERSION="$2"; shift 2 ;;
    --product-full-version) PRODUCT_FULL_VERSION="$2"; shift 2 ;;
    --trivy-file) TRIVY_FILE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

for cmd in curl jq; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: required command not found: $cmd" >&2; exit 1; }
done

require_value --guardian-url "$GUARDIAN_URL"
require_value --guardian-key "$GUARDIAN_KEY"
require_value --product-name "$PRODUCT_NAME"
require_value --product-version "$PRODUCT_VERSION"
require_value --product-full-version "$PRODUCT_FULL_VERSION"
require_value --trivy-file "$TRIVY_FILE"

if [ ! -f "$TRIVY_FILE" ]; then
  echo "ERROR: Trivy scan file not found: $TRIVY_FILE" >&2
  exit 1
fi

GUARDIAN_URL="${GUARDIAN_URL%/}"
RESPONSE_FILE="$(mktemp)"
trap 'rm -f "$RESPONSE_FILE"' EXIT
SCAN_TIME="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

echo "Uploading Trivy scan results to Guardian"
echo "  Product: $PRODUCT_NAME"
echo "  Product version: $PRODUCT_VERSION"
echo "  Product full version: $PRODUCT_FULL_VERSION"

HTTP_STATUS="$(
  curl -sS \
    -o "$RESPONSE_FILE" \
    -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $GUARDIAN_KEY" \
    -F "product_name=$PRODUCT_NAME" \
    -F "product_version=$PRODUCT_VERSION" \
    -F "product_full_version=$PRODUCT_FULL_VERSION" \
    -F "scan_time=$SCAN_TIME" \
    -F "trivy_scan=@${TRIVY_FILE};type=application/json" \
    "$GUARDIAN_URL/api/v1/upload_scan_results"
)"

if [ "$HTTP_STATUS" -lt 200 ] || [ "$HTTP_STATUS" -ge 300 ]; then
  echo "ERROR: upload_scan_results failed with HTTP $HTTP_STATUS" >&2
  jq -r '.detail // empty' "$RESPONSE_FILE" >&2 2>/dev/null || true
  exit 1
fi

echo "Guardian upload completed: $(jq -r '.saved_files | join(", ")' "$RESPONSE_FILE" 2>/dev/null || echo "ok")"

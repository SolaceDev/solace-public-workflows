#!/usr/bin/env bash
set -euo pipefail

GUARDIAN_URL=""
GUARDIAN_KEY=""
PRODUCT_NAME=""
PRODUCT_VERSION=""
PRODUCT_FULL_VERSION=""
PRISMA_FILE=""
PRISMA_SCAN_URL=""

usage() {
  cat <<'EOF'
Upload Prisma scan results to Guardian via POST /api/v1/upload_scan_results.

Required:
  --guardian-url <url>
  --guardian-key <token>
  --product-name <name>
  --product-version <version>
  --product-full-version <full-version>
  --prisma-file <path>

Optional:
  --prisma-scan-url <url>
  -h, --help
EOF
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $cmd" >&2
    exit 1
  fi
}

require_value() {
  local flag="$1"
  local value="$2"
  if [ -z "$value" ]; then
    echo "ERROR: missing required argument: $flag" >&2
    usage
    exit 1
  fi
}

append_step_summary() {
  local line="$1"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '%s\n' "$line" >> "$GITHUB_STEP_SUMMARY"
  fi
}

print_response() {
  local file="$1"
  if jq -e . "$file" >/dev/null 2>&1; then
    jq . "$file"
  else
    cat "$file"
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --guardian-url)
      GUARDIAN_URL="$2"
      shift 2
      ;;
    --guardian-key|--guardian-token)
      GUARDIAN_KEY="$2"
      shift 2
      ;;
    --product-name)
      PRODUCT_NAME="$2"
      shift 2
      ;;
    --product-version)
      PRODUCT_VERSION="$2"
      shift 2
      ;;
    --product-full-version)
      PRODUCT_FULL_VERSION="$2"
      shift 2
      ;;
    --prisma-file)
      PRISMA_FILE="$2"
      shift 2
      ;;
    --prisma-scan-url)
      PRISMA_SCAN_URL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_command curl
require_command jq

require_value --guardian-url "$GUARDIAN_URL"
require_value --guardian-key "$GUARDIAN_KEY"
require_value --product-name "$PRODUCT_NAME"
require_value --product-version "$PRODUCT_VERSION"
require_value --product-full-version "$PRODUCT_FULL_VERSION"
require_value --prisma-file "$PRISMA_FILE"

if [ ! -f "$PRISMA_FILE" ]; then
  echo "ERROR: Prisma scan file not found: $PRISMA_FILE" >&2
  exit 1
fi

GUARDIAN_URL="${GUARDIAN_URL%/}"
RESPONSE_FILE="$(mktemp)"
SCAN_TIME="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

SCAN_URLS_JSON='{}'
if [ -n "$PRISMA_SCAN_URL" ]; then
  SCAN_URLS_JSON="$(jq -cn --arg prisma "$PRISMA_SCAN_URL" '{prisma: $prisma}')"
fi

echo "Uploading Prisma scan results to $GUARDIAN_URL/api/v1/upload_scan_results"
echo "  Product: $PRODUCT_NAME"
echo "  Product version: $PRODUCT_VERSION"
echo "  Product full version: $PRODUCT_FULL_VERSION"
echo "  Prisma file: $PRISMA_FILE"
echo "  Scan time: $SCAN_TIME"

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
    -F "scan_urls=$SCAN_URLS_JSON" \
    -F "prisma_scan=@${PRISMA_FILE};type=application/json" \
    "$GUARDIAN_URL/api/v1/upload_scan_results"
)"

if [ "$HTTP_STATUS" -lt 200 ] || [ "$HTTP_STATUS" -ge 300 ]; then
  echo "ERROR: upload_scan_results failed with HTTP $HTTP_STATUS" >&2
  print_response "$RESPONSE_FILE"
  exit 1
fi

S3_BUCKET="$(jq -r '.s3_bucket' "$RESPONSE_FILE")"
S3_PATH="$(jq -r '.s3_path' "$RESPONSE_FILE")"
SAVED_FILES="$(jq -r '.saved_files | join(",")' "$RESPONSE_FILE")"

echo "Guardian upload completed"
echo "  S3 bucket: $S3_BUCKET"
echo "  S3 path: $S3_PATH"
echo "  Saved files: $SAVED_FILES"

append_step_summary "### Guardian Prisma Upload"
append_step_summary "- Product: \`$PRODUCT_NAME\`"
append_step_summary "- Product version: \`$PRODUCT_VERSION\`"
append_step_summary "- Product full version: \`$PRODUCT_FULL_VERSION\`"
append_step_summary "- S3 bucket: \`$S3_BUCKET\`"
append_step_summary "- S3 path: \`$S3_PATH\`"

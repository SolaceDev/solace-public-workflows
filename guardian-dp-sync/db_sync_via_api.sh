#!/usr/bin/env bash
set -euo pipefail

GUARDIAN_URL=""
GUARDIAN_KEY=""
PRODUCT_NAME=""
PRODUCT_VERSION=""
PRODUCT_FULL_VERSION=""
COLLECTION=""
JIRA_COLLECTION_NAME=""
JIRA_PROFILE=""
JIRA_DRY_RUN="false"
OUTPUT_DIR=""

usage() {
  cat <<'EOF'
Synchronize already uploaded scan results through the Guardian REST API.

Required:
  --guardian-url <url>
  --guardian-key <token>

Optional:
  --product-name <name>            Defaults to the repository name without the org
  --product-version <version>
  --product-full-version <full-version>
  --collection <name>
  --jira-collection-name <name>
  --jira-profile <name>
  --jira-dry-run <true|false>   Default: false
  --output-dir <dir>
  -h, --help

Example:
  guardian-dp-sync/db_sync_via_api.sh \
    --guardian-url https://guardian.com \
    --guardian-key "$GUARDIAN_API_TOKEN" \
    --product-name some-repo\
    --product-version main \
    --product-full-version 0.0.1225 \
    --collection test_collection \
    --jira-collection-name test_jira_metadata
EOF
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $cmd" >&2
    exit 1
  fi
}

normalize_bool() {
  local value="$1"
  case "$value" in
    true|false)
      printf '%s\n' "$value"
      ;;
    *)
      echo "ERROR: invalid boolean value: $value (expected true or false)" >&2
      exit 1
      ;;
  esac
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

default_product_name() {
  if [ -n "${GITHUB_REPOSITORY:-}" ]; then
    printf '%s\n' "${GITHUB_REPOSITORY#*/}"
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

set_output() {
  local name="$1"
  local value="$2"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf '%s=%s\n' "$name" "$value" >> "$GITHUB_OUTPUT"
  fi
}

set_json_output_from_file() {
  local name="$1"
  local file="$2"
  if [ -n "${GITHUB_OUTPUT:-}" ] && [ -f "$file" ]; then
    local compact_json
    compact_json="$(jq -c . "$file")"
    if [ "${#compact_json}" -gt 50000 ]; then
      echo "WARNING: skipping GitHub output '$name' because the JSON payload exceeds 50000 bytes" >&2
      return 0
    fi
    printf '%s=%s\n' "$name" "$compact_json" >> "$GITHUB_OUTPUT"
  fi
}

append_step_summary() {
  local line="$1"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '%s\n' "$line" >> "$GITHUB_STEP_SUMMARY"
  fi
}

api_post_json() {
  local output_file="$1"
  local token="$2"
  local payload="$3"
  local url="$4"
  curl -sS \
    -o "$output_file" \
    -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    --data "$payload" \
    "$url"
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
    --collection)
      COLLECTION="$2"
      shift 2
      ;;
    --jira-collection-name|--jira_collection_name)
      JIRA_COLLECTION_NAME="$2"
      shift 2
      ;;
    --jira-profile)
      JIRA_PROFILE="$2"
      shift 2
      ;;
    --jira-dry-run)
      JIRA_DRY_RUN="$(normalize_bool "$2")"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
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

if [ -z "$PRODUCT_NAME" ]; then
  PRODUCT_NAME="$(default_product_name)"
fi

GUARDIAN_URL="${GUARDIAN_URL%/}"
SCAN_PATH=""
if [ -n "$PRODUCT_NAME" ] && [ -n "$PRODUCT_VERSION" ] && [ -n "$PRODUCT_FULL_VERSION" ]; then
  SCAN_PATH="scan-backups/${PRODUCT_NAME}/${PRODUCT_VERSION}/${PRODUCT_FULL_VERSION}"
fi
DISPLAY_SCAN_PATH="$SCAN_PATH"
if [ -z "$DISPLAY_SCAN_PATH" ]; then
  DISPLAY_SCAN_PATH="API resolved"
fi

if [ -n "$OUTPUT_DIR" ]; then
  mkdir -p "$OUTPUT_DIR"
  RESPONSE_FILE="$OUTPUT_DIR/db_synch_and_report_response.json"
else
  RESPONSE_FILE="$(mktemp)"
fi

REQUEST_BODY="$(
  jq -n \
    --arg scan_path "$SCAN_PATH" \
    --arg product_name "$PRODUCT_NAME" \
    --arg product_version "$PRODUCT_VERSION" \
    --arg product_full_version "$PRODUCT_FULL_VERSION" \
    --arg collection "$COLLECTION" \
    --arg jira_metadata_collection_name "$JIRA_COLLECTION_NAME" \
    --arg jira_profile "$JIRA_PROFILE" \
    --argjson jira_dry_run "$JIRA_DRY_RUN" \
    '{
      jira_dry_run: $jira_dry_run
    }
    + (if $scan_path != "" then {scan_path: $scan_path} else {} end)
    + (if $product_name != "" then {product_name: $product_name} else {} end)
    + (if $product_version != "" then {product_version: $product_version} else {} end)
    + (if $product_full_version != "" then {product_full_version: $product_full_version} else {} end)
    + (if $collection != "" then {collection: $collection} else {} end)
    + (if $jira_metadata_collection_name != "" then {jira_metadata_collection_name: $jira_metadata_collection_name} else {} end)
    + (if $jira_profile != "" then {jira_profile: $jira_profile} else {} end)'
)"

echo "Running Guardian sync and report via $GUARDIAN_URL/api/v1/db_synch_and_report"
if [ -n "$PRODUCT_NAME" ]; then
  echo "  Product: $PRODUCT_NAME"
fi
if [ -n "$PRODUCT_VERSION" ]; then
  echo "  Product version: $PRODUCT_VERSION"
fi
if [ -n "$PRODUCT_FULL_VERSION" ]; then
  echo "  Product full version: $PRODUCT_FULL_VERSION"
fi
echo "  Scan path: $DISPLAY_SCAN_PATH"
echo "  S3 bucket: API default"
if [ -n "$COLLECTION" ]; then
  echo "  Vulnerability collection: $COLLECTION"
fi
if [ -n "$JIRA_COLLECTION_NAME" ]; then
  echo "  Jira collection: $JIRA_COLLECTION_NAME"
fi
if [ -n "$JIRA_PROFILE" ]; then
  echo "  Jira profile: $JIRA_PROFILE"
fi
echo "  Jira dry run: $JIRA_DRY_RUN"

HTTP_STATUS="$(api_post_json "$RESPONSE_FILE" "$GUARDIAN_KEY" "$REQUEST_BODY" "$GUARDIAN_URL/api/v1/db_synch_and_report")"

if [ "$HTTP_STATUS" -lt 200 ] || [ "$HTTP_STATUS" -ge 300 ]; then
  echo "ERROR: db_synch_and_report failed with HTTP $HTTP_STATUS" >&2
  print_response "$RESPONSE_FILE"
  exit 1
fi

PRODUCT_NAME="$(jq -r '.db_synch.product_name' "$RESPONSE_FILE")"
PRODUCT_VERSION="$(jq -r '.db_synch.product_version' "$RESPONSE_FILE")"
DB_SUMMARY="$(jq -c '.db_synch.summary' "$RESPONSE_FILE")"

echo "Guardian sync and report completed"
echo "  Product: $PRODUCT_NAME"
echo "  Version: $PRODUCT_VERSION"
echo "  DB summary: $DB_SUMMARY"

print_response "$RESPONSE_FILE"

set_output product_name "$PRODUCT_NAME"
set_output product_version "$PRODUCT_VERSION"
set_json_output_from_file response_json "$RESPONSE_FILE"

append_step_summary "### Guardian Sync and Report"
append_step_summary "- Product: \`$PRODUCT_NAME\`"
append_step_summary "- Version: \`$PRODUCT_VERSION\`"
append_step_summary "- Scan path: \`$DISPLAY_SCAN_PATH\`"
append_step_summary "- DB summary: \`$DB_SUMMARY\`"

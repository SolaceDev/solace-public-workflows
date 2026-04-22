#!/usr/bin/env bash
set -euo pipefail

GUARDIAN_URL=""
GUARDIAN_KEY=""
PRODUCT_NAME=""
PRODUCT_VERSION=""
PRODUCT_FULL_VERSION=""
SCAN_TIME=""
FOSSA_REVISION=""
FOSSA_SCAN_PATH=""
PRISMA_SCAN_PATH=""
TRIVY_SCAN_PATH=""
THRESHOLDS=""
SEVERITY=""
SLACK_CHANNEL_ID=""
SLACK_THREAD_TS=""
SLACK_BUILD_URL=""
SLACK_TITLE=""
FAIL_ON_BLOCKED="true"
REPORT_PATH="release_gate_report.md"
SUMMARY_REPORT="true"

usage() {
  cat <<'EOF'
Gate a release artifact against Guardian vulnerability thresholds via the REST API.

Required:
  --guardian-url <url>
  --guardian-key <token>
  --product-name <name>
  --product-full-version <full-version>

Scan sources (at least one required):
  --fossa-revision <sha>           FOSSA revision for server-side auto-fetch
  --fossa-scan-path <path>         Path to fossa_scan.json
  --prisma-scan-path <path>        Path to prisma_scan.json
  --trivy-scan-path <path>         Path to trivy_scan.json

Optional:
  --product-version <version>      Defaults to GITHUB_REF_NAME
  --scan-time <iso8601>            Defaults to current UTC time
  --thresholds <json>              e.g. '{"Critical":null,"High":10}'
  --severity <json>                e.g. '["Critical","High"]'
  --slack-channel-id <id>
  --slack-thread-ts <ts>
  --slack-build-url <url>
  --slack-title <title>
  --fail-on-blocked <true|false>   Default: true
  --report-path <path>             Default: release_gate_report.md
  --summary-report <true|false>    Include full report in step summary. Default: true.
                                   Set to false for public repos to avoid leaking vuln details.
  -h, --help

Example:
  guardian-release-gate/release_gate_via_api.sh \
    --guardian-url https://guardian.example.com \
    --guardian-key "$GUARDIAN_API_TOKEN" \
    --product-name some-repo \
    --product-full-version 3.2.1.1744100000 \
    --fossa-revision abc123def456 \
    --thresholds '{"Critical":null,"High":10}'
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

append_step_summary() {
  local line="$1"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '%s\n' "$line" >> "$GITHUB_STEP_SUMMARY"
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
    --scan-time)
      SCAN_TIME="$2"
      shift 2
      ;;
    --fossa-revision)
      FOSSA_REVISION="$2"
      shift 2
      ;;
    --fossa-scan-path)
      FOSSA_SCAN_PATH="$2"
      shift 2
      ;;
    --prisma-scan-path)
      PRISMA_SCAN_PATH="$2"
      shift 2
      ;;
    --trivy-scan-path)
      TRIVY_SCAN_PATH="$2"
      shift 2
      ;;
    --thresholds)
      THRESHOLDS="$2"
      shift 2
      ;;
    --severity)
      SEVERITY="$2"
      shift 2
      ;;
    --slack-channel-id)
      SLACK_CHANNEL_ID="$2"
      shift 2
      ;;
    --slack-thread-ts)
      SLACK_THREAD_TS="$2"
      shift 2
      ;;
    --slack-build-url)
      SLACK_BUILD_URL="$2"
      shift 2
      ;;
    --slack-title)
      SLACK_TITLE="$2"
      shift 2
      ;;
    --fail-on-blocked)
      FAIL_ON_BLOCKED="$(normalize_bool "$2")"
      shift 2
      ;;
    --report-path)
      REPORT_PATH="$2"
      shift 2
      ;;
    --summary-report)
      SUMMARY_REPORT="$(normalize_bool "$2")"
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
require_value --product-name "$PRODUCT_NAME"

require_value --product-full-version "$PRODUCT_FULL_VERSION"

if [ -z "$PRODUCT_VERSION" ]; then
  PRODUCT_VERSION="${GITHUB_REF_NAME:-}"
fi

if [ -z "$SCAN_TIME" ]; then
  SCAN_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

# Validate at least one scan source is provided
if [ -z "$FOSSA_REVISION" ] && [ -z "$FOSSA_SCAN_PATH" ] && [ -z "$PRISMA_SCAN_PATH" ] && [ -z "$TRIVY_SCAN_PATH" ]; then
  echo "ERROR: at least one scan source is required: --fossa-revision, --fossa-scan-path, --prisma-scan-path, or --trivy-scan-path" >&2
  usage
  exit 1
fi

# Validate scan file paths exist
for scan_path in "$FOSSA_SCAN_PATH" "$PRISMA_SCAN_PATH" "$TRIVY_SCAN_PATH"; do
  if [ -n "$scan_path" ] && [ ! -f "$scan_path" ]; then
    echo "ERROR: scan file not found: $scan_path" >&2
    exit 1
  fi
done

GUARDIAN_URL="${GUARDIAN_URL%/}"

RESPONSE_FILE="$(mktemp)"

# Build Slack JSON if channel-id is provided
SLACK_JSON=""
if [ -n "$SLACK_CHANNEL_ID" ]; then
  SLACK_JSON="$(
    jq -n \
      --arg channel_id "$SLACK_CHANNEL_ID" \
      --arg thread_ts "$SLACK_THREAD_TS" \
      --arg build_url "$SLACK_BUILD_URL" \
      --arg title "$SLACK_TITLE" \
      '{channel_id: $channel_id}
      + (if $thread_ts != "" then {thread_ts: $thread_ts} else {} end)
      + (if $build_url != "" then {build_url: $build_url} else {} end)
      + (if $title != "" then {title: $title} else {} end)'
  )"
fi

CURL_ARGS=(
  -sS
  -o "$RESPONSE_FILE"
  -w "%{http_code}"
  -X POST
  -H "Authorization: Bearer $GUARDIAN_KEY"
  --form-string "product_name=$PRODUCT_NAME"
  --form-string "product_version=$PRODUCT_VERSION"
  --form-string "product_full_version=$PRODUCT_FULL_VERSION"
  --form-string "scan_time=$SCAN_TIME"
)

[ -n "$FOSSA_REVISION" ]   && CURL_ARGS+=(--form-string "fossa_revision=$FOSSA_REVISION")
[ -n "$FOSSA_SCAN_PATH" ]  && CURL_ARGS+=(--form "fossa_scan=@$FOSSA_SCAN_PATH")
[ -n "$PRISMA_SCAN_PATH" ] && CURL_ARGS+=(--form "prisma_scan=@$PRISMA_SCAN_PATH")
[ -n "$TRIVY_SCAN_PATH" ]  && CURL_ARGS+=(--form "trivy_scan=@$TRIVY_SCAN_PATH")
[ -n "$THRESHOLDS" ]       && CURL_ARGS+=(--form-string "thresholds=$THRESHOLDS")
[ -n "$SEVERITY" ]         && CURL_ARGS+=(--form-string "severity=$SEVERITY")
[ -n "$SLACK_JSON" ]       && CURL_ARGS+=(--form-string "slack=$SLACK_JSON")

echo "Running Guardian release gate via $GUARDIAN_URL/api/v1/release_gate"
echo "  Product: $PRODUCT_NAME"
echo "  Product version: $PRODUCT_VERSION"
echo "  Product full version: $PRODUCT_FULL_VERSION"
echo "  Scan time: $SCAN_TIME"
if [ -n "$FOSSA_REVISION" ]; then
  echo "  FOSSA revision: $FOSSA_REVISION"
fi
if [ -n "$FOSSA_SCAN_PATH" ]; then
  echo "  FOSSA scan path: $FOSSA_SCAN_PATH"
fi
if [ -n "$PRISMA_SCAN_PATH" ]; then
  echo "  Prisma scan path: $PRISMA_SCAN_PATH"
fi
if [ -n "$TRIVY_SCAN_PATH" ]; then
  echo "  Trivy scan path: $TRIVY_SCAN_PATH"
fi
if [ -n "$THRESHOLDS" ]; then
  echo "  Thresholds: $THRESHOLDS"
fi
if [ -n "$SEVERITY" ]; then
  echo "  Severity filter: $SEVERITY"
fi

HTTP_STATUS="$(curl "${CURL_ARGS[@]}" "$GUARDIAN_URL/api/v1/release_gate")"

if [ "$HTTP_STATUS" -lt 200 ] || [ "$HTTP_STATUS" -ge 300 ]; then
  echo "ERROR: release_gate failed with HTTP $HTTP_STATUS" >&2
  print_response "$RESPONSE_FILE"
  exit 1
fi

OVERALL_BLOCKED="$(jq -r '.overall_blocked' "$RESPONSE_FILE")"
VULN_COUNT="$(jq -r '.vulnerability_count // 0' "$RESPONSE_FILE")"
REPORT_MD="$(jq -r '.report_markdown // ""' "$RESPONSE_FILE")"

# Ensure report directory exists and write the markdown report
mkdir -p "$(dirname "$REPORT_PATH")"
printf '%s\n' "$REPORT_MD" > "$REPORT_PATH"

echo "Guardian release gate completed"
echo "  Overall blocked: $OVERALL_BLOCKED"
echo "  Vulnerability count: $VULN_COUNT"
echo "  Report written to: $REPORT_PATH"

if [ "$SUMMARY_REPORT" = "true" ]; then
  print_response "$RESPONSE_FILE"
fi

set_output overall_blocked "$OVERALL_BLOCKED"
set_output vulnerability_count "$VULN_COUNT"
set_output report_path "$REPORT_PATH"

if [ "$SUMMARY_REPORT" = "true" ] && [ -n "$REPORT_MD" ]; then
  append_step_summary "$REPORT_MD"
fi

if [ "$FAIL_ON_BLOCKED" = "true" ] && [ "$OVERALL_BLOCKED" = "true" ]; then
  echo "Release is blocked by Guardian vulnerability gate." >&2
  exit 1
fi

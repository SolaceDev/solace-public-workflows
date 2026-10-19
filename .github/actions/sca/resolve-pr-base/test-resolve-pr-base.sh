#!/bin/bash
set -euo pipefail

###############################################################################
# Test Suite for resolve-pr-base.sh
#
# A stub curl on PATH answers from $STUB_RESPONSES, one "<http code> <json body>"
# line per call (the last line repeats), or fails like an unreachable host when
# the code is "fail". A stub sleep returns at once. No FOSSA key or network.
#
# Usage:
#   ./test-resolve-pr-base.sh
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PASSED=0
TEST_FAILED=0

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"
cat > "$WORK/bin/curl" <<'EOF'
#!/usr/bin/env bash
out=""; while [[ $# -gt 0 ]]; do [[ "$1" == "-o" ]] && { out=$2; shift; }; shift; done
n=$(( $(cat "$STUB_COUNT" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$STUB_COUNT"
line=$(sed -n "${n}p" "$STUB_RESPONSES"); [[ -n "$line" ]] || line=$(tail -1 "$STUB_RESPONSES")
code=${line%% *}; body=${line#* }
[[ "$code" == fail ]] && { echo "curl: (7) Failed to connect" >&2; exit 7; }
printf '%s' "$body" > "$out"
printf '%s' "$code"
EOF
printf '#!/usr/bin/env bash\nexit 0\n' > "$WORK/bin/sleep"
chmod +x "$WORK/bin/curl" "$WORK/bin/sleep"

# run_case <name> <minutes already used of 90> <expected outputs> <expected log fragment> <responses...>
# The base's budget is 90 minutes, less those used, less the 10-minute guard reserve.
run_case() {
  local name=$1 used=$2 expected=$3 log_fragment=$4; shift 4
  printf '%s\n' "$@" > "$WORK/responses"
  rm -f "$WORK/count" "$WORK/out"
  local log
  log=$(PATH="$WORK/bin:$PATH" STUB_RESPONSES="$WORK/responses" STUB_COUNT="$WORK/count" \
    FOSSA_API_KEY=key FOSSA_ORG_ID=custom+1 FOSSA_PROJECT_ID=SolaceDev_repo \
    BASE_SHA=abc123 BASE_REF=main STARTED_AT=$(( $(date +%s) - used * 60 )) JOB_TIMEOUT_MINUTES=90 \
    GITHUB_OUTPUT="$WORK/out" "$SCRIPT_DIR/resolve-pr-base.sh" 2>&1) || { fail "$name" "script exited non-zero" "$log"; return; }
  local actual
  actual=$(tr '\n' ' ' < "$WORK/out" | sed 's/ $//')
  if [[ "$actual" != "$expected" ]]; then
    fail "$name" "outputs: expected '$expected', got '$actual'" "$log"
  elif [[ -n "$log_fragment" && "$log" != *"$log_fragment"* ]]; then
    fail "$name" "log lacks '$log_fragment'" "$log"
  else
    echo -e "${GREEN}✓${NC} $name"
    TEST_PASSED=$((TEST_PASSED + 1))
  fi
}

fail() {
  echo -e "${RED}✗${NC} $1"
  echo "  $2"
  while IFS= read -r line; do echo "  | $line"; done <<< "$3"
  TEST_FAILED=$((TEST_FAILED + 1))
}

run_case "existing, analysed revision is reused" 10 \
  "revision=abc123 scan=false" "already scanned" \
  '200 {"resolved":true,"error":""}'
run_case "missing revision is scanned, budget split from the time left" 10 \
  "checkout_minutes=5 setup_minutes=26 scan_minutes=39 scan=true" "within 70 minutes" \
  '404 {}'
run_case "missing revision with too little of the job left falls back" 72 \
  "scan=false" "only 8 minutes of the job are left" \
  '404 {}'
run_case "analysis in progress is waited for, then reused" 10 \
  "revision=abc123 scan=false" "still being analysed" \
  '200 {"resolved":false,"error":""}' '200 {"resolved":false,"error":""}' '200 {"resolved":true,"error":""}'
run_case "failed analysis falls back at once" 10 \
  "scan=false" "failed (dependency resolution failed)" \
  '200 {"resolved":false,"error":"dependency resolution failed"}'
run_case "unsupported analysis falls back at once" 10 \
  "scan=false" "failed (unsupported)" \
  '200 {"resolved":false,"unsupported":true,"error":""}'
ANALYSIS_WAIT_SECONDS=0 run_case "analysis that never finishes falls back" 10 \
  "scan=false" "did not finish in time" \
  '200 {"resolved":false,"error":""}'
run_case "unauthorised lookup falls back" 10 \
  "scan=false" "HTTP 401" \
  '401 {"message":"Unauthorized"}'
run_case "unreachable FOSSA falls back" 10 \
  "scan=false" "HTTP unreachable" \
  'fail'

echo
echo "Passed: $TEST_PASSED, failed: $TEST_FAILED"
[[ "$TEST_FAILED" -eq 0 ]]

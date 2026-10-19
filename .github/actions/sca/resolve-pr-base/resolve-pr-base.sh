#!/usr/bin/env bash
###############################################################################
# Resolve the FOSSA revision a pull request is diffed against: its base commit.
#
# Reuses FOSSA's existing revision of the base commit, waiting while its
# analysis is still running; otherwise asks for the base to be scanned, with
# step timeouts sized from what is left of the job's own timeout.
#
# Environment (required):
#   FOSSA_API_KEY        FOSSA API token
#   FOSSA_ORG_ID         FOSSA organisation locator prefix, e.g. custom+48578
#   FOSSA_PROJECT_ID     FOSSA project id, e.g. SolaceDev_my-repo
#   BASE_SHA             the PR's base commit (github.event.pull_request.base.sha)
#   BASE_REF             the PR's base branch, for messages
#   STARTED_AT           epoch seconds the job started
#   JOB_TIMEOUT_MINUTES  the job's timeout-minutes
# Environment (optional):
#   ANALYSIS_WAIT_SECONDS  longest wait for an in-progress analysis (600)
#   GUARD_RESERVE_SECONDS  time kept for the guards after the base (600)
#   MIN_BASE_MINUTES       below this, the base is not scanned (15)
#   POLL_SECONDS           interval between analysis checks (20)
#   FOSSA_API_URL          FOSSA base URL (https://app.fossa.com)
#   GITHUB_OUTPUT          where key=value outputs go (stdout when unset)
#
# Outputs:
#   revision          the base commit, when FOSSA already has its revision
#   scan              true when the base should be scanned under PR_BASE
#   checkout_minutes  \
#   setup_minutes      > timeouts for the base checkout, setup and scan, when scan=true
#   scan_minutes      /
#
# Every problem (lookup failed, analysis failed or never finished, too little
# time left) ends in scan=false with no revision and a ::warning::, which the
# caller treats as "fall back to fossa-guard's own base detection". The script
# exits 0 in every one of those cases.
###############################################################################
set -euo pipefail

: "${FOSSA_API_KEY:?}" "${FOSSA_ORG_ID:?}" "${FOSSA_PROJECT_ID:?}" "${BASE_SHA:?}" "${BASE_REF:?}"
: "${STARTED_AT:?}" "${JOB_TIMEOUT_MINUTES:?}"
ANALYSIS_WAIT_SECONDS=${ANALYSIS_WAIT_SECONDS:-600}
GUARD_RESERVE_SECONDS=${GUARD_RESERVE_SECONDS:-600}
MIN_BASE_MINUTES=${MIN_BASE_MINUTES:-15}
POLL_SECONDS=${POLL_SECONDS:-20}
FOSSA_API_URL=${FOSSA_API_URL:-https://app.fossa.com}
GITHUB_OUTPUT=${GITHUB_OUTPUT:-/dev/stdout}

base="${BASE_REF}@${BASE_SHA}"
fallback="diffing against fossa-guard's auto-detected base, which may be the wrong commit"
output() { echo "$1" >> "$GITHUB_OUTPUT"; }
seconds_left() { echo $(( JOB_TIMEOUT_MINUTES * 60 - ($(date +%s) - STARTED_AT) - GUARD_RESERVE_SECONDS )); }

body=$(mktemp)
trap 'rm -f "$body"' EXIT
encoded=$(jq -rn --arg v "${FOSSA_ORG_ID}/${FOSSA_PROJECT_ID}\$${BASE_SHA}" '$v | @uri')

# A revision exists from upload, before its analysis finishes: a base still being analysed (a PR
# opened right after its base's push scan started) is waited for, within the job's remaining time.
wait_for=$(seconds_left)
(( wait_for > ANALYSIS_WAIT_SECONDS )) && wait_for=$ANALYSIS_WAIT_SECONDS
deadline=$(( SECONDS + wait_for ))
analysis_error=""
while :; do
  # --retry covers timeouts, 429 and 5xx, so one transient error is not mistaken for an outage.
  status=$(curl -sS --max-time 30 --retry 2 -o "$body" -w '%{http_code}' \
    -H "Authorization: Bearer ${FOSSA_API_KEY}" "${FOSSA_API_URL}/api/revisions/${encoded}") || status="unreachable"
  [[ "$status" == 200 ]] || break
  [[ "$(jq -r '.resolved' "$body")" == true ]] && break
  # A failed or unsupported analysis never resolves; waiting for it would only cost time.
  analysis_error=$(jq -r 'if .unsupported == true then "unsupported" else (.error // "") end' "$body")
  if [[ -n "$analysis_error" ]]; then status="failed"; break; fi
  if (( SECONDS >= deadline )); then status="unresolved"; break; fi
  echo "Base ${base} is still being analysed in FOSSA; waiting"
  sleep "$POLL_SECONDS"
done

scan=false
case "$status" in
  200)
    echo "Base ${base} is already scanned in FOSSA; diffing against it"
    output "revision=${BASE_SHA}" ;;
  404)
    minutes=$(( $(seconds_left) / 60 ))
    if (( minutes < MIN_BASE_MINUTES )); then
      echo "::warning::Base ${base} has no FOSSA revision, and only ${minutes} minutes of the job are left to scan it; ${fallback}"
    else
      echo "Base ${base} has no FOSSA revision; scanning it under branch PR_BASE within ${minutes} minutes"
      scan=true
      setup=$(( (minutes - 5) * 2 / 5 ))
      output "checkout_minutes=5"
      output "setup_minutes=${setup}"
      output "scan_minutes=$(( minutes - 5 - setup ))"
    fi ;;
  failed)
    echo "::warning::FOSSA's analysis of base ${base} failed (${analysis_error}); ${fallback}" ;;
  unresolved)
    echo "::warning::FOSSA's analysis of base ${base} did not finish in time; ${fallback}" ;;
  *)
    echo "::warning::Could not look up base ${base} in FOSSA (HTTP ${status}); ${fallback}" ;;
esac
output "scan=${scan}"

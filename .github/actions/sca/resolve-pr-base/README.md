# Resolve PR Base Revision

Finds the FOSSA revision a pull request should be diffed against: the PR's base commit. `sca-scan-and-guard.yaml` uses it so `fossa-guard`'s diff mode compares the PR with the commit it merges into, rather than guessing a base from FOSSA's branches. The workflow docs ([../../../workflows/docs/sca-scan-and-guard.md](../../../workflows/docs/sca-scan-and-guard.md#diff-base)) explain the diff base and the FOSSA branch convention.

What it decides:

1. **FOSSA has a finished revision for the base commit**: `revision` is the base commit and `scan` is `false`, so the caller diffs against it and scans nothing.
2. **That revision's analysis is still running**: the action waits, for up to `analysis_wait_seconds`. It stops at once if the analysis failed or is unsupported.
3. **FOSSA has no revision for it**: `scan` is `true`. The caller scans the base under the FOSSA branch `PR_BASE`, within the timeouts given in `checkout_minutes`, `setup_minutes` and `scan_minutes`. These split what is left of the job's `job_timeout_minutes`, less `guard_reserve_seconds`. With under `min_base_minutes` left, `scan` is `false` instead.
4. **Anything else** (the lookup fails, the analysis failed or never finishes, too little time left): `scan` is `false` with no `revision`, and a `::warning::` says why. The caller falls back to `fossa-guard`'s own base detection.

The action always succeeds; every problem is a fallback, not a failure. Run it with `continue-on-error: true` anyway, so a killed step falls back too.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `fossa_api_key` | Yes | | FOSSA API key |
| `fossa_org_id` | Yes | | FOSSA organisation locator prefix, e.g. `custom+48578` |
| `fossa_project_id` | Yes | | FOSSA project id, e.g. `SolaceDev_my-repo` |
| `base_sha` | No | `github.event.pull_request.base.sha` | The PR's base commit |
| `base_ref` | No | `github.base_ref` | The PR's base branch, for messages |
| `started_at` | Yes | | Epoch seconds the job started |
| `job_timeout_minutes` | Yes | | The job's `timeout-minutes` |
| `analysis_wait_seconds` | No | `600` | Longest wait for an in-progress analysis |
| `guard_reserve_seconds` | No | `600` | Time kept for the guards and report after the base |
| `min_base_minutes` | No | `15` | Below this many minutes left, the base is not scanned |

## Outputs

| Output | Description |
|--------|-------------|
| `revision` | The base commit, when FOSSA already has its revision; empty otherwise |
| `scan` | `true` when the base should be scanned under `PR_BASE` |
| `checkout_minutes` | Timeout for the base checkout, when `scan` is `true` |
| `setup_minutes` | Timeout for the base's dependency setup, when `scan` is `true` |
| `scan_minutes` | Timeout for the base's FOSSA scan, when `scan` is `true` |

## Usage

```yaml
- name: Resolve PR base revision
  id: pr_base
  if: github.event_name == 'pull_request'
  continue-on-error: true
  timeout-minutes: 12
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/resolve-pr-base@<sha>
  with:
    fossa_api_key: ${{ steps.vault.outputs.FOSSA_API_KEY }}
    fossa_org_id: custom+48578
    fossa_project_id: SolaceDev_my-repo
    started_at: ${{ steps.start.outputs.epoch }}
    job_timeout_minutes: "90"

- name: Checkout PR base
  if: steps.pr_base.outputs.scan == 'true'
  continue-on-error: true
  timeout-minutes: ${{ fromJSON(steps.pr_base.outputs.checkout_minutes || '1') }}
  uses: actions/checkout@<sha>
  with:
    ref: ${{ github.event.pull_request.base.sha }}
```

## Running it locally

`resolve-pr-base.sh` reads its settings from environment variables (listed at the top of the script). It writes its outputs to `$GITHUB_OUTPUT`, or to stdout when that is unset:

```bash
FOSSA_API_KEY=... FOSSA_ORG_ID=custom+48578 FOSSA_PROJECT_ID=SolaceDev_my-repo \
BASE_SHA=<sha> BASE_REF=main STARTED_AT=$(date +%s) JOB_TIMEOUT_MINUTES=90 \
  ./resolve-pr-base.sh
```

`./test-resolve-pr-base.sh` runs every path against a stub `curl`, with no FOSSA key or network.

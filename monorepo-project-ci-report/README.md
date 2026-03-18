# Monorepo Project CI Report

Builds one normalized JSON payload for a single monorepo project.  
This payload is designed to be uploaded as an artifact and consumed later by aggregation jobs (status checks and release-readiness checks).

## What this action does

For one project, it combines:

- SonarQube step outcome
- FOSSA licensing report and outcome
- FOSSA vulnerability report and outcome
- Unit test result plus optional CTRF report
- Project metadata (path, branch, sha, event)

Output is written to `ci-project-result-<project>.json` (or custom `output_file`).

## How it works with FOSSA actions

This action **does not run FOSSA**. It only packages outputs produced earlier in the workflow:

1. Run your FOSSA guard/check action(s) first (licensing + vulnerability).
2. Point this action to the generated JSON reports via:
   - `fossa_licensing_report_path`
   - `fossa_vulnerability_report_path`
3. Pass the matching outcomes via:
   - `fossa_licensing_result`
   - `fossa_vulnerability_result`
4. This action copies full report payloads and derives normalized counters:
   - `fossa_licensing_total_issues`
   - `fossa_licensing_blocking_issues`
   - `fossa_vulnerability_total_issues`
   - `fossa_vulnerability_blocking_issues`
5. It also builds a canonical FOSSA report URL from `repo_owner + project_name + branch + revision`.

This keeps build jobs focused on scanning, while aggregation jobs operate on a single stable schema.

## Usage

```yaml
- name: Build project CI payload
  uses: SolaceDev/solace-public-workflows/monorepo-project-ci-report@main
  with:
    project_name: sam-foo
    project_path: sam-foo
    repo_owner: ${{ github.repository_owner }}
    branch: ${{ steps.fossa_target.outputs.branch }}
    revision: ${{ steps.fossa_target.outputs.revision }}
    sha: ${{ github.sha }}
    github_event: ${{ github.event_name }}
    sonarqube_result: ${{ steps.sonar_scan.outcome }}
    unit_test_result: ${{ steps.unit_test_normalized.outputs.result }}
    unit_test_outcome: ${{ steps.test.outcome }}
    unit_test_report_path: sam-foo/report.json
    unit_test_junit_report_path: sam-foo/junit.xml
    tests_present: ${{ steps.test.outputs.tests_present }}
    junit_exists: ${{ steps.test.outputs.junit_exists }}
    coverage_exists: ${{ steps.test.outputs.coverage_exists }}
    fossa_diff_mode: ${{ steps.fossa_target.outputs.enable_diff_mode }}
    fossa_licensing_result: ${{ steps.fossa_licensing.outcome }}
    fossa_licensing_report_path: fossa/licensing.json
    fossa_vulnerability_result: ${{ steps.fossa_vulnerability.outcome }}
    fossa_vulnerability_report_path: fossa/vulnerability.json
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `project_name` | yes | - | Project identifier |
| `project_path` | yes | - | Relative path of the project |
| `repo_owner` | yes | - | Owner prefix for FOSSA project id |
| `branch` | yes | - | FOSSA branch context |
| `revision` | yes | - | FOSSA revision context |
| `sha` | yes | - | Commit SHA for this project run |
| `github_event` | yes | - | GitHub event name |
| `sonarqube_result` | yes | - | SonarQube step outcome |
| `unit_test_result` | yes | - | Normalized test status (`passed/failed/skipped`) |
| `unit_test_outcome` | no | `missing` | Raw unit test step outcome |
| `unit_test_report_path` | no | `""` | Path to CTRF file |
| `unit_test_junit_report_path` | no | `""` | Path to JUnit XML file (fallback failure details) |
| `tests_present` | no | `false` | Whether test folder existed |
| `junit_exists` | no | `false` | Whether junit XML exists |
| `coverage_exists` | no | `false` | Whether coverage XML exists |
| `fossa_diff_mode` | no | `false` | Whether FOSSA executed in diff mode |
| `fossa_licensing_result` | yes | - | Licensing guard outcome |
| `fossa_licensing_report_path` | no | `""` | Licensing JSON report path |
| `fossa_vulnerability_result` | yes | - | Vulnerability guard outcome |
| `fossa_vulnerability_report_path` | no | `""` | Vulnerability JSON report path |
| `output_file` | no | `ci-project-result-<project>.json` | Output payload file path |

## Outputs

| Output | Description |
|---|---|
| `report_file` | Path to the generated project CI payload JSON file |

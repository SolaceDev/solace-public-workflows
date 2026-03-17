# Project CI Report

Reusable composite action that builds a **single per-project CI payload** JSON combining:

- SonarQube step result
- FOSSA licensing report + status
- FOSSA vulnerability report + status
- Unit-test status and optional CTRF report

It is intended for matrix project builds in monorepos where a downstream aggregator
downloads `ci-*-result-*.json` artifacts and publishes unified checks/comments.

## Usage

```yaml
- name: Build unified CI project report payload
  uses: SolaceDev/solace-public-workflows/.github/actions/project-ci-report@main
  with:
    project_name: service-a
    project_path: services/service-a
    repo_owner: ${{ github.repository_owner }}
    branch: PR
    revision: ${{ github.head_ref }}
    sha: ${{ github.sha }}
    github_event: ${{ github.event_name }}
    sonarqube_result: ${{ steps.sonarqube-scan.outcome }}
    unit_test_result: passed
    unit_test_outcome: ${{ steps.test.outcome }}
    unit_test_report_path: services/service-a/report.json
    tests_present: "true"
    junit_exists: "true"
    coverage_exists: "true"
    fossa_diff_mode: "true"
    fossa_licensing_result: ${{ steps.fossa_guard_licensing.outcome }}
    fossa_licensing_report_path: fossa-guard-licensing-service-a.json
    fossa_vulnerability_result: ${{ steps.fossa_guard_vulnerability.outcome }}
    fossa_vulnerability_report_path: fossa-guard-vulnerability-service-a.json
    output_file: ci-project-result-service-a.json
```

## Output shape

The generated JSON includes:

- `project`, `project_path`, `branch`, `sha`, `github_event`
- `sonarqube_result`
- `fossa_vulnerability_report`
- `fossa_licensing_report`
- `unit_test_result`
- `unit_test_report` (empty object when not available)

Compatibility fields are also included for plugin-based consumers.

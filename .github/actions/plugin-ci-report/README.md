# Plugin CI Report (Deprecated Alias)

Use `.github/actions/project-ci-report` for new integrations.

Reusable composite action that builds a **single per-plugin CI payload** JSON combining:

- SonarQube step result
- FOSSA licensing report + status
- FOSSA vulnerability report + status
- Unit-test status and optional CTRF report

It is intended for matrix plugin builds in monorepos where a downstream aggregator
downloads `ci-plugin-result-*.json` artifacts and publishes unified checks/comments.

## Usage

```yaml
- name: Build unified CI plugin report payload
  uses: SolaceDev/solace-public-workflows/.github/actions/plugin-ci-report@main
  with:
    plugin_name: sam-geo-information
    project_path: sam-geo-information
    repo_owner: ${{ github.repository_owner }}
    branch: PR
    revision: ${{ github.head_ref }}
    sha: ${{ github.sha }}
    github_event: ${{ github.event_name }}
    sonarqube_result: ${{ steps.sonarqube-scan.outcome }}
    unit_test_result: passed
    unit_test_outcome: ${{ steps.test.outcome }}
    unit_test_report_path: sam-geo-information/report.json
    tests_present: "true"
    junit_exists: "true"
    coverage_exists: "true"
    fossa_diff_mode: "true"
    fossa_licensing_result: ${{ steps.fossa_guard_licensing.outcome }}
    fossa_licensing_report_path: fossa-guard-licensing-sam-geo-information.json
    fossa_vulnerability_result: ${{ steps.fossa_guard_vulnerability.outcome }}
    fossa_vulnerability_report_path: fossa-guard-vulnerability-sam-geo-information.json
    output_file: ci-plugin-result-sam-geo-information.json
```

## Output shape

The generated JSON includes:

- `project_path`, `branch`, `sha`, `github_event`
- `sonarqube_result`
- `fossa_vulnerability_report`
- `fossa_licensing_report`
- `unit_test_result`
- `unit_test_report` (empty object when not available)

And compatibility fields currently used by existing aggregation actions
(`tests_status`, `sonar_outcome`, `fossa_*_total_issues`, etc.).

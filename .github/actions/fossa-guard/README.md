# fossa-guard GitHub Action Usage Guide

The `fossa-guard` GitHub Action integrates with the FOSSA API to fetch and process licensing or vulnerability issues for a given project. It is designed for CI/CD pipelines (such as GitHub Actions) to enforce open source compliance and security policies.

---

## Usage

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    fossa_project_id: <your_fossa_project_id>
    fossa_category: licensing # or vulnerability
    fossa_mode: BLOCK        # Optional, default is BLOCK. Use REPORT for reporting only.
    block_on: policy_conflict,policy_flag # Optional, comma-separated list of issue types to block on
```

---

## Inputs

| Name              | Required | Description                                                                 |
|-------------------|----------|-----------------------------------------------------------------------------|
| `fossa_api_key`   | Yes      | API key for FOSSA.                                                          |
| `fossa_project_id`| Yes      | Project ID in FOSSA. Can be specified in `.fossa.yml`. If not, use the format `custom+48578/SolaceDev_solace-agent-mesh-enterprise` and drop the `custom+48578/` prefix. |
| `fossa_category`  | Yes      | Issue category: `licensing` or `vulnerability`.                             |
| `fossa_mode`      | No       | Mode: `BLOCK` (default, fails build on violations) or `REPORT` (report only).|
| `block_on`        | No       | Comma-separated list of issue types to block on (e.g., `policy_conflict,policy_flag`). Default: `policy_conflict`.|
| `fossa_revision`  | No       | Specify a branch, tag, version, or commit SHA to filter issues for a specific revision. |

### Issue Types Explained
- **policy_conflict**: There is a known explicit policy violation (FOSSA terminology). This means the license or dependency is denied in your FOSSA policy and should block the build.
- **policy_flag**: The license needs to be reviewed or is unknown (FOSSA terminology). This means the license or dependency is flagged for review or is uncategorized in your FOSSA policy and may require manual attention.

> **Note:**
> The FOSSA project ID can be specified in your `.fossa.yml` file. If not present, use the format `custom+48578/SolaceDev_solace-agent-mesh-enterprise` and drop the `custom+48578/` prefix, so the project ID is just `SolaceDev_solace-agent-mesh-enterprise`.

---

## Supported Modes

| Mode   | Description                                                                                   |
|--------|-----------------------------------------------------------------------------------------------|
| BLOCK  | Fails the build if violations matching `block_on` are found. Prints a Markdown/HTML summary.  |
| REPORT | Prints a Markdown/HTML summary. Intended for reporting only (e.g., Slack integration).        |

---

## Business Logic

- Fetches issues from FOSSA for the specified project and category.
- All violations are always reported in the summary, regardless of blocking rules.
- The `block_on` flag determines which issue types (e.g., `policy_conflict`, `policy_flag`) will cause the build to fail in BLOCK mode.
- If `block_on` is empty, no violations will block the build, but all will be reported.
- Supports both licensing and vulnerability categories, with clear, formatted output for each.
- In REPORT mode, the script is intended for informational/reporting purposes and will not fail the build.

---

## Example Workflow Usage

```yaml
jobs:
  fossa_guard:
    runs-on: ubuntu-latest
    steps:
      - name: Run FOSSA Guard (Block mode)
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        with:
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
          fossa_category: licensing
          fossa_mode: BLOCK
          block_on: policy_conflict,policy_flag

      - name: Run FOSSA Guard (Report only, for Slack)
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        continue-on-error: true
        with:
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
          fossa_category: licensing
          fossa_mode: REPORT
          block_on: policy_conflict,policy_flag
```

> **Note:**
> If you want to use REPORT mode for Slack reporting and do not want the CI to fail on violations, set `continue-on-error: true` on the step.

---

## Notes
- The action prints a Markdown summary to the GitHub Actions log.
- If the `GITHUB_STEP_SUMMARY` environment variable is set, the summary is also written to the step summary for rich UI display.
- In BLOCK mode, the script exits with code 2 if blocking violations are found, causing the GitHub Action to fail.
- For more details, see the script source and comments.

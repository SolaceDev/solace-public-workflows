# Workflow Dispatch and Wait

Dispatch another GitHub Actions workflow via `workflow_dispatch` and optionally
wait for it to finish.

This action uses the GitHub API `return_run_details` parameter (API version
`2026-03-10`) to get the workflow run ID and URL directly from the dispatch
response, eliminating the need to poll for run discovery.

It can:

- trigger a workflow by name, filename, or workflow ID
- target the current repo or another repo
- optionally wait for the triggered run to complete
- optionally print or export the triggered run logs

## Inputs

- `workflow` (required): workflow name, filename, or ID to dispatch.
- `token` (required): token with permission to dispatch workflows.
- `inputs` (optional): JSON object string of workflow inputs.
- `ref` (optional): branch, tag, or SHA to dispatch against.
- `repo` (optional): target repository as `owner/name`.
- `wait-for-completion` (optional): `true` or `false`.
- `wait-for-completion-timeout` (optional): timeout like `1h`.
- `wait-for-completion-interval` (optional): poll interval like `1m`.
- `workflow-logs` (optional): `ignore`, `print`, `output`, or `json-output`.

## Outputs

- `workflow-conclusion`: remote workflow conclusion.
- `workflow-id`: remote workflow run ID.
- `workflow-url`: remote workflow run URL.
- `workflow-logs`: remote workflow logs when `workflow-logs` is `output` or `json-output`.

## Example

```yaml
- name: Trigger release workflow and wait
  id: dispatch
  uses: SolaceDev/solace-public-workflows/workflow-dispatch-and-wait@main
  with:
    workflow: release.yml
    token: ${{ secrets.PERSONAL_ACCESS_TOKEN }}
    ref: main
    inputs: >-
      {
        "version": "1.2.3"
      }

- name: Print remote conclusion
  if: always()
  run: echo "Conclusion: ${{ steps.dispatch.outputs.workflow-conclusion }}"
```

## Notes

- `workflow_dispatch` must be enabled on the target workflow.
- Requires GitHub API version `2026-03-10` or later (handled automatically).

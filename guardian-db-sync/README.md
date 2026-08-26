# Guardian Sync and Report

Runs Guardian's reconcile (ingest → Jira sync → dev-mode close) for scan results already uploaded to S3.

The reconcile routinely runs longer than the API gateway's request timeout, so this action always submits to the asynchronous `POST /api/v1/db_synch_and_report_async` endpoint and polls `GET /api/v1/db_synch_and_report/status/{task_id}` until it finishes. There is no synchronous mode. **This requires a Guardian deployment that has the async endpoints.**

This action does not upload scan files and does not run the vulnerability gate. Use `guardian-vulnerability-gate` as a separate step when needed.

## Required Inputs

- `guardian-url`
- `guardian-key`

## Optional Inputs

- `product-name`
- `product-full-version`
- `unifiers`
- `collection`
- `jira-collection-name`
- `jira-profile`
- `jira-dry-run`
- `poll-interval` — default `10`. Seconds between status polls. The defaults are sufficient; override only if needed.
- `poll-timeout` — default `1800`. Fail if the reconcile hasn't finished by then.
- `upload-logs`

## Outputs

- `product_name`
- `product_version`
- `response_json`

Some large JSON outputs may be omitted automatically to stay within GitHub Actions output limits.

## Example

```yaml
steps:
  - name: Sync Guardian DB and Jira
    id: guardian-sync
    uses: SolaceDev/solace-public-workflows/guardian-db-sync@main
    with:
      guardian-url: ${{ secrets.GUARDIAN_API_URL }}
      guardian-key: ${{ secrets.GUARDIAN_API_TOKEN }}
      product-full-version: 1.110.9
      unifiers: "fossa,prisma"
      collection: test_collection
      jira-collection-name: test_collection_jira_metadata
      jira-profile: CICDSOL

  - name: Run Guardian vulnerability gate
    uses: SolaceDev/solace-public-workflows/guardian-vulnerability-gate@main
    with:
      guardian-url: ${{ secrets.GUARDIAN_API_URL }}
      guardian-key: ${{ secrets.GUARDIAN_API_TOKEN }}
      product-name: ${{ steps.guardian-sync.outputs.product_name }}
      product-version: 1.110.9
      collection: test_collection
      jira-collection: test_collection_jira_metadata
```

## Notes

- If `product-name` is omitted, the action defaults it to `${GITHUB_REPOSITORY#*/}`.
- Guardian now resolves `product_version` from product config and `product_full_version` from the latest uploaded scan metadata when it is not provided.
- Set `unifiers` when you want to explicitly restrict sync to specific uploaded scanner results instead of relying on metadata autodetection.
- The calling workflow is responsible for uploading scan results first. This action sends `product_name` and optionally `product_full_version`, then lets Guardian resolve the canonical scan path.
- Set `upload-logs: "true"` to upload the db sync response directory as a workflow artifact for debugging.

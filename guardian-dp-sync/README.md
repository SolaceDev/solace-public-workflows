# Guardian Sync and Report

Runs Guardian `POST /api/v1/db_synch_and_report` for scan results that were already uploaded to S3.

This action does not upload scan files and does not run the vulnerability gate. Use `guardian-vulnerability-gate` as a separate step when needed.

## Required Inputs

- `guardian-url`
- `guardian-key`
- `product-name`
- `product-version`
- `product-full-version`

## Optional Inputs

- `collection`
- `jira-collection-name`
- `jira-profile`
- `jira-dry-run`
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
      product-name: some-product
      product-version: main
      product-full-version: 1.110.9
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

- The calling workflow is responsible for uploading scan results first. This action derives `scan_path` as `scan-backups/<product-name>/<product-version>/<product-full-version>` and relies on the Guardian API defaults
- Set `upload-logs: "true"` to upload the db sync response directory as a workflow artifact for debugging.

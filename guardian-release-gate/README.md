# Guardian Release Gate

Calls Guardian `POST /api/v1/release_gate` to evaluate a release artifact against vulnerability thresholds before it is published. The gate runs in-memory on the Guardian server using scan data already uploaded during CI (via FOSSA revision or uploaded scan files), so there is no race condition with the latest CI scan.

The action fails the workflow if `overall_blocked` is `true` and `fail-on-blocked` is not overridden. A markdown report is always written to disk; optionally it is appended to the job summary and uploaded as an artifact (suppressed automatically for public repositories).

## Required Inputs

| Input | Description |
|-------|-------------|
| `guardian-url` | Guardian API base URL |
| `guardian-key` | Guardian API bearer token |
| `product-full-version` | Unique build identifier (e.g. `3.2.1.1744100000` or `1.6.0`) |

At least one scan source must also be provided: `fossa-revision`, `fossa-scan-path`, `prisma-scan-path`, or `trivy-scan-path`.

## Optional Inputs

### Product identity

| Input | Default | Description |
|-------|---------|-------------|
| `product-name` | repo name (without org) | Guardian product name |
| `product-version` | `GITHUB_REF_NAME` | Product branch or stream (e.g. `main`) |
| `scan-time` | current UTC time | ISO 8601 timestamp |

### Scan sources

| Input | Description |
|-------|-------------|
| `fossa-revision` | FOSSA revision (git SHA or semver tag) for server-side auto-fetch |
| `fossa-scan-path` | Path to `fossa_scan.json` to upload directly |
| `prisma-scan-path` | Path to `prisma_scan.json` to upload directly |
| `trivy-scan-path` | Path to `trivy_scan.json` to upload directly |

### Thresholds

| Input | Default | Description |
|-------|---------|-------------|
| `thresholds` | `""` | JSON dict of per-severity counts (e.g. `{"Critical":null,"High":10}`). `null` blocks immediately on any finding. Takes precedence over `severity`. |
| `severity` | `""` | JSON array of severities to gate on (e.g. `["Critical","High"]`). Ignored when `thresholds` is set. |

### Slack notification

| Input | Description |
|-------|-------------|
| `slack-channel-id` | Slack channel ID. Omit to skip Slack. |
| `slack-thread-ts` | Thread timestamp for reply |
| `slack-build-url` | CI build URL for the Slack link |
| `slack-title` | Label for the Slack notification |

### Behaviour

| Input | Default | Description |
|-------|---------|-------------|
| `fail-on-blocked` | `"true"` | Exit non-zero when `overall_blocked` is `true` |
| `report-path` | `release_gate_report.md` | Workspace path where the markdown report is written |
| `publish-report` | `"true"` | Append the report to the job summary and upload it as an artifact. Always suppressed for public repositories regardless of this flag — a warning is logged instead. |

## Outputs

| Output | Description |
|--------|-------------|
| `overall_blocked` | `"true"` if the release is blocked |
| `vulnerability_count` | Number of blocking (non-excluded) vulnerabilities |
| `pending_count` | Number of pending (non-blocking) vulnerabilities |
| `report_path` | Workspace path where the markdown report was written |

## Examples

### Dev release — gate before registry push (FOSSA revision + Prisma scan file)

In dev release workflows the Docker image is built locally with `jib:buildTar` and scanned before being pushed to the registry. The FOSSA revision is the SHA the `dev` git tag points to.

```yaml
- name: Fetch SCA configs
  id: fetch_sca_configs
  run: |
    echo "DEV_TAG_CURRENT_SHA=$(git rev-parse dev)" >> $GITHUB_OUTPUT

- name: Tag release image locally
  run: |
    docker tag ${{ steps.load_docker_image.outputs.LOCAL_IMAGE_TAG }} \
      ${{ vars.IMAGE_REGISTRY }}/${{ github.event.repository.name }}:${{ inputs.releaseVersion }}

- name: Prisma Cloud Container Scan
  id: prisma_scan
  uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
  with:
    image_registry: ${{ vars.IMAGE_REGISTRY }}
    image_repo: ${{ github.event.repository.name }}
    image_tag: ${{ inputs.releaseVersion }}
    skip_image_pull: "true"
    pcc_console_url: ${{ vars.PCC_CONSOLE_URL }}
    pcc_user: ${{ steps.secrets.outputs.PRISMACLOUD_ACCESS_KEY_ID }}
    pcc_pass: ${{ steps.secrets.outputs.PRISMACLOUD_SECRET_KEY }}
    guardian_url: ${{ vars.GUARDIAN_URL }}
    guardian_key: ${{ steps.secrets.outputs.GUARDIAN_API_TOKEN }}
    guardian_product_full_version: ${{ inputs.releaseVersion }}

- name: Guardian Release Gate
  id: release_gate
  continue-on-error: ${{ env.ignore_vulnerability_check_failures == 'true' }}
  uses: SolaceDev/solace-public-workflows/guardian-release-gate@main
  with:
    guardian-url: ${{ vars.GUARDIAN_URL }}
    guardian-key: ${{ steps.secrets.outputs.GUARDIAN_API_TOKEN }}
    product-version: "main"
    product-full-version: ${{ inputs.releaseVersion }}
    fossa-revision: ${{ steps.fetch_sca_configs.outputs.DEV_TAG_CURRENT_SHA }}
    prisma-scan-path: "prisma_scan.json"
    fail-on-blocked: "true"
    publish-report: "true"

# Registry push follows only if the gate passed
- name: Registry - Tag/Push
  ...
```

### External release — gate against an already-published registry image (FOSSA semver tag)

In external release workflows the image is already in the registry from the dev release. FOSSA was re-analyzed against the release tag checkout, so `fossa-revision` is the semver tag.

```yaml
- name: Configuring SCA configs
  id: sca_configs
  run: |
    echo "fossa_revision=${{ inputs.release_version }}" >> $GITHUB_OUTPUT

- name: Registry - Login
  uses: docker/login-action@...
  with:
    registry: ${{ vars.IMAGE_REGISTRY }}
    username: ${{ steps.secrets.outputs.REGISTRY_USERNAME }}
    password: ${{ steps.secrets.outputs.REGISTRY_PASSWORD }}

- name: Prisma Cloud Container Scan
  id: prisma_scan
  continue-on-error: ${{ env.ignore_vulnerability_check_failures == 'true' }}
  uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
  with:
    image_registry: ${{ vars.IMAGE_REGISTRY }}
    image_repo: ${{ github.event.repository.name }}
    image_tag: ${{ inputs.release_version }}
    pcc_console_url: ${{ vars.PCC_CONSOLE_URL }}
    pcc_user: ${{ steps.secrets.outputs.PRISMACLOUD_ACCESS_KEY_ID }}
    pcc_pass: ${{ steps.secrets.outputs.PRISMACLOUD_SECRET_KEY }}
    guardian_url: ${{ vars.GUARDIAN_URL }}
    guardian_key: ${{ steps.secrets.outputs.GUARDIAN_API_TOKEN }}
    guardian_product_full_version: ${{ inputs.release_version }}

- name: Guardian Release Gate
  id: release_gate
  continue-on-error: ${{ env.ignore_vulnerability_check_failures == 'true' }}
  uses: SolaceDev/solace-public-workflows/guardian-release-gate@main
  with:
    guardian-url: ${{ vars.GUARDIAN_URL }}
    guardian-key: ${{ steps.secrets.outputs.GUARDIAN_API_TOKEN }}
    product-version: "main"
    product-full-version: ${{ inputs.release_version }}
    fossa-revision: ${{ steps.sca_configs.outputs.fossa_revision }}
    prisma-scan-path: "prisma_scan.json"
    fail-on-blocked: "true"
    publish-report: "true"
```

### Custom thresholds

Block immediately on any Critical, allow up to 5 High:

```yaml
- uses: SolaceDev/solace-public-workflows/guardian-release-gate@main
  with:
    guardian-url: ${{ vars.GUARDIAN_URL }}
    guardian-key: ${{ secrets.GUARDIAN_API_TOKEN }}
    product-full-version: ${{ inputs.version }}
    fossa-revision: ${{ github.sha }}
    thresholds: '{"Critical":null,"High":5}'
    publish-report: "true"
```

## Notes

- **Gate before push**: in dev release workflows, run this action _before_ pushing the image to the registry. A blocked gate means the image is never published.
- **`continue-on-error`**: to mirror the existing `ignore_vulnerability_check_failures` bypass flag used in connector workflows, set `continue-on-error: ${{ env.ignore_vulnerability_check_failures == 'true' }}`.
- **`fossa-revision` in dev vs external**: dev workflows pass the SHA of the `dev` git tag (`git rev-parse dev`) because the release tag does not exist yet. External workflows pass the semver tag (`inputs.release_version`) because FOSSA was re-analyzed against the checked-out release tag.
- **Public repositories**: `publish-report: "true"` is suppressed for public repositories. The action logs a warning and continues — the report is still written to `report-path` on disk for use by subsequent steps.
- **Non-2xx responses from Guardian** are treated as hard failures (`exit 1`). Use `continue-on-error` or `ignore_vulnerability_check_failures` to bypass.

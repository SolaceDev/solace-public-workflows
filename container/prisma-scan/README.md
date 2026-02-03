# Prisma Container Scan Action

A wrapper action that scans Docker container images using Prisma Cloud. This action provides a consistent interface with the container scanning framework while calling the existing `prisma-cloud-scan` action.

## Overview

This action serves as a bridge between the container scanning orchestrator and the existing Prisma Cloud scanning functionality. It accepts environment variables prefixed with `CONTAINER_PRISMA_*` and maps them to the appropriate inputs for the underlying `prisma-cloud-scan` action.

## Features

- Wrapper around existing `prisma-cloud-scan` action
- Consistent environment variable naming with `CONTAINER_PRISMA_*` prefix
- Validates required parameters before execution
- Passes through all scan results and outputs
- Supports expand-and-contract migration pattern

## Usage

This action is typically called by the `container-scan` orchestrator action, but can also be used directly.

### Via Container Scan Orchestrator (Recommended)

```yaml
- name: Scan Container
  uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "prisma"
    additional_scan_params: |
      prisma.image_registry=868978040651.dkr.ecr.us-east-1.amazonaws.com
      prisma.image_repo=my-service
      prisma.image_tag=v1.0.0
      prisma.twistcli_publish=true
    prisma_console_url: ${{ secrets.PRISMA_CONSOLE_URL }}
    prisma_user: ${{ secrets.PRISMA_ACCESS_KEY }}
    prisma_pass: ${{ secrets.PRISMA_SECRET_KEY }}
```

### Direct Usage

```yaml
- name: Prisma Container Scan
  uses: SolaceDev/solace-public-workflows/container/prisma-scan@main
  env:
    CONTAINER_PRISMA_IMAGE_REGISTRY: "868978040651.dkr.ecr.us-east-1.amazonaws.com"
    CONTAINER_PRISMA_IMAGE_REPO: "my-service"
    CONTAINER_PRISMA_IMAGE_TAG: "v1.0.0"
    CONTAINER_PRISMA_PCC_CONSOLE_URL: ${{ secrets.PRISMA_CONSOLE_URL }}
    CONTAINER_PRISMA_PCC_USER: ${{ secrets.PRISMA_ACCESS_KEY }}
    CONTAINER_PRISMA_PCC_PASS: ${{ secrets.PRISMA_SECRET_KEY }}
```

## Environment Variables

All configuration is passed via environment variables with the `CONTAINER_PRISMA_*` prefix.

### Required Variables

| Variable | Description |
|----------|-------------|
| `CONTAINER_PRISMA_IMAGE_REGISTRY` | Docker image registry (e.g., `868978040651.dkr.ecr.us-east-1.amazonaws.com`, `ghcr.io`) |
| `CONTAINER_PRISMA_IMAGE_TAG` | Docker image tag to scan |
| `CONTAINER_PRISMA_PCC_CONSOLE_URL` | Prisma Cloud Console URL (e.g., `https://console.prisma.cloud`) |
| `CONTAINER_PRISMA_PCC_USER` | Prisma Cloud Access Key ID |
| `CONTAINER_PRISMA_PCC_PASS` | Prisma Cloud Secret Access Key |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTAINER_PRISMA_IMAGE_REPO` | Docker image repository name | GitHub repository name |
| `CONTAINER_PRISMA_TWISTCLI_PUBLISH` | Whether to publish scan results to Prisma Cloud Console | `true` |

## Outputs

This action passes through all outputs from the underlying `prisma-cloud-scan` action:

| Output | Description |
|--------|-------------|
| `scan_passed` | Whether the scan passed without blocking issues (`true`/`false`) |
| `vuln_critical` | Number of critical vulnerabilities found |
| `vuln_high` | Number of high severity vulnerabilities found |
| `vuln_medium` | Number of medium severity vulnerabilities found |
| `vuln_low` | Number of low severity vulnerabilities found |

## Examples

### Basic Container Scan

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Login to Amazon ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Prisma Container Scan
        uses: SolaceDev/solace-public-workflows/container/prisma-scan@main
        env:
          CONTAINER_PRISMA_IMAGE_REGISTRY: "868978040651.dkr.ecr.us-east-1.amazonaws.com"
          CONTAINER_PRISMA_IMAGE_TAG: "v1.2.3"
          CONTAINER_PRISMA_PCC_CONSOLE_URL: ${{ secrets.PRISMA_CONSOLE_URL }}
          CONTAINER_PRISMA_PCC_USER: ${{ secrets.PRISMA_ACCESS_KEY }}
          CONTAINER_PRISMA_PCC_PASS: ${{ secrets.PRISMA_SECRET_KEY }}
```

### With Custom Repository Name

```yaml
- name: Prisma Container Scan
  uses: SolaceDev/solace-public-workflows/container/prisma-scan@main
  env:
    CONTAINER_PRISMA_IMAGE_REGISTRY: "ghcr.io"
    CONTAINER_PRISMA_IMAGE_REPO: "myorg/custom-image-name"
    CONTAINER_PRISMA_IMAGE_TAG: "latest"
    CONTAINER_PRISMA_PCC_CONSOLE_URL: ${{ secrets.PRISMA_CONSOLE_URL }}
    CONTAINER_PRISMA_PCC_USER: ${{ secrets.PRISMA_ACCESS_KEY }}
    CONTAINER_PRISMA_PCC_PASS: ${{ secrets.PRISMA_SECRET_KEY }}
```

### Without Publishing to Console

```yaml
- name: Prisma Container Scan (No Publish)
  uses: SolaceDev/solace-public-workflows/container/prisma-scan@main
  env:
    CONTAINER_PRISMA_IMAGE_REGISTRY: "docker.io"
    CONTAINER_PRISMA_IMAGE_REPO: "myorg/myapp"
    CONTAINER_PRISMA_IMAGE_TAG: "test-123"
    CONTAINER_PRISMA_TWISTCLI_PUBLISH: "false"
    CONTAINER_PRISMA_PCC_CONSOLE_URL: ${{ secrets.PRISMA_CONSOLE_URL }}
    CONTAINER_PRISMA_PCC_USER: ${{ secrets.PRISMA_ACCESS_KEY }}
    CONTAINER_PRISMA_PCC_PASS: ${{ secrets.PRISMA_SECRET_KEY }}
```

### Using Scan Results

```yaml
- name: Prisma Container Scan
  id: prisma
  uses: SolaceDev/solace-public-workflows/container/prisma-scan@main
  env:
    CONTAINER_PRISMA_IMAGE_REGISTRY: "ghcr.io"
    CONTAINER_PRISMA_IMAGE_TAG: "v2.0.0"
    CONTAINER_PRISMA_PCC_CONSOLE_URL: ${{ secrets.PRISMA_CONSOLE_URL }}
    CONTAINER_PRISMA_PCC_USER: ${{ secrets.PRISMA_ACCESS_KEY }}
    CONTAINER_PRISMA_PCC_PASS: ${{ secrets.PRISMA_SECRET_KEY }}

- name: Check Scan Results
  run: |
    echo "Scan passed: ${{ steps.prisma.outputs.scan_passed }}"
    echo "Critical vulnerabilities: ${{ steps.prisma.outputs.vuln_critical }}"
    echo "High vulnerabilities: ${{ steps.prisma.outputs.vuln_high }}"
```

## How It Works

This action is a thin wrapper that:

1. **Validates** required environment variables
2. **Maps** `CONTAINER_PRISMA_*` variables to the inputs expected by `prisma-cloud-scan`
3. **Calls** the existing `prisma-cloud-scan` action at the repository root
4. **Passes through** all outputs from the underlying action

### Environment Variable Mapping

| Container Variable | Prisma Cloud Scan Input |
|-------------------|-------------------------|
| `CONTAINER_PRISMA_IMAGE_REGISTRY` | `image_registry` |
| `CONTAINER_PRISMA_IMAGE_REPO` | `image_repo` |
| `CONTAINER_PRISMA_IMAGE_TAG` | `image_tag` |
| `CONTAINER_PRISMA_PCC_CONSOLE_URL` | `pcc_console_url` |
| `CONTAINER_PRISMA_PCC_USER` | `pcc_user` |
| `CONTAINER_PRISMA_PCC_PASS` | `pcc_pass` |
| `CONTAINER_PRISMA_TWISTCLI_PUBLISH` | `twistcli_publish` |

## Expand-and-Contract Pattern

This action follows an expand-and-contract migration pattern:

1. **Existing action** (`prisma-cloud-scan/`) remains unchanged and available
2. **New wrapper** (`container/prisma-scan/`) provides the new interface
3. **Teams can migrate** gradually from the old to new structure
4. **Future consolidation** may occur once all teams have migrated

## Blocking Behavior

The scan will **block the build** if:
- Critical severity vulnerabilities are found
- High severity vulnerabilities are found

The scan will **pass** if:
- Only medium or low severity issues are found
- No issues are found

## Troubleshooting

### Image Pull Failures

If the scan fails to pull the image, ensure you authenticate with the registry first:

```yaml
# For AWS ECR
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: us-east-1

- name: Login to Amazon ECR
  uses: aws-actions/amazon-ecr-login@v2
```

### Missing Environment Variables

The action will fail with a clear error message if required variables are missing:

```
❌ Error: CONTAINER_PRISMA_IMAGE_REGISTRY is required
```

Ensure all required variables are set before calling the action.

### Scan Results Location

Scan results are saved to `pcc_scan_results.json` in the working directory. You can access this file in subsequent steps if needed.

## Related Documentation

- [Container Scan Orchestrator](../container-scan/README.md) - Wrapper for running multiple scanners
- [Prisma Cloud Scan](../../prisma-cloud-scan/README.md) - Underlying Prisma Cloud scanning action
- [Prisma Cloud Documentation](https://docs.prismacloud.io/) - Official Prisma Cloud documentation

## Support

For issues with this wrapper action, please report them in the solace-public-workflows repository.
For Prisma Cloud-specific issues, refer to the Prisma Cloud documentation or support channels.

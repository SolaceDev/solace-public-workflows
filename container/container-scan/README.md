# Container Scan Action

Unified orchestrator for container image security and compliance scanning. Supports multiple scanning tools including FOSSA and Prisma Cloud.

## Overview

This action provides a single interface to run container image scans using various security tools. It:
- Orchestrates multiple container scanners
- Provides a consistent parameter interface
- Allows flexible scanner selection
- Supports scanner-specific configuration

## Supported Scanners

| Scanner | Purpose | Documentation |
|---------|---------|---------------|
| `fossa` | License compliance and vulnerability detection | [fossa-scan README](../fossa-scan/README.md) |
| `prisma` | Container security scanning with Prisma Cloud | [prisma-scan README](../prisma-scan/README.md) |

## Usage

### Basic Scan with FOSSA

```yaml
- name: Scan Container Image
  uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.image=ghcr.io/solacedev/my-app:v1.0.0
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Scan with Multiple Scanners

```yaml
- name: Scan Container Image
  uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa,prisma"
    additional_scan_params: |
      fossa.image=ghcr.io/solacedev/my-app:v1.0.0
      fossa.project=MyOrg_my-app
      prisma.image_registry=ghcr.io
      prisma.image_repo=solacedev/my-app
      prisma.image_tag=v1.0.0
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    prisma_console_url: ${{ secrets.PRISMA_CONSOLE_URL }}
    prisma_user: ${{ secrets.PRISMA_USER }}
    prisma_pass: ${{ secrets.PRISMA_PASS }}
```

### Complete Workflow Example

```yaml
name: Container Scan

on:
  push:
    branches: [main]
  pull_request:

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build Container Image
        run: |
          docker build -t ghcr.io/solacedev/my-app:${{ github.sha }} .
          docker push ghcr.io/solacedev/my-app:${{ github.sha }}

      - name: Scan Container
        uses: SolaceDev/solace-public-workflows/container/container-scan@main
        with:
          scanners: "fossa"
          additional_scan_params: |
            fossa.image=ghcr.io/solacedev/my-app:${{ github.sha }}
            fossa.project=MyOrg_my-app
            fossa.branch=${{ github.ref_name }}
            fossa.revision=${{ github.sha }}
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

## Inputs

### Required Inputs (Scanner-Dependent)

The required inputs depend on which scanners you're using. See individual scanner documentation for details.

### Common Inputs

| Input | Description | Default | Required |
|-------|-------------|---------|----------|
| `scanners` | Comma-separated list of scanners | `"fossa"` | No |
| `additional_scan_params` | Scanner-specific parameters (see below) | `""` | No |

### FOSSA Inputs

| Input | Description | Required |
|-------|-------------|----------|
| `fossa_api_key` | FOSSA API key | Yes (if using fossa) |

### Prisma Cloud Inputs

| Input | Description | Required |
|-------|-------------|----------|
| `prisma_console_url` | Prisma Cloud Console URL | Yes (if using prisma) |
| `prisma_user` | Prisma Cloud Access Key | Yes (if using prisma) |
| `prisma_pass` | Prisma Cloud Secret Key | Yes (if using prisma) |

## Parameter System

The `additional_scan_params` input uses a flexible key-value format:

```yaml
additional_scan_params: |
  scanner.parameter=value
  scanner.another_param=value
```

Parameters are automatically converted to environment variables:
- `fossa.image=ghcr.io/repo:tag` → `CONTAINER_FOSSA_IMAGE=ghcr.io/repo:tag`
- `prisma.image_registry=ghcr.io` → `CONTAINER_PRISMA_IMAGE_REGISTRY=ghcr.io`

### FOSSA Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `fossa.image` | Container image to scan (REQUIRED) | `ghcr.io/solacedev/my-app:v1.0.0` |
| `fossa.project` | Project name override | `MyOrg_my-app` |
| `fossa.branch` | Branch name | `main` |
| `fossa.revision` | Git commit SHA | `abc123` |
| `fossa.skip_test` | Skip policy test | `true` |
| `fossa.debug` | Enable debug logging | `true` |

See [fossa-scan README](../fossa-scan/README.md) for complete parameter list.

### Prisma Cloud Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `prisma.image_registry` | Container registry | `ghcr.io` |
| `prisma.image_repo` | Repository name | `solacedev/my-app` |
| `prisma.image_tag` | Image tag | `v1.0.0` |

See [prisma-scan README](../prisma-scan/README.md) for complete parameter list.

## Examples

### Scan Docker Hub Image

```yaml
- uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.image=solace/pubsubplus:latest
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Scan GHCR Image with Custom Project Name

```yaml
- uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.image=ghcr.io/solacedev/my-app:v1.0.0
      fossa.project=MyOrg_my-app-container
      fossa.team=Platform Team
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Scan AWS ECR Image

```yaml
- name: Login to ECR
  uses: aws-actions/amazon-ecr-login@v2

- uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.image=123456789012.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0.0
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Debug Mode

```yaml
- uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.image=ghcr.io/solacedev/my-app:v1.0.0
      fossa.debug=true
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Skip Policy Test

```yaml
- uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.image=ghcr.io/solacedev/my-app:v1.0.0
      fossa.skip_test=true
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

## Registry Authentication

Most container registries require authentication. Ensure you authenticate before scanning:

### GitHub Container Registry (GHCR)

```yaml
- uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

### AWS ECR

```yaml
- uses: aws-actions/amazon-ecr-login@v2
```

### Docker Hub

```yaml
- uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKERHUB_USERNAME }}
    password: ${{ secrets.DOCKERHUB_TOKEN }}
```

## How It Works

1. **Parameter Parsing**: Converts `additional_scan_params` into environment variables with `CONTAINER_*` prefix
2. **Scanner Execution**: Runs requested scanners conditionally based on `scanners` input
3. **Results**: Each scanner reports results independently

### Parameter Conversion Flow

```
Input:
  additional_scan_params: |
    fossa.image=ghcr.io/solacedev/my-app:v1.0.0
    fossa.project=MyOrg_my-app

Conversion:
  CONTAINER_FOSSA_IMAGE=ghcr.io/solacedev/my-app:v1.0.0
  CONTAINER_FOSSA_PROJECT=MyOrg_my-app

Usage by Scanner:
  fossa-scan action reads CONTAINER_FOSSA_* variables
  Builds CLI: fossa container analyze ghcr.io/solacedev/my-app:v1.0.0 --project MyOrg_my-app
```

## Architecture

```
container-scan (orchestrator)
├── Parses additional_scan_params
├── Converts to CONTAINER_* env vars
├── Conditionally calls:
│   ├── fossa-scan (if 'fossa' in scanners)
│   └── prisma-scan (if 'prisma' in scanners)
```

Each scanner action:
1. Reads `CONTAINER_SCANNER_*` environment variables
2. Converts them to scanner-specific CLI arguments
3. Executes the scanner
4. Reports results

## Relationship to Other Actions

| Action | Purpose |
|--------|---------|
| [container/fossa-scan](../fossa-scan/README.md) | FOSSA container scanning (called by this action) |
| [container/prisma-scan](../prisma-scan/README.md) | Prisma Cloud scanning (called by this action) |
| [.github/actions/sca/sca-scan](../../.github/actions/sca/sca-scan/README.md) | Source code dependency scanning |

## Troubleshooting

### "Invalid additional_scan_params line"
Ensure each line follows `key=value` format with no spaces around the `=`:
```yaml
# Good
fossa.image=ghcr.io/repo:tag

# Bad
fossa.image = ghcr.io/repo:tag
```

### "Permission denied" accessing image
Authenticate to the registry before scanning (see [Registry Authentication](#registry-authentication))

### Scanner not running
Check that the scanner name is spelled correctly in the `scanners` input:
```yaml
scanners: "fossa"  # Correct
scanners: "FOSSA"  # Wrong - case sensitive
```

### Missing required parameters
Each scanner has required parameters. For FOSSA:
```yaml
additional_scan_params: |
  fossa.image=ghcr.io/repo:tag  # REQUIRED
```

## Best Practices

1. **Always specify the full image path** including registry, repository, and tag
2. **Use dynamic tags** in CI/CD (commit SHA, PR number) for traceability
3. **Authenticate to registries** before scanning private images
4. **Use secrets** for API keys and credentials
5. **Set project metadata** (project, branch, revision) for better tracking in scanner dashboards

## Related Documentation

- [FOSSA Container Scan](../fossa-scan/README.md)
- [Prisma Cloud Scan](../prisma-scan/README.md)
- [SCA Scan](../../.github/actions/sca/sca-scan/README.md)

## Support

For issues or questions:
- FOSSA scanning: See [FOSSA CLI documentation](https://github.com/fossas/fossa-cli)
- Prisma scanning: See [Prisma Cloud documentation](https://docs.paloaltonetworks.com/prisma/prisma-cloud)
- Action issues: Open an issue in the repository

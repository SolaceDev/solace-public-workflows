# FOSSA Container Scan Action

Scans container images for security vulnerabilities and license compliance using the FOSSA CLI.

## Overview

This action performs container image scanning using FOSSA's container analysis capabilities. It can:
- Scan container images from any registry (Docker Hub, GHCR, ECR, etc.)
- Detect dependencies and licenses within container layers
- Report security vulnerabilities
- Enforce license policies

## Usage

This action is typically called by the [container-scan](../container-scan/README.md) orchestrator, but can also be used directly.

### Direct Usage

```yaml
- name: Scan Container with FOSSA
  uses: SolaceDev/solace-public-workflows/container/fossa-scan@main
  env:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
```

### Via Container Scan Orchestrator (Recommended)

```yaml
- name: Scan Container Image
  uses: SolaceDev/solace-public-workflows/container/container-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.image=ghcr.io/solacedev/my-app:v1.0.0
      fossa.project=MyOrg_my-app
      fossa.branch=main
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

## Environment Variables

All configuration is done through environment variables with the `CONTAINER_FOSSA_` prefix.

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `FOSSA_API_KEY` | FOSSA API key for authentication | From secrets |
| `CONTAINER_FOSSA_IMAGE` | Container image to scan | `ghcr.io/solacedev/my-app:v1.0.0` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTAINER_FOSSA_SKIP_TEST` | Skip the policy test step | `false` |
| `CONTAINER_FOSSA_DEBUG` | Enable debug logging | `false` |
| `CONTAINER_FOSSA_PROJECT` | Override project name | Auto-detected |
| `CONTAINER_FOSSA_REVISION` | Git revision/commit SHA | Auto-detected |
| `CONTAINER_FOSSA_BRANCH` | Git branch name | Auto-detected |
| `CONTAINER_FOSSA_TITLE` | Project title in FOSSA | Auto-generated |
| `CONTAINER_FOSSA_TEAM` | Team within FOSSA organization | None |
| `CONTAINER_FOSSA_POLICY` | Specific policy to enforce | Default policy |

## Parameter Configuration

The action uses a JSON-based parameter system for flexible configuration. See [fossa-container-params.json](./fossa-container-params.json) for all available parameters.

### Adding Parameters via additional_scan_params

When using the container-scan orchestrator, parameters are converted from `fossa.key=value` format to `CONTAINER_FOSSA_KEY` environment variables:

```yaml
additional_scan_params: |
  fossa.image=ghcr.io/solacedev/my-app:v1.0.0
  fossa.project=MyOrg_my-app
  fossa.branch=main
  fossa.debug=true
```

This automatically converts to:
- `fossa.image` → `CONTAINER_FOSSA_IMAGE`
- `fossa.project` → `CONTAINER_FOSSA_PROJECT`
- `fossa.branch` → `CONTAINER_FOSSA_BRANCH`
- `fossa.debug` → `CONTAINER_FOSSA_DEBUG`

## Container Image Formats

The action supports various container image formats:

### Docker Hub
```yaml
CONTAINER_FOSSA_IMAGE: solace/pubsubplus:latest
```

### GitHub Container Registry (GHCR)
```yaml
CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
```

### AWS ECR
```yaml
CONTAINER_FOSSA_IMAGE: 123456789012.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0.0
```

### Google Container Registry (GCR)
```yaml
CONTAINER_FOSSA_IMAGE: gcr.io/my-project/my-app:v1.0.0
```

## Authentication

Container registries may require authentication. Ensure you've logged in before running the scan:

```yaml
- name: Login to GHCR
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}

- name: Scan Container
  uses: SolaceDev/solace-public-workflows/container/fossa-scan@main
  env:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
```

## How It Works

1. **Installation**: Checks if FOSSA CLI is installed, installs if needed
2. **Parameter Parsing**: Converts environment variables to CLI arguments using [parse-fossa-container-params.sh](./parse-fossa-container-params.sh)
3. **Analysis**: Runs `fossa container analyze <image>` to scan the container
4. **Testing**: Runs `fossa container test <image>` to check policy compliance (unless skipped)

## Examples

### Basic Scan
```yaml
- name: Scan Container
  uses: SolaceDev/solace-public-workflows/container/fossa-scan@main
  env:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
```

### Scan with Custom Project Name
```yaml
- name: Scan Container
  uses: SolaceDev/solace-public-workflows/container/fossa-scan@main
  env:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
    CONTAINER_FOSSA_PROJECT: MyOrg_my-app-container
    CONTAINER_FOSSA_BRANCH: main
```

### Skip Policy Test
```yaml
- name: Scan Container
  uses: SolaceDev/solace-public-workflows/container/fossa-scan@main
  env:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
    CONTAINER_FOSSA_SKIP_TEST: "true"
```

### Debug Mode
```yaml
- name: Scan Container
  uses: SolaceDev/solace-public-workflows/container/fossa-scan@main
  env:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
    CONTAINER_FOSSA_DEBUG: "true"
```

## Relationship to SCA Scanning

This action is separate from the [SCA fossa-scan](../../.github/actions/sca/fossa-scan/README.md) action:

- **SCA fossa-scan**: Scans source code dependencies (npm, pip, maven, etc.)
- **Container fossa-scan**: Scans container images and their contents

Both use FOSSA but serve different purposes and use different FOSSA CLI commands (`fossa analyze` vs `fossa container analyze`).

## Troubleshooting

### "CONTAINER_FOSSA_IMAGE is required"
Set the image environment variable:
```yaml
env:
  CONTAINER_FOSSA_IMAGE: ghcr.io/solacedev/my-app:v1.0.0
```

### "Permission denied" accessing image
Ensure you've authenticated to the registry before scanning:
```yaml
- uses: docker/login-action@v3
  # ... login configuration
```

### Policy test fails
If you want to scan without enforcing policies:
```yaml
env:
  CONTAINER_FOSSA_SKIP_TEST: "true"
```

## Related Actions

- [container-scan](../container-scan/README.md) - Orchestrator that can run multiple container scanners
- [prisma-scan](../prisma-scan/README.md) - Prisma Cloud container scanning
- [SCA fossa-scan](../../.github/actions/sca/fossa-scan/README.md) - Source code dependency scanning

## References

- [FOSSA CLI Documentation](https://github.com/fossas/fossa-cli)
- [FOSSA Container Scanning](https://docs.fossa.com/docs/container-scanning)

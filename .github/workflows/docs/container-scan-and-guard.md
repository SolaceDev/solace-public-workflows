# Container Scan and Guard Workflow

Container image security scanning with FOSSA and optional Prisma Cloud integration.

## Overview

The container scan and guard workflow provides automated security scanning of container images. It supports multiple scanners (FOSSA, Prisma Cloud) with configurable policy enforcement for licensing and vulnerabilities.

**Workflow Path**: [`../.github/workflows/container-scan-and-guard.yaml`](../container-scan-and-guard.yaml)

## Features

- **FOSSA container scanning** for dependencies and vulnerabilities
- **Prisma Cloud scanning** (optional)
- **Config-driven policy enforcement** via workflow-config.json
- **Split enforcement gates** for licensing vs vulnerabilities
- **ECR authentication** via Vault
- **Privacy mode** auto-enabled for public repositories
- **Dashboard links** with correct Solace organization {org_id}

## Usage

### Basic Usage

```yaml
name: Container Security Scan

on:
  workflow_run:
    workflows: ["Build Image"]
    types: [completed]

jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    with:
      container_image: "${{ vars.ECR_REGISTRY }}/my-service:${{ github.sha }}"
      use_vault: true
      config_file: '.github/workflow-config.json'
```

### With Custom Project ID

```yaml
jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    with:
      container_image: "my-registry/my-image:tag"
      use_vault: true
      additional_scan_params: |
        fossa.project=custom+{org_id}/SolaceDev_my-custom-project
```

### Multiple Scanners

```yaml
jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    with:
      container_image: "my-registry/my-image:tag"
      scanners: "fossa,prisma"
      use_vault: true
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `container_image` | Yes | - | Container image to scan (registry/repository:tag format) |
| `scanners` | No | `"fossa"` | Comma-separated list of scanners to run: `fossa`, `prisma` |
| `skip_fossa_gate` | No | `false` | EMERGENCY: Skip FOSSA gate (requires admin permission) |
| `bypass_justification` | No | (empty) | REQUIRED: Justification for bypassing FOSSA gate |
| `use_vault` | No | `false` | Retrieve secrets from Vault (true for private repos) |
| `config_file` | No | `.github/workflow-config.json` | Path to workflow configuration file |
| `additional_scan_params` | No | (empty) | Additional scanner-specific parameters |
| `fossa_licensing_mode` | No | `"REPORT"` | Licensing check mode: `BLOCK` or `REPORT` |
| `fossa_licensing_block_on` | No | `"policy_conflict"` | What to block on for licensing |
| `fossa_vulnerability_mode` | No | `"REPORT"` | Vulnerability check mode: `BLOCK` or `REPORT` |
| `fossa_vulnerability_block_on` | No | `"critical,high"` | Vulnerability severities to block on |
| `slack_channel` | No | `"#sc-deploy-cicd-activity"` | Slack channel for failure notifications |

**Note**: When `config_file` is provided, configuration from the file takes precedence over individual inputs.

## Configuration File

Create `.github/workflow-config.json`:

```json
{
  "container_scanning": {
    "fossa": {
      "policy": {
        "mode": "BLOCK",
        "block_on": ["policy_conflict", "policy_flag"]
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical", "high"]
      },
      "project_id": "SolaceDev_my-service",
      "team": "Platform Engineering",
      "labels": ["production", "container", "critical-path"]
    },
    "secrets": {
      "vault": {
        "secret_path": "secret/data/path/to/secrets",
        "aws_role": "secret/data/path/to/aws-role"
      }
    }
  },
  "slack_channel": "#platform-alerts"
}
```

**See**: [Workflow Config Schema Documentation](../../../workflow-config-loader/workflow-config-schema.md)

## Additional Scan Parameters

Use `additional_scan_params` for FOSSA-specific options:

```yaml
additional_scan_params: |
  fossa.debug=true
  fossa.team=Platform Team
  fossa.project=custom+{org_id}/SolaceDev_my-container
  fossa.project_label=critical,production
```

**Common Parameters**:
- `fossa.debug` - Enable debug logging
- `fossa.project` - Override project ID (format: `custom+{org_id}/SolaceDev_{name}`)
- `fossa.team` - FOSSA team name
- `fossa.project_label` - Comma-separated labels
- `fossa.privacy_mode` - Override privacy mode detection

**See**: [Container FOSSA Scan Action](../../../container/fossa-scan/README.md) for full parameter list

## Scanners

### FOSSA (Default)

Scans container image dependencies and checks for:
- License policy violations
- Known security vulnerabilities
- Dependency compliance

### Prisma Cloud (Optional)

Additional security scanning with:
- CVE detection
- Compliance checks
- Runtime security analysis

Enable via:

```yaml
with:
  scanners: "fossa,prisma"
```

## Emergency Bypass Gate

```yaml
with:
  skip_fossa_gate: true
  bypass_justification: "JIRA-123: Emergency hotfix for production incident"
```

**Requirements**:
- Caller must have **admin** repository permissions
- Must provide `bypass_justification`
- Bypass is logged and visible in workflow output

## Privacy Mode

Privacy mode prevents FOSSA from exposing internal dependency information.

**Automatic Detection**:
- Public repositories: Privacy mode enabled
- Private repositories: Privacy mode disabled

**Manual Override**:

```yaml
additional_scan_params: |
  fossa.privacy_mode=false
```

## ECR Authentication

For private ECR images, use Vault to retrieve AWS credentials:

```json
{
  "container_scanning": {
    "secrets": {
      "vault": {
        "aws_role": "secret/data/path/to/aws-sts"
      }
    }
  }
}
```

The workflow automatically:
1. Authenticates to Vault
2. Retrieves AWS STS credentials
3. Logs into ECR
4. Pulls the container image for scanning

## FOSSA Dashboard Links

Dashboard URLs use Solace's organization ID:

```
https://app.fossa.com/projects/custom%2B{org_id}%2F{project_id}
```

**Format**: `custom+{org_id}/SolaceDev_{container_name}`

## Troubleshooting

### Image Pull Failed

**Error**: `Unable to pull image`

**Solutions**:
- Verify image exists and tag is correct
- Check ECR authentication (Vault AWS role configured)
- Ensure image is accessible from GitHub Actions runners

### FOSSA Scan Failed

**Error**: `FOSSA scan failed`

**Solutions**:
- Enable debug mode: `fossa.debug=true`
- Check FOSSA API key is valid
- Verify project ID format is correct

### Configuration File Not Found

**Error**: `❌ Configuration file not found`

**Solution**: Create `.github/workflow-config.json` or specify correct path

## Examples

### Basic Container Scan After Build

```yaml
name: Build and Scan

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.build.outputs.image_tag }}
    steps:
      - name: Build Image
        id: build
        run: |
          docker build -t my-image:${{ github.sha }} .
          echo "image_tag=${{ github.sha }}" >> $GITHUB_OUTPUT

  scan:
    needs: build
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    with:
      container_image: "my-registry/my-image:${{ needs.build.outputs.image_tag }}"
      use_vault: true
```

### Scan on Release

```yaml
name: Release Container Scan

on:
  release:
    types: [published]

jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    with:
      container_image: "${{ vars.ECR_REGISTRY }}/my-service:${{ github.event.release.tag_name }}"
      use_vault: true
      config_file: '.github/workflow-config.json'
```

### Multi-Scanner with Custom Config

```yaml
jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    with:
      container_image: "my-registry/my-image:latest"
      scanners: "fossa,prisma"
      use_vault: true
      additional_scan_params: |
        fossa.debug=true
        fossa.team=Backend Team
        fossa.project_label=production,critical
```

## Related Documentation

- [Workflow Config Loader](../../../workflow-config-loader/README.md)
- [Container Scan Action](../../../container/container-scan/README.md)
- [Container FOSSA Scan](../../../container/fossa-scan/README.md)
- [Prisma Cloud Scan](../../../container/prisma-scan/README.md)
- [FOSSA Guard Action](../../../.github/actions/fossa-guard/README.md)

## Support

- **Issues**: [GitHub Issues](https://github.com/SolaceDev/solace-public-workflows/issues)

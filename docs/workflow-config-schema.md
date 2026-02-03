# Workflow Configuration Schema

## Overview

This document defines the JSON schema for `.github/workflow-config.json`, which centralizes configuration for container scanning workflows. By moving policy configuration from workflow inputs to a JSON file, we reduce workflow inputs from **15 to 6** (60% reduction) while improving maintainability and reusability.

## Benefits

- **Reduced Workflow Complexity**: Only 6 runtime inputs instead of 15+
- **Configuration Reusability**: One config file shared across multiple workflows
- **Better Documentation**: Config file is versioned and discoverable in the repo
- **Team Flexibility**: Teams can customize scanning policies without workflow changes
- **Backward Compatible**: Existing workflows without `container_scanning` field continue to work

## File Location

**Path**: `.github/workflow-config.json` (in your repository root)

This file may already exist in your repository for other build configuration. The `container_scanning` field is **optional** and can be added alongside existing configuration.

## Schema Structure

### Root Level

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "squad": "string",
  "service_name": "string",
  "slack_channel": "string",
  "container_scanning": {
    // Container scanning configuration (optional)
  }
}
```

### Container Scanning Section

```json
{
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa", "prisma"],
    "fossa": {
      "policy": {
        "mode": "REPORT | BLOCK",
        "block_on": ["policy_conflict", "policy_flag", ...]
      },
      "vulnerability": {
        "mode": "REPORT | BLOCK",
        "block_on": ["critical", "high", "medium", "low"]
      },
      "project_id": "string or null",
      "scan_params": {
        "debug": false,
        "skip_test": false,
        "timeout": 3600
      }
    },
    "prisma": {
      "policy": {
        "mode": "REPORT | BLOCK",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "REPORT | BLOCK",
        "block_on": ["critical", "high", "medium", "low"]
      },
      "console_url": "https://console.prismacloud.io",
      "scan_params": {
        "twistcli_publish": true
      }
    },
    "secrets": {
      "vault": {
        "secret_path": "secret/data/tools/githubactions"
      }
    }
  }
}
```

## Field Reference

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `squad` | string | No | Team or squad name (existing field) |
| `service_name` | string | No | Service identifier (existing field) |
| `slack_channel` | string | No | Slack channel for notifications (e.g., `#team-alerts`) |
| `container_scanning` | object | No | Container scanning configuration (see below) |

### Container Scanning Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | boolean | No | `true` | Enable/disable container scanning |
| `scanners` | array | No | `["fossa"]` | List of scanners to run: `fossa`, `prisma` |
| `fossa` | object | No | See defaults | FOSSA scanner configuration |
| `prisma` | object | No | See defaults | Prisma Cloud scanner configuration |
| `secrets` | object | No | See defaults | Secret management configuration |

### FOSSA Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `fossa.policy.mode` | string | No | `REPORT` | Policy enforcement mode: `REPORT` or `BLOCK` |
| `fossa.policy.block_on` | array | No | `["policy_conflict"]` | Policy issues to block on |
| `fossa.vulnerability.mode` | string | No | `REPORT` | Vulnerability enforcement mode: `REPORT` or `BLOCK` |
| `fossa.vulnerability.block_on` | array | No | `["critical", "high"]` | Vulnerability severities to block on |
| `fossa.project_id` | string | No | `null` | Override FOSSA project ID (auto-detected if null) |
| `fossa.scan_params.debug` | boolean | No | `false` | Enable debug logging |
| `fossa.scan_params.skip_test` | boolean | No | `false` | Skip policy test step |
| `fossa.scan_params.timeout` | number | No | `3600` | Scan timeout in seconds |

**Policy Block On Options**:
- `policy_conflict` - License policy violations
- `policy_flag` - Flagged licenses
- `deny` - Denied licenses

**Vulnerability Severities**:
- `critical` - Critical vulnerabilities
- `high` - High severity vulnerabilities
- `medium` - Medium severity vulnerabilities
- `low` - Low severity vulnerabilities

### Prisma Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prisma.policy.mode` | string | No | `REPORT` | Policy enforcement mode: `REPORT` or `BLOCK` |
| `prisma.policy.block_on` | array | No | `["policy_conflict"]` | Policy issues to block on |
| `prisma.vulnerability.mode` | string | No | `REPORT` | Vulnerability enforcement mode: `REPORT` or `BLOCK` |
| `prisma.vulnerability.block_on` | array | No | `["critical", "high"]` | Vulnerability severities to block on |
| `prisma.console_url` | string | No | `https://console.prismacloud.io` | Prisma Cloud console URL |
| `prisma.scan_params.twistcli_publish` | boolean | No | `true` | Publish scan results to console |

### Secrets Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `secrets.vault.secret_path` | string | No | `secret/data/tools/githubactions` | Vault path for FOSSA_API_KEY and other secrets |

## Complete Examples

### Example 1: Minimal Configuration (Report Only)

```json
{
  "squad": "platform-team",
  "service_name": "my-service",
  "slack_channel": "#platform-alerts",
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa"]
  }
}
```

**Result**: Uses all defaults - REPORT mode for both policy and vulnerabilities, blocks on policy_conflict and critical/high vulnerabilities.

### Example 2: Strict Blocking Mode

```json
{
  "squad": "security-team",
  "service_name": "critical-service",
  "slack_channel": "#security-alerts",
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa"],
    "fossa": {
      "policy": {
        "mode": "BLOCK",
        "block_on": ["policy_conflict", "policy_flag", "deny"]
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical", "high"]
      }
    }
  }
}
```

**Result**: Blocks workflow on ANY policy issue or critical/high vulnerabilities.

### Example 3: Multi-Scanner Configuration

```json
{
  "squad": "devops-team",
  "service_name": "api-gateway",
  "slack_channel": "#devops-alerts",
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa", "prisma"],
    "fossa": {
      "policy": {
        "mode": "REPORT",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical"]
      }
    },
    "prisma": {
      "policy": {
        "mode": "REPORT",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical", "high"]
      },
      "console_url": "https://console.prismacloud.io"
    }
  }
}
```

**Result**: Runs both FOSSA and Prisma scans. Blocks only on critical/high vulnerabilities, reports policy issues.

### Example 4: Custom Vault Path

```json
{
  "squad": "backend-team",
  "service_name": "auth-service",
  "slack_channel": "#backend-alerts",
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa"],
    "fossa": {
      "policy": {
        "mode": "REPORT",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "REPORT",
        "block_on": ["critical", "high"]
      }
    },
    "secrets": {
      "vault": {
        "secret_path": "secret/data/teams/backend/githubactions"
      }
    }
  }
}
```

**Result**: Uses custom Vault path for retrieving FOSSA_API_KEY and other secrets.

### Example 5: Debug Mode for Troubleshooting

```json
{
  "squad": "frontend-team",
  "service_name": "web-app",
  "slack_channel": "#frontend-alerts",
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa"],
    "fossa": {
      "policy": {
        "mode": "REPORT",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "REPORT",
        "block_on": ["critical", "high"]
      },
      "scan_params": {
        "debug": true,
        "skip_test": false,
        "timeout": 7200
      }
    }
  }
}
```

**Result**: Enables debug logging and increases timeout to 2 hours for troubleshooting.

## Common Scenarios

### Scenario 1: New Service (Permissive)

**Use Case**: New service in development, want visibility but not blocking

```json
{
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa"],
    "fossa": {
      "policy": { "mode": "REPORT" },
      "vulnerability": { "mode": "REPORT" }
    }
  }
}
```

### Scenario 2: Production Service (Strict)

**Use Case**: Production service, must block on security issues

```json
{
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa", "prisma"],
    "fossa": {
      "policy": { "mode": "BLOCK", "block_on": ["policy_conflict"] },
      "vulnerability": { "mode": "BLOCK", "block_on": ["critical", "high"] }
    },
    "prisma": {
      "policy": { "mode": "BLOCK", "block_on": ["policy_conflict"] },
      "vulnerability": { "mode": "BLOCK", "block_on": ["critical", "high"] }
    }
  }
}
```

### Scenario 3: Gradual Rollout

**Use Case**: Start permissive, gradually increase strictness

**Phase 1: Visibility Only**
```json
{
  "fossa": {
    "policy": { "mode": "REPORT" },
    "vulnerability": { "mode": "REPORT" }
  }
}
```

**Phase 2: Block Critical Only**
```json
{
  "fossa": {
    "policy": { "mode": "REPORT" },
    "vulnerability": { "mode": "BLOCK", "block_on": ["critical"] }
  }
}
```

**Phase 3: Full Enforcement**
```json
{
  "fossa": {
    "policy": { "mode": "BLOCK", "block_on": ["policy_conflict"] },
    "vulnerability": { "mode": "BLOCK", "block_on": ["critical", "high"] }
  }
}
```

### Scenario 4: Custom Project ID

**Use Case**: Multiple services share a FOSSA project

```json
{
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa"],
    "fossa": {
      "project_id": "MyOrg_shared-infrastructure"
    }
  }
}
```

### Scenario 5: Disable Scanning Temporarily

**Use Case**: Temporarily disable scanning

```json
{
  "container_scanning": {
    "enabled": false
  }
}
```

## Workflow Usage

### Basic Usage

```yaml
jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    secrets:
      FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    with:
      container_image: ghcr.io/myorg/app:${{ github.sha }}
```

### With Emergency Bypass

```yaml
jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    secrets:
      FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    with:
      container_image: ghcr.io/myorg/app:${{ github.sha }}
      skip_policy_gate: true
      skip_vulnerability_gate: false
      bypass_justification: "Emergency hotfix for production incident #12345"
```

### With Vault Secrets

```yaml
jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    secrets:
      VAULT_URL: ${{ secrets.VAULT_URL }}
      VAULT_ROLE: ${{ secrets.VAULT_ROLE }}
    with:
      container_image: ghcr.io/myorg/app:${{ github.sha }}
      use_vault: true
```

### Custom Config File Location

```yaml
jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    secrets:
      FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
    with:
      container_image: ghcr.io/myorg/app:${{ github.sha }}
      config_file: .github/custom-scan-config.json
```

## Troubleshooting

### Config file not found

**Error**: `Config file not found at path: .github/workflow-config.json`

**Solution**: Create the config file in your repository root, or specify a custom path:

```yaml
with:
  config_file: .github/custom-config.json
```

### Invalid JSON syntax

**Error**: `Invalid JSON syntax in config file`

**Solution**: Validate your JSON using `jq` or an online JSON validator:

```bash
jq '.' .github/workflow-config.json
```

Common JSON errors:
- Missing commas between fields
- Trailing commas (not allowed in JSON)
- Unquoted keys or values
- Mismatched brackets

### Workflow still blocking after setting REPORT mode

**Issue**: Workflow blocks even though config has `"mode": "REPORT"`

**Possible Causes**:
1. Config file not loaded correctly - check workflow logs
2. Emergency bypass flags set to `true` in workflow call
3. Separate gate (policy vs vulnerability) is in BLOCK mode

**Solution**: Check the "Load Configuration" step in workflow logs to verify config is loaded correctly.

### Scan timeout

**Error**: `Scan exceeded timeout of 3600 seconds`

**Solution**: Increase timeout in config:

```json
{
  "fossa": {
    "scan_params": {
      "timeout": 7200
    }
  }
}
```

### Custom Vault path not working

**Issue**: Secrets not found when using custom `vault.secret_path`

**Solution**: Verify the Vault path exists and your Vault role has read permissions:

```bash
vault kv get secret/data/teams/myteam/githubactions
```

### Container registry authentication failures

**Issue**: Scanner cannot pull container image

**Solution**: Ensure you authenticate to the registry before calling the workflow:

```yaml
- name: Login to GHCR
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}

- name: Container Scan
  uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
  # ... workflow call
```

For AWS ECR, the container-scan-and-guard workflow handles authentication automatically based on the `use_vault` input.

## Related Documentation

- [Container Scan Architecture](./container-scan-config-architecture.md)
- [Container Scan Action README](../container/container-scan/README.md)
- [FOSSA Scan Action README](../container/fossa-scan/README.md)

## Questions or Issues?

If you encounter problems or have questions about the configuration schema:

1. Review the [Architecture Document](./container-scan-config-architecture.md) for design decisions
2. Check the troubleshooting section above
3. Open an issue in the solace-public-workflows repository

# Workflow Configuration Schema

Configuration reference for `.github/workflow-config.json` used by container scanning workflows.

## File Location

**Path**: `.github/workflow-config.json` (in your repository root)

This file may already exist in your repository for other build configuration. The `container_scanning` field is **optional** and can be added alongside existing configuration.

## Schema Structure

### Root Level

```jsonc
{
  "squad": "string",
  "service_name": "string",
  "slack_channel": "string",
  "secrets": {
    "vault": {
      // Vault configuration (optional, for private repos)
      "url": "https://vault.example.com:8200",
      "role": "github-actions-role",
      "secret_path": "/path/to/secret",
      "aws_role": "/path/to/aws/role"
    }
  },
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
    "fossa": {
      "policy": {
        "mode": "REPORT | BLOCK",
        "block_on": ["policy_conflict", "policy_flag"]
      },
      "vulnerability": {
        "mode": "REPORT | BLOCK",
        "block_on": ["critical", "high", "medium", "low"]
      },
      "project_id": "string or null",
      "team": "string",
      "labels": ["string"]
    }
  }
}
```

## Field Reference

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `squad` | string | No | Team or squad name |
| `service_name` | string | No | Service identifier |
| `slack_channel` | string | No | Slack channel for notifications (e.g., `#team-alerts`) |
| `secrets` | object | No | Secret management configuration (Vault) - Required for private repos |
| `container_scanning` | object | No | Container scanning configuration |

### Container Scanning Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | boolean | No | `true` | Enable/disable container scanning |
| `fossa` | object | No | See defaults | FOSSA scanner configuration |
| `secrets` | object | No | See defaults | Secret management configuration (Vault paths) |

### FOSSA Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `fossa.policy.mode` | string | No | `REPORT` | Policy enforcement: `REPORT` (log only) or `BLOCK` (fail build) |
| `fossa.policy.block_on` | array | No | `["policy_conflict"]` | Policy issues to block on |
| `fossa.vulnerability.mode` | string | No | `REPORT` | Vulnerability enforcement: `REPORT` or `BLOCK` |
| `fossa.vulnerability.block_on` | array | No | `["critical", "high"]` | Vulnerability severities to block on |
| `fossa.project_id` | string | No | `null` | Override FOSSA project ID (auto-detected if null) |
| `fossa.team` | string | No | `""` | FOSSA team name for project assignment |
| `fossa.labels` | array | No | `[]` | FOSSA project labels (e.g., `["production", "container"]`) |

**Policy Block On Options**:
- `policy_conflict` - License policy violations
- `policy_flag` - Flagged licenses
- `deny` - Denied licenses

**Vulnerability Severities**:
- `critical` - Critical vulnerabilities (CVSSv3 9.0-10.0)
- `high` - High severity vulnerabilities (CVSSv3 7.0-8.9)
- `medium` - Medium severity vulnerabilities (CVSSv3 4.0-6.9)
- `low` - Low severity vulnerabilities (CVSSv3 0.1-3.9)

### Secrets Configuration (Vault)

**Note**: The `secrets` section is defined at the **root level** of the configuration file, not under `container_scanning`. It is shared across all workflows that use this configuration.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `secrets.vault.url` | string | Yes | - | Vault server URL (e.g., `https://vault.example.com:8200`) |
| `secrets.vault.role` | string | Yes | - | Vault JWT authentication role for GitHub Actions (e.g., `github-actions-role`) |
| `secrets.vault.secret_path` | string | No | `/path/to/secret` | Vault path for FOSSA_API_KEY |
| `secrets.vault.aws_role` | string | No | `""` | Vault AWS STS role path for ECR authentication |

## Complete Examples

### Example 1: Minimal Configuration (Report Only)

```json
{
  "squad": "platform-team",
  "service_name": "my-service",
  "slack_channel": "#platform-alerts",
  "container_scanning": {
    "enabled": true
  }
}
```

**Result**: Uses all defaults - REPORT mode for both policy and vulnerabilities.

### Example 2: Block on Security Issues

```json
{
  "squad": "security-team",
  "service_name": "critical-service",
  "slack_channel": "#security-alerts",
  "container_scanning": {
    "enabled": true,
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

**Result**: Fails workflow on ANY policy issue or critical/high vulnerabilities.

### Example 3: Team Assignment and Labels

```json
{
  "squad": "backend-team",
  "service_name": "api-gateway",
  "slack_channel": "#backend-alerts",
  "container_scanning": {
    "enabled": true,
    "fossa": {
      "policy": {
        "mode": "REPORT"
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical"]
      },
      "team": "Backend Engineering",
      "labels": ["production", "container", "api"]
    }
  }
}
```

**Result**: Assigns FOSSA project to "Backend Engineering" team with labels, blocks only on critical vulnerabilities.

### Example 4: Custom Vault Configuration (Private Repos)

```json
{
  "squad": "platform-team",
  "service_name": "auth-service",
  "slack_channel": "#platform-alerts",
  "secrets": {
    "vault": {
      "url": "https://vault.example.com:8200",
      "role": "github-actions-role",
      "secret_path": "secret/data/team/secrets",
      "aws_role": "aws-development/sts/team-role"
    }
  },
  "container_scanning": {
    "enabled": true,
    "fossa": {
      "team": "Platform Team",
      "labels": ["production"]
    }
  }
}
```

**Result**: Uses custom Vault configuration for team-specific secrets. The `secrets` section is defined at the **root level** and is shared across all workflows.

### Example 5: Custom Project ID

```json
{
  "container_scanning": {
    "enabled": true,
    "fossa": {
      "project_id": "MyOrg_shared-infrastructure",
      "team": "Infrastructure Team"
    }
  }
}
```

**Result**: Multiple services can share a single FOSSA project.

## Common Scenarios

### Scenario 1: New Service (Permissive)

**Use Case**: New service in development, want visibility but no blocking

```json
{
  "container_scanning": {
    "enabled": true,
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
    "fossa": {
      "policy": {
        "mode": "BLOCK",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical", "high"]
      },
      "team": "Your Team Name",
      "labels": ["production"]
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
    "vulnerability": {
      "mode": "BLOCK",
      "block_on": ["critical"]
    }
  }
}
```

**Phase 3: Full Enforcement**
```json
{
  "fossa": {
    "policy": {
      "mode": "BLOCK",
      "block_on": ["policy_conflict"]
    },
    "vulnerability": {
      "mode": "BLOCK",
      "block_on": ["critical", "high"]
    }
  }
}
```

### Scenario 4: Disable Scanning Temporarily

**Use Case**: Emergency deployment, temporarily bypass scanning

```json
{
  "container_scanning": {
    "enabled": false
  }
}
```

## Validation

### Check JSON Syntax

```bash
jq '.' .github/workflow-config.json
```

### Common JSON Errors

- Missing commas between fields
- Trailing commas (not allowed in JSON)
- Unquoted keys or values
- Mismatched brackets `{ }` or `[ ]`

### Verify Configuration is Loaded

Check the "Load Workflow Configuration" step in your workflow logs to see parsed values.

## Related Documentation

- [Workflow Config Loader README](./README.md) - Action documentation and usage
- [Container Scan Action](../container/container-scan/README.md) - Container scanning framework
- [FOSSA Scan Action](../container/fossa-scan/README.md) - FOSSA integration details
- [Container Scan Architecture](https://github.com/SolaceDev/cicd-processes-docs/blob/main/processes/security-scanning/design/container-scan-config-architecture.md) - Design document

## Questions or Issues?

1. Review the troubleshooting section in the [Workflow Config Loader README](./README.md)
2. Check workflow logs for configuration parsing output
3. Open an issue in the solace-public-workflows repository

# Container Scan and Guard - Config File Architecture

## Problem Statement

The `container-scan-and-guard.yaml` workflow has **15+ inputs** which is approaching GitHub's workflow input limits. Many inputs are tool-specific configuration flags (FOSSA/Prisma modes, block_on policies) that rarely change per-invocation and should be stored in a configuration file.

**This is a NEW workflow** - no migration concerns, clean slate design.

## Solution Overview

**Reduce inputs from 15 → 6 (60% reduction)** by:
1. ✅ Removing `git_ref` (not needed - image already has tag)
2. ✅ Splitting `skip_fossa_gate` → `skip_policy_gate` + `skip_vulnerability_gate` (granular control)
3. ✅ Moving gate policies to JSON config file (extends existing `.github/workflow-config.json`)
4. ✅ Leveraging existing `maas-build-actions/load-workflow-config.yaml` loader (backward compatible)

## Design Principles

1. **Runtime values stay as inputs**: `container_image`, `skip_policy_gate`, `skip_vulnerability_gate`, `bypass_justification`
2. **Secrets stay as secrets**: `FOSSA_API_KEY`, `VAULT_URL`, `VAULT_ROLE`, `PRISMA_USER`, `PRISMA_PASS`
3. **Policy configuration moves to config**: gate modes, block_on lists, scanner params, vault paths
4. **Reuse existing JSON config pattern**: Extend `.github/workflow-config.json` (already used for builds)
5. **Backward compatible**: Existing workflows ignore new `container_scanning` field

## Configuration File Structure

### Extend Existing workflow-config.json

**File**: `.github/workflow-config.json` (in consuming repository)

This file already exists in many repos for build configuration. We add an optional `container_scanning` section:

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",

  // === EXISTING FIELDS (preserved for backward compatibility) ===
  "squad": "mission-control",
  "service_name": "maas-core",
  "slack_channel": "#sc-deploy-cicd-activity",
  // ... other existing build config fields ...

  // === NEW CONTAINER SCANNING SECTION (optional) ===
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
      "project_id": null,
      "scan_params": {
        "debug": false,
        "skip_test": false,
        "timeout": 3600
      }
    },

    "prisma": {
      "policy": {
        "mode": "REPORT",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "REPORT",
        "block_on": ["critical", "high"]
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

**Key Points:**
- ✅ **Backward compatible**: Repos without `container_scanning` field work fine
- ✅ **Reuses existing loader**: `SolaceDev/maas-build-actions/.github/workflows/load-workflow-config.yaml`
- ✅ **No new infrastructure**: Uses existing config file pattern
- ✅ **Safe to add**: Doesn't break existing workflows

## Reduced Workflow Inputs

### Final Input Count: 6 (down from 15)

```yaml
on:
  workflow_call:
    inputs:
      # 1. Runtime target (REQUIRED - what to scan)
      container_image:
        description: 'Container image to scan (registry/repository:tag)'
        required: true
        type: string

      # 2-3. Emergency controls (RUNTIME - granular bypass)
      skip_policy_gate:
        description: 'EMERGENCY: Skip policy/licensing gate (requires admin)'
        required: false
        type: boolean
        default: false

      skip_vulnerability_gate:
        description: 'EMERGENCY: Skip vulnerability gate (requires admin)'
        required: false
        type: boolean
        default: false

      # 4. Bypass justification (REQUIRED when skipping)
      bypass_justification:
        description: 'Required justification for bypassing any gate'
        required: false
        type: string

      # 5. Secret management mode
      use_vault:
        description: 'Use Vault for secrets (vs GitHub Secrets)'
        required: false
        type: boolean
        default: false

      # 6. Config file path
      config_file:
        description: 'Path to workflow config JSON'
        required: false
        type: string
        default: '.github/workflow-config.json'

    secrets:
      FOSSA_API_KEY:
        description: 'FOSSA API key (if use_vault=false)'
        required: false
      PRISMA_USER:
        description: 'Prisma Cloud Access Key'
        required: false
      PRISMA_PASS:
        description: 'Prisma Cloud Secret Key'
        required: false
      VAULT_URL:
        description: 'Vault endpoint (if use_vault=true)'
        required: false
      VAULT_ROLE:
        description: 'Vault JWT role (if use_vault=true)'
        required: false
```

### What Moved to Config File

| Old Input | New Config Location | Notes |
|-----------|---------------------|-------|
| `git_ref` | **REMOVED** | Not needed - image tag already specified |
| `skip_fossa_gate` | **SPLIT** → `skip_policy_gate` + `skip_vulnerability_gate` | Granular control |
| `fossa_licensing_mode` | `container_scanning.fossa.policy.mode` | BLOCK or REPORT |
| `fossa_licensing_block_on` | `container_scanning.fossa.policy.block_on` | Array of issues |
| `fossa_vulnerability_mode` | `container_scanning.fossa.vulnerability.mode` | BLOCK or REPORT |
| `fossa_vulnerability_block_on` | `container_scanning.fossa.vulnerability.block_on` | Array of severities |
| `fossa_project_override` | `container_scanning.fossa.project_id` | Optional custom ID |
| `vault_secret_path` | `container_scanning.secrets.vault.secret_path` | Vault path |
| `additional_scan_params` | `container_scanning.fossa.scan_params` | Scanner-specific flags |
| `slack_channel` | `slack_channel` (root level) | Already exists in config |

## Image Pulling Requirements

**Important Note for Implementation:**

### FOSSA Container Scan
- **No explicit docker pull needed** - FOSSA CLI automatically pulls images
- `fossa container analyze <image>` handles pulling internally
- Requires Docker daemon credentials for registry authentication via `docker/login-action`

### Prisma Cloud Scan
- **YES - Requires explicit docker pull**
- The `prisma-cloud-scan` action includes a dedicated docker pull step internally (lines 85-123 of `prisma-cloud-scan/action.yml`)
- Must authenticate to registry BEFORE calling the scan action
- Twistcli scans the locally-available image after pulling

### Workflow Implication
- Registry authentication must happen **FIRST** before scanning
- Each scanner handles image access internally
- **No additional docker pull steps needed in container-scan-and-guard workflow itself**

### AWS ECR Authentication Strategy
Since most container images are in **AWS ECR**, the workflow must handle ECR authentication:

**Public Repos:**
- Use static AWS keys from GitHub Secrets
- `aws-actions/configure-aws-credentials@v4` with `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
- Then `aws-actions/amazon-ecr-login@v2`

**Private Repos:**
- Use Vault to generate temporary AWS STS credentials
- Vault action: `vault write aws-development/sts/sc-cicd-development-role`
- Then `aws-actions/amazon-ecr-login@v2`

**Implementation Note:** The container-scan-and-guard workflow should include ECR authentication steps before calling the scanner orchestrator.

## Implementation Plan

### Phase 1: Document Config Schema

**New documentation files:**
1. `docs/workflow-config-schema.md` - Complete JSON schema documentation
2. Update existing docs to include `container_scanning` field examples

**No code changes needed** - existing `load-workflow-config.yaml` already handles arbitrary JSON fields!

### Phase 2: Create container-scan-and-guard.yaml Workflow

**New file:** `.github/workflows/container-scan-and-guard.yaml`

**High-level structure:**

```yaml
name: Container Scan and Guard

on:
  workflow_call:
    inputs: # (6 inputs as defined above)
    secrets: # (5 secrets as defined above)

jobs:
  container_scan:
    runs-on: ubuntu-latest
    steps:
      # 1. Load config from repo
      - uses: actions/checkout@v4

      - name: Load Config
        id: config
        uses: SolaceDev/maas-build-actions/.github/workflows/load-workflow-config.yaml@master
        with:
          config_file: ${{ inputs.config_file }}

      # 2. Admin check for bypass (unchanged from sca-scan-and-guard)
      - name: Check Admin Permissions
        if: inputs.skip_policy_gate || inputs.skip_vulnerability_gate
        uses: actions/github-script@v7
        # ... admin permission check ...

      # 3. Retrieve secrets (Vault or GitHub Secrets)
      - name: Get Secrets from Vault
        if: inputs.use_vault
        uses: hashicorp/vault-action@v3
        with:
          url: ${{ secrets.VAULT_URL }}
          role: ${{ secrets.VAULT_ROLE }}
          secrets: |
            ${{ fromJSON(needs.config.outputs.config_json).container_scanning.secrets.vault.secret_path }} FOSSA_FULL_API_TOKEN | FOSSA_API_KEY
            # ... Prisma secrets ...

      - name: Set Secrets
        id: secrets
        run: |
          if [[ "${{ inputs.use_vault }}" == "true" ]]; then
            echo "FOSSA_KEY=${{ steps.vault.outputs.FOSSA_API_KEY }}" >> $GITHUB_OUTPUT
          else
            echo "FOSSA_KEY=${{ secrets.FOSSA_API_KEY }}" >> $GITHUB_OUTPUT
          fi
          # ... set PRISMA_USER, PRISMA_PASS ...

      # 4. Run container scan
      - name: Container Scan
        uses: SolaceDev/solace-public-workflows/container/container-scan@main
        with:
          scanners: ${{ join(fromJSON(needs.config.outputs.config_json).container_scanning.scanners, ',') }}
          additional_scan_params: |
            fossa.image=${{ inputs.container_image }}
            ${{ fromJSON(needs.config.outputs.config_json).container_scanning.fossa.scan_params | to_json }}
          fossa_api_key: ${{ steps.secrets.outputs.FOSSA_KEY }}
          prisma_console_url: ${{ fromJSON(needs.config.outputs.config_json).container_scanning.prisma.console_url }}
          prisma_user: ${{ steps.secrets.outputs.PRISMA_USER }}
          prisma_pass: ${{ steps.secrets.outputs.PRISMA_PASS }}

      # 5. FOSSA Policy Guard
      - name: FOSSA Policy Check
        if: ${{ !inputs.skip_policy_gate }}
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        with:
          fossa_api_key: ${{ steps.secrets.outputs.FOSSA_KEY }}
          fossa_project_id: ${{ github.repository_owner }}_${{ github.event.repository.name }}
          fossa_category: licensing
          fossa_mode: ${{ fromJSON(needs.config.outputs.config_json).container_scanning.fossa.policy.mode }}
          block_on: ${{ join(fromJSON(needs.config.outputs.config_json).container_scanning.fossa.policy.block_on, ',') }}
          enable_pr_comment: ${{ github.event_name == 'pull_request' }}
          enable_status_check: ${{ github.event_name == 'pull_request' }}

      # 6. FOSSA Vulnerability Guard
      - name: FOSSA Vulnerability Check
        if: ${{ !inputs.skip_vulnerability_gate }}
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        with:
          fossa_api_key: ${{ steps.secrets.outputs.FOSSA_KEY }}
          fossa_project_id: ${{ github.repository_owner }}_${{ github.event.repository.name }}
          fossa_category: vulnerability
          fossa_mode: ${{ fromJSON(needs.config.outputs.config_json).container_scanning.fossa.vulnerability.mode }}
          block_on: ${{ join(fromJSON(needs.config.outputs.config_json).container_scanning.fossa.vulnerability.block_on, ',') }}
          enable_pr_comment: ${{ github.event_name == 'pull_request' }}
          enable_status_check: ${{ github.event_name == 'pull_request' }}

      # 7. Report results
      - name: Report Results
        if: always()
        run: |
          # ... generate GitHub step summary ...

      # 8. Block on failures (if not bypassed)
      - name: Block on Policy Failures
        if: |
          always() && !inputs.skip_policy_gate &&
          steps.fossa_policy.outcome == 'failure'
        run: exit 1

      - name: Block on Vulnerability Failures
        if: |
          always() && !inputs.skip_vulnerability_gate &&
          steps.fossa_vulnerability.outcome == 'failure'
        run: exit 1

      # 9. Slack notification
      - name: Notify on Failure
        if: failure()
        uses: SolaceDev/maas-build-actions/.github/actions/build-finish-notifier@master
        with:
          workflow_title: "Container Scan"
          notify_channel: ${{ fromJSON(needs.config.outputs.config_json).slack_channel }}
```

**Key Implementation Notes:**
1. Use `fromJSON(needs.config.outputs.config_json).container_scanning.*` to access config values
2. Convert arrays to comma-separated strings with `join(..., ',')`
3. Separate policy and vulnerability gates with separate bypass flags
4. No `git_ref` needed - checkout is only for config file, not source code

## Usage Examples

### Minimal Usage (Defaults from Config)

**workflow-config.json:**
```json
{
  "slack_channel": "#my-team",
  "container_scanning": {
    "enabled": true,
    "scanners": ["fossa"],
    "fossa": {
      "policy": { "mode": "REPORT", "block_on": ["policy_conflict"] },
      "vulnerability": { "mode": "REPORT", "block_on": ["critical", "high"] }
    }
  }
}
```

**Workflow call:**
```yaml
container_scan:
  uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
  secrets:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
  with:
    container_image: ghcr.io/solacedev/my-app:${{ github.sha }}
```

### Blocking on Vulnerabilities

**workflow-config.json:**
```json
{
  "container_scanning": {
    "fossa": {
      "policy": { "mode": "BLOCK", "block_on": ["policy_conflict"] },
      "vulnerability": { "mode": "BLOCK", "block_on": ["critical", "high"] }
    }
  }
}
```

### Emergency Bypass

```yaml
container_scan:
  uses: ./.github/workflows/container-scan-and-guard.yaml
  secrets:
    FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
  with:
    container_image: ghcr.io/solacedev/my-app:v1.0.0
    skip_vulnerability_gate: true  # Skip only vulnerability gate
    bypass_justification: "FOSSA outage - INC12345"
```

### Using Vault (Private Repos)

```yaml
container_scan:
  uses: SolaceDev/maas-build-actions/.github/workflows/container-scan-and-guard.yaml@master
  secrets:
    VAULT_URL: ${{ secrets.VAULT_URL }}
    VAULT_ROLE: ${{ secrets.VAULT_ROLE }}
  with:
    container_image: 123456.dkr.ecr.us-east-1.amazonaws.com/app:v1.0.0
    use_vault: true
```

## Benefits

1. **60% fewer inputs** - From 15 to 6 inputs
2. **No new infrastructure** - Reuses existing `workflow-config.json` pattern
3. **Backward compatible** - Doesn't break existing build workflows
4. **Granular control** - Separate bypass flags for policy vs vulnerability
5. **Clean design** - No migration needed (brand new workflow)
6. **Consistent** - Follows established patterns in maas-build-actions

## Critical Files

### To Create:
- `.github/workflows/container-scan-and-guard.yaml` - New workflow
- `docs/workflow-config-schema.md` - Config schema documentation

### To Reference (Existing):
- `.github/workflow-config.json` - Config file (in consuming repos)
- `SolaceDev/maas-build-actions/.github/workflows/load-workflow-config.yaml` - Config loader
- `SolaceDev/solace-public-workflows/container/container-scan/` - Scanner orchestrator
- `SolaceDev/solace-public-workflows/.github/actions/fossa-guard/` - Policy enforcement

## Rollout Plan

### Phase 1: Foundation (Week 1)
**Goal:** Create the core infrastructure in solace-public-workflows

**Tasks:**
1. **Create config loader workflow**
   - File: `.github/workflows/load-workflow-config.yaml`
   - Reusable workflow for loading JSON config from consuming repos
   - Validates JSON syntax, exports as workflow output
   - Test with mock config file

2. **Create container-scan-and-guard workflow**
   - File: `.github/workflows/container-scan-and-guard.yaml`
   - 6 inputs (down from 15)
   - Integrates config loader
   - Includes ECR authentication logic
   - Separate policy and vulnerability gates
   - Test locally with act or similar tool

3. **Document config schema**
   - File: `docs/workflow-config-schema.md`
   - Complete JSON schema for `container_scanning` field
   - Examples for common scenarios
   - Migration guide from current approach

**Deliverables:**
- ✅ Working config loader
- ✅ Working container-scan-and-guard workflow
- ✅ Complete documentation

### Phase 2: Pilot Testing (Week 2)
**Goal:** Test with 1-2 pilot repositories

**Pilot Repository Selection Criteria:**
- Active development team
- Uses container scanning currently (or needs it)
- Team willing to provide feedback
- Mix of public + private repo if possible

**Tasks:**
1. **Select pilot repos**
   - Identify 1-2 candidate repos
   - Get team buy-in for testing

2. **Add config to pilot repos**
   - Create `.github/workflow-config.json` (or extend existing)
   - Add `container_scanning` section with team-specific settings
   - Example:
     ```json
     {
       "slack_channel": "#team-alerts",
       "container_scanning": {
         "enabled": true,
         "scanners": ["fossa"],
         "fossa": {
           "policy": { "mode": "REPORT", "block_on": ["policy_conflict"] },
           "vulnerability": { "mode": "REPORT", "block_on": ["critical", "high"] }
         }
       }
     }
     ```

3. **Integrate workflow into pilot repos**
   - Add workflow call to their CI/CD pipeline
   - Test PR scanning (diff mode)
   - Test release scanning (full scan)
   - Test emergency bypass functionality

4. **Collect feedback**
   - Gather team feedback on usability
   - Identify pain points or missing features
   - Monitor for errors or edge cases

**Success Criteria:**
- ✅ Pilot repos successfully scan containers
- ✅ Config file approach is intuitive
- ✅ No blocking issues discovered
- ✅ Team feedback is positive

### Phase 3: Limited Rollout (Week 3-4)
**Goal:** Expand to 5-10 additional repositories

**Tasks:**
1. **Address pilot feedback**
   - Fix any issues discovered in pilot
   - Update documentation based on feedback
   - Add any missing features identified

2. **Create rollout documentation**
   - Step-by-step onboarding guide
   - Troubleshooting FAQ
   - Config file templates for common scenarios

3. **Onboard additional repos**
   - Work with teams to add config files
   - Support integration into existing pipelines
   - Monitor for issues

4. **Monitor and iterate**
   - Watch for common configuration mistakes
   - Track workflow execution success rates
   - Gather metrics on input reduction benefits

**Success Criteria:**
- ✅ 5-10 repos successfully onboarded
- ✅ Common issues documented in FAQ
- ✅ Teams report improved workflow clarity

### Phase 4: General Availability (Week 5+)
**Goal:** Make available to all teams

**Tasks:**
1. **Announce availability**
   - Slack announcement with documentation links
   - Optional training session for interested teams
   - Add to internal developer portal

2. **Self-service onboarding**
   - Teams can adopt at their own pace
   - Documentation supports self-service
   - Support channel for questions

3. **Deprecation plan (optional)**
   - If replacing existing workflow, create deprecation timeline
   - Migrate remaining teams gradually
   - Eventually remove old workflow

**Success Criteria:**
- ✅ All teams aware of new workflow
- ✅ Clear path for adoption
- ✅ Support channels established

### Phase 5: Extension to SCA (Week 6+)
**Goal:** Apply same pattern to sca-scan-and-guard

**Tasks:**
1. **Review container scanning success**
   - Gather lessons learned
   - Identify improvements for SCA implementation

2. **Create SCA config schema**
   - Add `sca_scanning` section to workflow-config.json
   - Similar structure to `container_scanning`

3. **Update sca-scan-and-guard workflow**
   - Reduce inputs using same approach
   - Reuse config loader
   - Apply lessons from container scanning

4. **Rollout using proven process**
   - Follow phases 2-4 for SCA workflow

## Rollback Plan

If critical issues are discovered during rollout:

1. **Immediate Actions:**
   - Document the issue clearly
   - Notify affected teams via Slack
   - Pause onboarding of new repos

2. **Hotfix Process:**
   - Fix issue in solace-public-workflows
   - Tag new version
   - Test with pilot repos
   - Resume rollout once verified

3. **Full Rollback (if needed):**
   - Teams can revert to direct input approach by removing config file
   - Workflow still accepts all inputs as defaults
   - No breaking changes for consuming repos

## Success Metrics

Track these metrics to measure rollout success:

1. **Adoption Metrics:**
   - Number of repos using config-based approach
   - Time to onboard new repo (should decrease)

2. **Quality Metrics:**
   - Workflow execution success rate
   - Number of configuration errors
   - Time spent debugging config issues

3. **Developer Experience:**
   - Survey feedback on workflow clarity
   - Reduction in support requests about inputs
   - Team satisfaction scores

4. **Technical Metrics:**
   - Config file reuse across repos
   - Average workflow input count per invocation
   - Emergency bypass usage frequency

## Next Steps

1. ✅ Review and approve this architecture document
2. ✅ Review and approve rollout plan
3. Begin Phase 1: Create config loader and workflow
4. Identify pilot repositories for Phase 2
5. Execute rollout phases 1-5

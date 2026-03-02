# Multi-Language SCA Workflow Design - JSON-Driven Setup & Config-As-Code Secrets

## Problem Statement

Current SCA scanning workflows have several limitations:

1. **Hardcoded Vault secret paths** - Workflows previously used fixed internal paths, preventing teams with different Vault structures from using the workflow.
2. **Non-optional Maven setup** - Maven-specific steps always run, even for non-Maven projects.
3. **No multi-language support** - Cannot handle npm, Python, .NET, or mixed-language projects.
4. **No custom setup injection** - Cannot inject arbitrary setup commands for edge cases.

### Requirements

1. Configurable Vault secret paths (per project via config file).
2. Optional, conditional setup steps (not always Maven).
3. Support for multiple languages and build tools (Java, Node, Python, .NET).
4. Ability to inject custom setup commands.
5. Backward compatible with existing Maven workflows.

## Design Decision 1: JSON-Driven Composite Action (`setup-sca-deps`)

### Approach Overview

**Core Concept**: Users define the "ingredients" for their build environment using a JSON array. A single composite action interprets this array and runs the necessary steps.

**Example Input:**
```yaml
setup_actions: '["setup-java", "maven-settings", "npm-config", "npm-install"]'
```

### Supported Actions
- `setup-java`, `maven-settings`, `maven-build`
- `setup-node`, `npm-config`, `npm-install`
- `setup-python`, `python-install`
- `setup-dotnet`, `dotnet-restore`, `dotnet-nuget-config`
- `custom-script` (Escape hatch for arbitrary bash commands)

## Design Decision 2: Centralized Secret Configuration (`workflow-config.json`)

To avoid passing complex secret mappings as workflow inputs every time, we leverage the existing `workflow-config.json`.

### Schema Update
We add a `secret_mappings` array to the `secrets.vault` section. This defines which Vault secrets map to which environment variables.

```json
{
  "secrets": {
    "vault": {
      "url": "https://vault.example.com",
      "role": "example-role-name",
      "secret_mappings": [
        "secret/data/path/to/maven username | MAVEN_USERNAME",
        "secret/data/path/to/npm token | NPM_TOKEN"
      ]
    }
  }
}
```

## Architecture & Data Flow

```mermaid
graph TD
    Config[workflow-config.json] -->|Read by| Loader[workflow-config-loader]
    Loader -->|Outputs| ConfigOutput(vault_secret_mappings)
    
    ConfigOutput -->|Passed via| MainWorkflow[sca-scan-and-guard.yaml]
    
    MainWorkflow -->|Input: vault_secrets| SetupAction[action: setup-sca-deps]
    MainWorkflow -->|Input: setup_actions| SetupAction
    
    subgraph "Setup Composite Action"
        SetupAction -->|1. Fetch Secrets| VaultAction[hashicorp/vault-action]
        VaultAction -->|Sets Env Vars| BuildSteps
        
        SetupAction -->|2. Conditionals| BuildSteps
        BuildSteps -->|if: contains(..)| Java[Java Setup]
        BuildSteps -->|if: contains(..)| Node[Node Setup]
        BuildSteps -->|if: contains(..)| Python[Python Setup]
    end
```

### Implementation Status Checklist

#### Phase 1: Update `workflow-config-loader`
**Goal:** Enable parsing of `secret_mappings` from `workflow-config.json`.
- [x] **Modify `workflow-config-loader/action.yaml`**
    - Add `vault_secret_mappings` output.
    - Use `jq` to join `.secrets.vault.secret_mappings` array with newlines.
    - URL-encode the result for safe GitHub Action output.
- [x] **Update Verification:**
    - Test with sample config containing mappings.

#### Phase 2: Create `setup-sca-deps` Composite Action
**Goal:** Create the centralized setup engine.
- [x] **Create `.github/actions/setup-sca-deps/action.yml`**
    - **Inputs:** `setup_actions`, `vault_secrets` (multiline string), `vault_url`, `vault_role`, plus language versions/commands.
    - **Logic:**
        - **Vault**: Run `hashicorp/vault-action` if `inputs.vault_secrets` is present.
        - **Java**: `setup-java`, `maven-settings` (generates settings.xml), `maven-build`.
        - **Node**: `setup-node`, `npm-config` (generates .npmrc), `npm-install`.
        - **Python**: `setup-python`, `python-install`.
        - **Dotnet**: `setup-dotnet`, `dotnet-restore`, `dotnet-nuget-config`.
        - **Custom**: Run `custom_setup_script`.

#### Phase 3: Update `sca-scan-and-guard.yaml`
**Goal:** Integrate the new action.
- [x] **Modify Inputs:** Add `setup_actions`, `vault_secrets`, `custom_setup_script` and language configs.
- [x] **Modify Steps:**
    - Capture `vault_secret_mappings` from config loader call.
    - Replace hardcoded steps with `./sca-setup-deps`.
    - Wire inputs: `vault_secrets: ${{ inputs.vault_secrets != '' && inputs.vault_secrets || steps.config.outputs.vault_secret_mappings }}`.

#### Phase 4: Verification
- [ ] **Backward Compatibility**: Verify Maven default behavior works unchanged.
- [ ] **New Language**: Verify Node/Python application setup logic.
- [ ] **Vault Config**: Verify `secret_mappings` from file are correctly injected as env vars.

# FOSSA Scan Action

A GitHub Action that runs FOSSA security and license compliance scanning with configurable parameters.

## Overview

This action uses a JSON-based configuration system (`fossa-params.json`) to dynamically map environment variables to FOSSA CLI flags, making it easy to add new parameters without modifying the action logic.

**Performance Features:**
- Automatically checks if FOSSA CLI is already installed before downloading (saves time in cached environments)
- Configurable test step execution via `fossa.skip_test` parameter

## Configuration

### Parameter Mapping (`fossa-params.json`)

The action reads parameter definitions from `fossa-params.json`:

```json
{
  "parameters": [
    {
      "env": "SCA_FOSSA_CONFIG",
      "flag": "--config",
      "type": "value",
      "description": "Path to custom .fossa.yml configuration file",
      "example": "fossa.config=packages/my-package/.fossa.yml"
    }
  ]
}
```

**Field Definitions:**
- `env`: Environment variable name (automatically set by `sca-scan` action)
- `flag`: FOSSA CLI flag to use
- `type`: Either `"flag"` (boolean), `"value"` (requires a value), or `"multi_value"` (comma-separated list)
- `commands`: Array of FOSSA commands that support this parameter (`["analyze"]`, `["test"]`, or both)
- `description`: Human-readable description
- `example`: Example usage via `additional_scan_params`

### Parameter Types

#### Type: `flag` (Boolean)
Only added to CLI if environment variable equals `"true"`.

**Example:**
```yaml
additional_scan_params: |
  fossa.debug=true
  fossa.snippet_scan=true
```
Generates: `fossa analyze --debug --snippet-scan`

#### Type: `value` (String)
Added to CLI with the provided value if non-empty.

**Example:**
```yaml
additional_scan_params: |
  fossa.config=sam-mongodb/.fossa.yml
  fossa.path=sam-mongodb
  fossa.team=Platform Team
```
Generates: `fossa analyze --config sam-mongodb/.fossa.yml --team Platform Team`

#### Type: `multi_value` (Comma-separated list)
Added to CLI multiple times, once for each comma-separated value. Used for flags that can be specified multiple times.

**Example:**
```yaml
additional_scan_params: |
  fossa.project_label=critical,backend,production
  fossa.exclude_path=test/,examples/,docs/
```
Generates: `fossa analyze --project-label critical --project-label backend --project-label production --exclude-path test/ --exclude-path examples/ --exclude-path docs/`

## Usage

### Basic Usage

```yaml
- name: FOSSA Scan
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### With Custom Parameters

```yaml
- name: FOSSA Scan (Monorepo Plugin)
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.path=sam-mongodb
      fossa.config=sam-mongodb/.fossa.yml
      fossa.project=my-plugin
      fossa.branch=PR
      fossa.revision=${{ github.sha }}
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Skip Test Step (for container scans or custom workflows)

```yaml
- name: FOSSA Analyze Only
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.skip_test=true
      fossa.project=my-project
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

## Available Parameters

This action supports **48 parameters** including 47 FOSSA CLI flags and 1 action-specific parameter. Below is a summary of key parameters. For the complete list with examples, see [fossa-params.json](./fossa-params.json).

**Note:** The `fossa test` step runs automatically after `fossa analyze` unless you set `fossa.skip_test=true`.

### Action-Specific Parameters

These parameters control the GitHub Action behavior and are not FOSSA CLI flags.

| Parameter | Type | Description |
|-----------|------|-------------|
| `fossa.skip_test` | flag | Skip the `fossa test` step after analyze (useful for container scans or when extending other FOSSA commands) |
| `fossa.fail_on_issue` | flag | Allow `fossa test` to throw errors on policy violations |

### Common Parameters (analyze & test)

| Parameter | Type | FOSSA Flag | Description |
|-----------|------|------------|-------------|
| `fossa.debug` | flag | `--debug` | Enable debug logging |
| `fossa.project` | value | `--project` | Override project name/ID |
| `fossa.revision` | value | `--revision` | Git commit SHA |
| `fossa.config` | value | `--config` | Path to `.fossa.yml` |
| `fossa.endpoint` | value | `--endpoint` | Override FOSSA API server URL |
| `fossa.fossa_api_key` | value | `--fossa-api-key` | API key (alternative to env var) |

### Analyze Command Parameters

#### Project Details
| Parameter | Type | FOSSA Flag | Description |
|-----------|------|------------|-------------|
| `fossa.title` | value | `--title` | Set project title |
| `fossa.branch` | value | `--branch` | Override detected branch |
| `fossa.project_url` | value | `--project-url` | Add project URL |
| `fossa.jira_project_key` | value | `--jira-project-key` | Add Jira project key |
| `fossa.link` | value | `--link` | Attach link to build |
| `fossa.team` | value | `--team` | Specify team name |
| `fossa.policy` | value | `--policy` | Assign policy by name |
| `fossa.policy_id` | value | `--policy-id` | Assign policy by ID |
| `fossa.project_label` | multi_value | `--project-label` | Assign labels (up to 5) |
| `fossa.release_group_name` | value | `--release-group-name` | Add to release group |
| `fossa.release_group_release` | value | `--release-group-release` | Release version |

#### Path & Target Filtering
| Parameter | Type | FOSSA Flag | Description |
|-----------|------|------------|-------------|
| `fossa.only_target` | multi_value | `--only-target` | Only scan these targets |
| `fossa.exclude_target` | multi_value | `--exclude-target` | Exclude targets |
| `fossa.only_path` | multi_value | `--only-path` | Only scan these paths |
| `fossa.exclude_path` | multi_value | `--exclude-path` | Exclude paths |
| `fossa.include_unused_deps` | flag | `--include-unused-deps` | Include all deps |
| `fossa.without_default_filters` | flag | `--without-default-filters` | Disable default filters |

#### Output Options
| Parameter | Type | FOSSA Flag | Description |
|-----------|------|------------|-------------|
| `fossa.output` | flag | `--output` | Print to stdout instead of upload |
| `fossa.tee_output` | flag | `--tee-output` | Print to stdout AND upload |
| `fossa.json` | flag | `--json` | Print metadata as JSON |
| `fossa.fossa_deps_file` | value | `--fossa-deps-file` | Specify fossa-deps file |

#### Analysis Features
| Parameter | Type | FOSSA Flag | Description |
|-----------|------|------------|-------------|
| `fossa.unpack_archives` | flag | `--unpack-archives` | Unpack and scan archives |
| `fossa.detect_vendored` | flag | `--detect-vendored` | Enable vendored source detection |
| `fossa.static_only_analysis` | flag | `--static-only-analysis` | No third-party tools |
| `fossa.strict` | flag | `--strict` | Enforce strict analysis |
| `fossa.snippet_scan` | flag | `--snippet-scan` | Enable snippet scanning |
| `fossa.x_vendetta` | flag | `--x-vendetta` | Enable Vendetta scanning |

### Test Command Parameters

| Parameter | Type | FOSSA Flag | Description |
|-----------|------|------------|-------------|
| `fossa.timeout` | value | `--timeout` | Max seconds to wait (default: 3600) |
| `fossa.format` | value | `--format` | Output format (json) |
| `fossa.diff` | value | `--diff` | Only report new issues vs revision |

**Commands Column:**
- `analyze` - Used for the `fossa analyze` command (scans code and uploads results)
- `test` - Used for the `fossa test` command (checks scan results against policies)
- Both - Parameter is used by both commands

**Special Parameters:**
- `fossa.path` - Sets the working directory for FOSSA commands. This is not a CLI flag but uses GitHub Actions' `working-directory` to change into the specified directory before running `fossa analyze` and `fossa test`.
  - **Important:** If you specify `fossa.path`, FOSSA will automatically look for `.fossa.yml` in that directory. You only need `fossa.config` if your config file is in a different location or has a non-standard name.
  - **Example:** `fossa.path=sam-bedrock-agent` will automatically use `sam-bedrock-agent/.fossa.yml` if it exists.

See [fossa-params.json](./fossa-params.json) for the complete list with examples.

## Adding New Parameters

To add a new FOSSA CLI parameter, follow these steps:

### 1. Update the JSON Configuration

Add an entry to [`fossa-params.json`](./fossa-params.json):

```json
{
  "env": "SCA_FOSSA_NEW_PARAM",
  "flag": "--new-param",
  "type": "value",
  "commands": ["analyze", "test"],
  "description": "Description of what this parameter does",
  "example": "fossa.new_param=value"
}
```

**Field Guide:**
- `env`: Environment variable name (must start with `SCA_FOSSA_`)
- `flag`: FOSSA CLI flag (e.g., `--config`, `--path`)
- `type`: One of:
  - `"flag"` - Boolean parameter (only added when set to `true`)
  - `"value"` - String parameter (requires a value)
  - `"multi_value"` - Comma-separated list that generates multiple flags
- `commands`: Array of FOSSA commands that support this parameter
  - `["analyze"]` - Only used for `fossa analyze`
  - `["test"]` - Only used for `fossa test`
  - `["analyze", "test"]` - Used for both commands
- `description`: Human-readable description of the parameter
- `example`: Usage example via `additional_scan_params`

### 2. Run the Test Suite

Before committing, verify your changes work correctly:

```bash
cd .github/actions/sca/fossa-scan
./test-parse-fossa-params.sh
```

Expected output:
```
🧪 FOSSA Parameter Parser Test Suite
...
✅ All tests passed!
```

### 3. (Optional) Add a Test Case

For complex parameters, add a test case to [`test-parse-fossa-params.sh`](./test-parse-fossa-params.sh):

```bash
test_your_new_parameter() {
  echo ""
  echo "Test: Your new parameter"

  export SCA_FOSSA_NEW_PARAM="test-value"
  export FOSSA_PARAMS_CONFIG="$SCRIPT_DIR/fossa-params.json"

  source "$SCRIPT_DIR/parse-fossa-params.sh"
  build_fossa_args > /dev/null

  assert_contains "$FOSSA_CLI_ARGS" "--new-param test-value" \
    "Should include --new-param with value"

  unset SCA_FOSSA_NEW_PARAM FOSSA_CLI_ARGS
}
```

Then add `test_your_new_parameter` to the test execution section.

### 4. Update Documentation

Add your parameter to the "Available Parameters" table in this README.

### 5. Commit and Create PR

```bash
git add fossa-params.json README.md
git commit -m "feat: Add support for --new-param FOSSA flag"
```

**That's it!** No code changes to `action.yaml` or `parse-fossa-params.sh` are needed - the JSON configuration is declarative and self-contained.

## Architecture

### Flow Diagram

```
User Workflow (sca-scan)
  ↓
  additional_scan_params: "fossa.config=path/.fossa.yml"
  ↓
  Converted to: SCA_FOSSA_CONFIG=path/.fossa.yml
  ↓
fossa-scan Action
  ↓
  Reads: fossa-params.json
  ↓
  Maps: SCA_FOSSA_CONFIG → --config path/.fossa.yml
  ↓
  Executes: fossa analyze --config path/.fossa.yml
```

## Related Documentation

- [FOSSA CLI Documentation](https://github.com/fossas/fossa-cli)
- [FOSSA `analyze` Command Reference](https://github.com/fossas/fossa-cli/blob/master/docs/references/subcommands/analyze.md)
- [FOSSA `test` Command Reference](https://github.com/fossas/fossa-cli/blob/master/docs/references/subcommands/test.md)
- [Parent SCA Scan Action](../sca-scan/)
- [FOSSA Parameter Config](./fossa-params.json)

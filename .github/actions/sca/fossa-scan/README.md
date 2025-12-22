# FOSSA Scan Action

A GitHub Action that runs FOSSA security and license compliance scanning with configurable parameters.

## Overview

This action uses a JSON-based configuration system (`fossa-params.json`) to dynamically map environment variables to FOSSA CLI flags, making it easy to add new parameters without modifying the action logic.

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
- `type`: Either `"flag"` (boolean) or `"value"` (requires a value)
- `description`: Human-readable description
- `example`: Example usage via `additional_scan_params`

### Parameter Types

#### Type: `flag` (Boolean)
Only added to CLI if environment variable equals `"true"`.

**Example:**
```yaml
additional_scan_params: |
  fossa.analyze_debug=true
```
Generates: `fossa analyze --debug`

#### Type: `value` (String)
Added to CLI with the provided value if non-empty.

**Example:**
```yaml
additional_scan_params: |
  fossa.config=sam-mongodb/.fossa.yml
  fossa.path=sam-mongodb
```
Generates: `fossa analyze --config sam-mongodb/.fossa.yml --path sam-mongodb`

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

## Available Parameters

| Parameter | Type | FOSSA Flag | Description |
|-----------|------|------------|-------------|
| `fossa.analyze_debug` | flag | `--debug` | Enable debug logging |
| `fossa.branch` | value | `--branch` | Branch name for tracking |
| `fossa.revision` | value | `--revision` | Git commit SHA |
| `fossa.path` | value | `--path` | Base directory to scan |
| `fossa.config` | value | `--config` | Path to `.fossa.yml` |
| `fossa.unpack_archives` | flag | `--unpack-archives` | Unpack and scan archives |
| `fossa.without_default_filters` | flag | `--without-default-filters` | Disable default filters |
| `fossa.force_vendored_dependency_rescans` | flag | `--force-vendored-dependency-rescans` | Force rescan vendored deps |

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
  "description": "Description of what this parameter does",
  "example": "fossa.new_param=value"
}
```

**Field Guide:**
- `env`: Environment variable name (must start with `SCA_FOSSA_`)
- `flag`: FOSSA CLI flag (e.g., `--config`, `--path`)
- `type`: Either `"flag"` (boolean) or `"value"` (requires a value)
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
- [Parent SCA Scan Action](../sca-scan/)
- [FOSSA Parameter Config](./fossa-params.json)

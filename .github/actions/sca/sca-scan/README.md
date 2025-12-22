# SCA Scan Action

A generic Software Composition Analysis (SCA) scan entrypoint that orchestrates multiple security scanning tools.

## Overview

This action serves as a unified interface for running various SCA scanners (currently supporting FOSSA). It handles parameter conversion and routing to specific scanner implementations.

## Features

- **Multi-scanner support**: Run one or more SCA scanners (currently: FOSSA)
- **Unified parameter system**: Configure scanner-specific options through `additional_scan_params`
- **Automatic parameter conversion**: Converts `scanner.param_name` → `SCA_SCANNER_PARAM_NAME` environment variables
- **Extensible architecture**: Easy to add new scanners without changing caller workflows

## Usage

### Basic Usage

```yaml
- name: Run SCA Scan
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### With Custom Parameters

```yaml
- name: Run SCA Scan with Custom Config
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.path=packages/my-package
      fossa.config=packages/my-package/.fossa.yml
      fossa.branch=main
      fossa.revision=${{ github.sha }}
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Monorepo Use Case

```yaml
- name: Scan Specific Plugin
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.path=sam-mongodb
      fossa.config=sam-mongodb/.fossa.yml
      fossa.project=SolaceLabs_sam-mongodb
      fossa.branch=PR
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `scanners` | Comma-separated list of scanners to run | No | `"fossa"` |
| `additional_scan_params` | Scanner-specific parameters (see below) | No | `""` |
| `fossa_api_key` | API key for FOSSA scanner | No (required if using FOSSA) | `""` |

## Additional Scan Parameters

The `additional_scan_params` input accepts scanner-specific configuration in `scanner.param_name=value` format.

### Format

```yaml
additional_scan_params: |
  scanner.parameter_name=value
  scanner.another_param=another_value
```

### Parameter Conversion

Parameters are automatically converted to environment variables:

| Input Format | Environment Variable | Example |
|--------------|---------------------|---------|
| `fossa.config` | `SCA_FOSSA_CONFIG` | `fossa.config=.fossa.yml` → `SCA_FOSSA_CONFIG=.fossa.yml` |
| `fossa.branch` | `SCA_FOSSA_BRANCH` | `fossa.branch=main` → `SCA_FOSSA_BRANCH=main` |
| `fossa.analyze_debug` | `SCA_FOSSA_ANALYZE_DEBUG` | `fossa.analyze_debug=true` → `SCA_FOSSA_ANALYZE_DEBUG=true` |

**Conversion Rules:**
1. Prefix with `SCA_`
2. Replace `.` with `_`
3. Convert to UPPERCASE

### Comments and Empty Lines

```yaml
additional_scan_params: |
  # This is a comment - will be ignored
  fossa.branch=main

  # Empty lines are also ignored
  fossa.config=.fossa.yml
```

### Available Parameters by Scanner

#### FOSSA

See the [FOSSA Scan Action README](../fossa-scan/README.md) for a complete list of available parameters.

**Common FOSSA Parameters:**
- `fossa.path` - Base directory to scan
- `fossa.config` - Path to `.fossa.yml` configuration file
- `fossa.branch` - Branch name for tracking
- `fossa.revision` - Git commit SHA
- `fossa.project` - Custom project name
- `fossa.analyze_debug` - Enable debug logging (`true`/`false`)

## How It Works

### Architecture Flow

```
User Workflow
  ↓
  sca-scan Action
  ↓
  Parse additional_scan_params
  ↓
  Convert to Environment Variables
  (fossa.config → SCA_FOSSA_CONFIG)
  ↓
  Route to Scanner Action (fossa-scan)
  ↓
  Scanner reads SCA_* environment variables
  ↓
  Execute Scanner CLI
```

### Parameter Parsing

1. **Input**: Multi-line string with `key=value` pairs
2. **Parsing**: Split on `=`, trim whitespace
3. **Conversion**: Apply naming convention (`SCA_SCANNER_PARAM`)
4. **Export**: Set as environment variable in `$GITHUB_ENV`
5. **Propagation**: Available to all child actions

### Example Transformation

**Input:**
```yaml
additional_scan_params: |
  fossa.path=sam-mongodb
  fossa.config=sam-mongodb/.fossa.yml
```

**Exported Variables:**
```bash
SCA_FOSSA_PATH=sam-mongodb
SCA_FOSSA_CONFIG=sam-mongodb/.fossa.yml
```

**FOSSA Command:**
```bash
fossa analyze --path sam-mongodb --config sam-mongodb/.fossa.yml
```

## Error Handling

### Invalid Parameter Format

```yaml
additional_scan_params: |
  invalid_line_without_equals
```

**Result:**
```
❌ Invalid additional_scan_params line (missing '='): invalid_line_without_equals
```

The action will fail fast to prevent incorrect configuration.

## Extending with New Scanners

To add a new scanner:

1. **Create scanner action**: `.github/actions/sca/new-scanner/action.yaml`
2. **Add input**: Add `new_scanner_api_key` input to this action
3. **Add step**: Add routing step to call your scanner action
4. **Update docs**: Document scanner-specific parameters

**Example:**
```yaml
- name: SCA - Run NewScanner scan
  if: contains(inputs.scanners, 'newscanner')
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/new-scanner@main
  env:
    NEWSCANNER_API_KEY: ${{ inputs.newscanner_api_key }}
```

## Related Documentation

- [FOSSA Scan Action](../fossa-scan/README.md) - FOSSA scanner implementation
- [FOSSA Parameters](../fossa-scan/fossa-params.json) - Complete FOSSA parameter list
- [FOSSA CLI Docs](https://github.com/fossas/fossa-cli) - Official FOSSA documentation

## Troubleshooting



### Matrix Build (Multiple Packages)

```yaml
jobs:
  sca-scan:
    strategy:
      matrix:
        package: [sam-mongodb, sam-slack, sam-jira]
    steps:
      - name: Scan ${{ matrix.package }}
        uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
        with:
          scanners: "fossa"
          additional_scan_params: |
            fossa.path=${{ matrix.package }}
            fossa.config=${{ matrix.package }}/.fossa.yml
            fossa.project=MyOrg_${{ matrix.package }}
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### PR Scanning

```yaml
- name: Scan PR Changes
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.branch=PR
      fossa.revision=${{ github.event.pull_request.head.sha }}
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

### Main Branch Scanning

```yaml
- name: Scan Main Branch
  if: github.ref == 'refs/heads/main'
  uses: SolaceDev/solace-public-workflows/.github/actions/sca/sca-scan@main
  with:
    scanners: "fossa"
    additional_scan_params: |
      fossa.branch=${{ github.ref_name }}
      fossa.revision=${{ github.sha }}
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
```

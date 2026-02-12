# Generate FOSSA Report Action

This action generates and downloads FOSSA attribution reports.

## Usage

```yaml
- name: Generate FOSSA Report
  uses: ./.github/actions/generate-fossa-report
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    project_locator: "my-project"
    revision_id: "1.0.0"
    format: "txt"
    output_file: "licenses/fossa-report.txt"
```

## Inputs

| Input               | Description                                                                                                                                        | Required | Default                                                |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------ |
| `fossa_api_key`     | Your FOSSA API Key. It is recommended to store this as a secret.                                                                                   | `true`   | N/A                                                  |
| `org_id`            | The organization ID for FOSSA. This will be combined with `project_locator`.                                                                       | `false`  | (organization default)                               |
| `project_locator`   | The project locator for the FOSSA project. If not provided, will be read from `fossa_config_file`.                                                | `false`  | N/A (reads from config if omitted)                  |
| `fossa_config_file` | Path to FOSSA config file to read project locator from. Used only if `project_locator` is not provided.                                           | `false`  | `.fossa.yml`                                         |
| `revision_id`       | The revision for the FOSSA project (e.g., `latest`, or a specific commit hash).                                                                    | `true`   | N/A                                                  |
| `format`            | The format of the report to generate (`txt` or `csv`).                                                                                             | `true`   | `txt`                                                |
| `output_file`       | The output file path for the generated report.                                                                                                   | `true`   | `fossa-report.txt`                                   |
| `report_profile`    | Preset report profile: `full` (comprehensive), `standard` (common fields), or `minimal` (basic info). Easier than using `report_parameters`.    | `false`  | `full`                                               |
| `report_parameters` | A JSON object of FOSSA report parameters for advanced customization. Overrides `report_profile` if provided.                                     | `false`  | N/A                                                  |

## Report Profiles

### Minimal Profile
- Direct and deep dependencies
- License list only
- Fields: Library, License

### Standard Profile
- Direct and deep dependencies
- Notice files
- License and copyright lists
- Fields: Library, License, Copyrights, PackageDownloadUrl

### Full Profile (Default)
- All dependencies, notices, hashes, versions
- Complete license and copyright information
- All available fields including full license text

## Examples

### Basic Usage

```yaml
- name: Generate License Report
  uses: ./.github/actions/generate-fossa-report
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    project_locator: "my-java-client"
    revision_id: ${{ github.ref_name }}
    output_file: "licenses/LICENSE.txt"
```

### Using .fossa.yml Config File

If you have a `.fossa.yml` file in your repository, you can omit the `project_locator` input and the action will automatically read it from the config file:

```yaml
- name: Generate FOSSA Report from Config
  uses: ./.github/actions/generate-fossa-report
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    revision_id: ${{ github.ref_name }}
    # project_locator is read from .fossa.yml automatically
```

**Example .fossa.yml:**
```yaml
version: 3

project:
  name: "My Project"
  locator: my-project-name
  id: my-project-name
```

The action will look for `project.id` or `project.locator` in the FOSSA config file.

### Custom Config File Location

If your FOSSA config file is in a different location or has a different name:

```yaml
- name: Generate Report with Custom Config
  uses: ./.github/actions/generate-fossa-report
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    fossa_config_file: "config/fossa-config.yml"
    revision_id: ${{ github.ref_name }}
```

### Using Different Profiles

```yaml
# Minimal report (faster, smaller)
- name: Generate Minimal License Report
  uses: ./.github/actions/generate-fossa-report
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    project_locator: "my-project"
    revision_id: "1.0.0"
    report_profile: "minimal"

# CSV format for spreadsheet analysis
- name: Generate CSV Report
  uses: ./.github/actions/generate-fossa-report
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    project_locator: "my-project"
    revision_id: "1.0.0"
    format: "csv"
    output_file: "licenses/report.csv"
    report_profile: "standard"
```

### Advanced Customization with JSON

```yaml
- name: Generate Custom Report
  uses: ./.github/actions/generate-fossa-report
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    project_locator: "my-project"
    revision_id: "1.0.0"
    report_parameters: |
      {
        "includeDirectDependencies": true,
        "includeDeepDependencies": true,
        "includeLicenseList": true,
        "includeCopyrightList": true,
        "dependencyInfoOptions": [
          "Library",
          "License",
          "Copyrights"
        ]
      }
```

## API Reference

For more details on available report parameters, see the official FOSSA API documentation:
- [Download FOSSA project attribution reports](https://docs.fossa.com/docs/download-fossa-project-attribution-reports)

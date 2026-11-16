# Generate FOSSA Report Action

This action generates and downloads FOSSA attribution reports.

## Caller Permissions

This action runs the `maas-build-actions` container image from GHCR (`ghcr.io/<org>/maas-build-actions`). The calling workflow's `GITHUB_TOKEN` must have **at least `packages: read`** so that `docker login ghcr.io` can authenticate before pulling the image.

```yaml
permissions:
  packages: read        # required to pull maas-build-actions image from GHCR
```

> **Note:** Composite actions cannot declare `permissions:` themselves. The calling workflow or job is fully responsible for granting this permission.

---

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
| `format`            | Report format, case-insensitive: `HTML`, `MD`, `PDF`, `CSV`, `TXT`, `SPDX` (SPDX 2.3 tag-value), `SPDX_JSON` (SPDX 2.3 JSON), `SPDX3_JSON` (SPDX 3.0.1), `CYCLONEDX_JSON`, `CYCLONEDX_XML`. Others fail the step. | `true`   | `txt`                                                |
| `output_file`       | The output file path for the generated report.                                                                                                   | `true`   | `fossa-report.txt`                                   |
| `report_profile`    | Preset report profile: `full` (comprehensive), `standard` (common fields), `minimal` (basic info), or `sbom` (see below). Easier than using `report_parameters`.    | `false`  | `full`                                               |
| `supplier`          | Organization name used as SBOM document creator and supplier. Required for `report_profile: sbom`.                                                | `false`  | N/A                                                  |
| `author_name`       | SBOM author name. Defaults to `supplier` when using the `sbom` profile.                                                                           | `false`  | `supplier`                                           |
| `author_email`      | SBOM author email.                                                                                                                                 | `false`  | N/A                                                  |
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

### SBOM Profile
- Direct and deep dependencies
- Licence scan, declared and concluded licences, copyright list
- Fields: Library, License, FullTextLicense, Copyrights
- Requires `supplier`; sets `supplier`, `authorName` (and `authorEmail`) so the document creator is not empty

FOSSA's default parameters send empty `authorName`/`authorEmail`/`supplier` (creator becomes `Organization: `) and, under `standard`, leave `licenseConcluded` as `NOASSERTION`. Use `sbom` for SPDX formats (`SPDX3_JSON`, `SPDX_JSON`, `SPDX`).

`output_file` defaults to `fossa-report.txt` regardless of `format`, so set it explicitly (for example `sbom/product.spdx3.json`) when generating an SBOM.

If you pass `report_parameters` yourself, `supplier`/`author_*` are merged over it.

## Examples

### SBOM for a release group

```yaml
permissions:
  packages: read

steps:
  - uses: SolaceDev/solace-public-workflows/.github/actions/generate-fossa-report@<sha>
    with:
      fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
      release_group_id: "12345"
      release_id: "67890"
      format: SPDX3_JSON
      report_profile: sbom
      supplier: "Solace Corporation"
      output_file: "sbom/product.spdx3.json"
```

### SBOM for a single project

```yaml
- uses: SolaceDev/solace-public-workflows/.github/actions/generate-fossa-report@<sha>
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    project_locator: "my-project"
    revision_id: ${{ github.sha }}
    format: SPDX3_JSON
    report_profile: sbom
    supplier: "Solace Corporation"
    author_email: "sbom@example.com"
    output_file: "sbom/my-project.spdx3.json"
```

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

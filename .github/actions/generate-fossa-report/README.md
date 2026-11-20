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
| `org_id`            | The organization ID for FOSSA. This will be combined with `project_locator`.                                                                       | `false`  | `custom+48578`                                       |
| `project_locator`   | The project locator for the FOSSA project. If not provided, will be read from `fossa_config_file`. Ignored (with a warning) when `release_group_id` is provided. | `false`  | N/A (reads from config if omitted)                  |
| `fossa_config_file` | Path to FOSSA config file to read project locator from. Used only if `project_locator` is not provided.                                           | `false`  | `.fossa.yml`                                         |
| `revision_id`       | The revision for the FOSSA project (e.g., `latest`, or a specific commit hash). Not used when `release_group_id` is provided.                      | `false`  | N/A                                                  |
| `release_group_id`  | FOSSA release group ID. When provided, generates a release group attribution report instead of a per-project report. Requires `release_id`.       | `false`  | N/A                                                  |
| `release_id`        | FOSSA release ID within the release group. Required when `release_group_id` is provided.                                                          | `false`  | N/A                                                  |
| `format`            | Report format, case-insensitive: `HTML`, `MD`, `PDF`, `CSV`, `TXT`, `SPDX` (SPDX 2.3 tag-value), `SPDX_JSON` (SPDX 2.3 JSON), `SPDX3_JSON` (SPDX 3.0.1), `CYCLONEDX_JSON`, `CYCLONEDX_XML`. Others fail the step. The format sets the SBOM spec version. | `true`   | `txt`                                                |
| `output_file`       | The output file path for the generated report. A relative path is relative to the workspace. For an absolute path outside the workspace, see [Output location](#output-location). | `true`   | `fossa-report.txt`                                   |
| `report_profile`    | Preset report profile: `full` (comprehensive), `standard` (common fields), `minimal` (basic info), or `sbom` (see below). Easier than using `report_parameters`.    | `false`  | `standard`                                           |
| `supplier`          | Organization name used as SBOM document creator and supplier. Required for `report_profile: sbom`; with another profile only valid together with `report_parameters`.                                                | `false`  | N/A                                                  |
| `author_name`       | SBOM author name (FOSSA `authorName`). Defaults to `supplier` with `report_profile: sbom`. Needs `sbom` or `report_parameters`.                    | `false`  | `supplier` (under `sbom`)                            |
| `author_email`      | SBOM author email (FOSSA `authorEmail`). Needs `sbom` or `report_parameters`.                                                                     | `false`  | N/A                                                  |
| `report_parameters` | A JSON object of FOSSA report parameters for advanced customization. Overrides `report_profile` if provided (with `sbom`, merged over the SBOM defaults; a caller `dependencyInfoOptions` replaces the default list).                                     | `false`  | N/A                                                  |

## Output location

The report is generated inside a container that only sees the workspace, `RUNNER_TEMP` and the runner's output-file directory. For an absolute `output_file` elsewhere, the action has the container write to a staging directory under `RUNNER_TEMP`, then (on the runner, after the container succeeds) creates the destination directory, copies the file to a temporary name there and renames it into place. The step fails if the report is missing or empty at the destination, so a green step means the file is there. The destination directory must be writable by the runner user. The staging copy is removed when the step ends.

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

### Full Profile
- All dependencies, notices, hashes, versions
- Complete license and copyright information
- All available fields including full license text

The default `report_profile` is `standard`. Set `full` explicitly to get this profile.

### SBOM Profile
- Direct and deep dependencies
- Licence scan, declared and concluded licences, copyright list
- Fields: Library, License, FullTextLicense, Copyrights

Requires `supplier`, which names the organization as the document creator. Without it, FOSSA's SPDX creator is not the product organization, and under `standard` `licenseConcluded` is `NOASSERTION`. Use it for the SPDX formats. `author_name` defaults to `supplier`.

The `format` input chooses the SPDX version and where the creator is recorded:
- `SPDX_JSON`: SPDX 2.3 JSON, in `creationInfo.creators`.
- `SPDX3_JSON`: SPDX 3.0.1 JSON, in `creationInfo.createdBy`.
- `SPDX`: SPDX 2.3 tag-value, in the `Creator:` lines.

`output_file` defaults to `fossa-report.txt` whatever the `format`, so set it explicitly for an SBOM (for example `sbom/product.spdx3.json`).

Keys in `report_parameters` override the SBOM defaults, but a `supplier` key inside it does not replace the `supplier` input, which `sbom` always needs.

## Examples

### SBOM for a release group

Both `release_group_id` and `release_id` are required. `project_locator` is ignored in this mode.

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

Use `format: SPDX_JSON` for SPDX 2.3 instead of 3.0.1.

### SBOM for a single project

```yaml
permissions:
  packages: read

steps:
  - uses: SolaceDev/solace-public-workflows/.github/actions/generate-fossa-report@<sha>
    with:
      fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
      project_locator: "my-project"
      revision_id: ${{ github.sha }}
      format: SPDX3_JSON
      report_profile: sbom
      supplier: "Solace Corporation"
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

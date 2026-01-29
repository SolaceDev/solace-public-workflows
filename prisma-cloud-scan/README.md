# Prisma Cloud Container Scan Action

A composite GitHub Action that scans Docker container images using Prisma Cloud's `twistcli` for vulnerabilities and compliance issues.

## Features

- Downloads and uses `twistcli` directly from Prisma Cloud Console
- Pulls Docker images from any registry
- Scans images for vulnerabilities and compliance issues
- Blocks releases on critical or high severity findings
- Provides detailed scan results as outputs
- Helpful error messages for authentication issues
- Automatically publishes results to Prisma Cloud Console (configurable)

## Usage

### Basic Example

```yaml
name: Container Security Scan

on:
  push:
    branches: [main]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Scan Docker Image
        uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
        with:
          image_registry: "868978040651.dkr.ecr.us-east-1.amazonaws.com"
          image_tag: "v1.2.3-sha-abc123"
          pcc_console_url: "https://console.prisma.cloud"
          pcc_user: ${{ secrets.PRISMACLOUD_ACCESS_KEY_ID }}
          pcc_pass: ${{ secrets.PRISMACLOUD_SECRET_KEY }}
```

### With ECR Authentication

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Login to Amazon ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Scan Docker Image
        uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
        with:
          image_registry: "868978040651.dkr.ecr.us-east-1.amazonaws.com"
          image_tag: "v1.2.3"
          pcc_console_url: "https://console.prisma.cloud"
          pcc_user: ${{ secrets.PRISMACLOUD_ACCESS_KEY_ID }}
          pcc_pass: ${{ secrets.PRISMACLOUD_SECRET_KEY }}
```

### With Custom Repository Name

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Scan Docker Image
        uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
        with:
          image_registry: "docker.io"
          image_repo: "myorg/my-custom-image-name" # Override default repo name
          image_tag: "latest"
          pcc_console_url: "https://console.prisma.cloud"
          pcc_user: ${{ secrets.PRISMACLOUD_ACCESS_KEY_ID }}
          pcc_pass: ${{ secrets.PRISMACLOUD_SECRET_KEY }}
          twistcli_publish: "false" # Don't publish to Prisma Console
```

### Using Scan Results

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Scan Docker Image
        id: prisma_scan
        uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
        with:
          image_registry: "868978040651.dkr.ecr.us-east-1.amazonaws.com"
          image_tag: "v1.2.3"
          pcc_console_url: "https://console.prisma.cloud"
          pcc_user: ${{ secrets.PRISMACLOUD_ACCESS_KEY_ID }}
          pcc_pass: ${{ secrets.PRISMACLOUD_SECRET_KEY }}

      - name: Report Scan Results
        if: always()
        run: |
          echo "Scan Passed: ${{ steps.prisma_scan.outputs.scan_passed }}"
          echo "Critical Vulnerabilities: ${{ steps.prisma_scan.outputs.vuln_critical }}"
          echo "High Vulnerabilities: ${{ steps.prisma_scan.outputs.vuln_high }}"
          echo "Medium Vulnerabilities: ${{ steps.prisma_scan.outputs.vuln_medium }}"
          echo "Low Vulnerabilities: ${{ steps.prisma_scan.outputs.vuln_low }}"
```

## Inputs

| Name               | Required | Default          | Description                                                                    |
| ------------------ | -------- | ---------------- | ------------------------------------------------------------------------------ |
| `image_registry`   | Yes      | -                | Docker image registry (e.g., `868978040651.dkr.ecr.us-east-1.amazonaws.com`)   |
| `image_repo`       | No       | GitHub repo name | Docker image repository name. If not provided, uses the GitHub repository name |
| `image_tag`        | Yes      | -                | Docker image tag to scan                                                       |
| `pcc_console_url`  | Yes      | -                | Prisma Cloud Console URL (e.g., `https://console.prisma.cloud`)                |
| `pcc_user`         | Yes      | -                | Prisma Cloud Access Key ID                                                     |
| `pcc_pass`         | Yes      | -                | Prisma Cloud Secret Access Key                                                 |
| `twistcli_publish` | No       | `true`           | Whether to publish scan results to Prisma Cloud Console (`true` or `false`)    |

## Outputs

| Name            | Description                                                                           |
| --------------- | ------------------------------------------------------------------------------------- |
| `scan_passed`   | Boolean string indicating if scan passed (no critical/high issues): `true` or `false` |
| `vuln_critical` | Number of critical vulnerabilities found                                              |
| `vuln_high`     | Number of high severity vulnerabilities found                                         |
| `vuln_medium`   | Number of medium severity vulnerabilities found                                       |
| `vuln_low`      | Number of low severity vulnerabilities found                                          |

## Blocking Behavior

The action will **fail and block the pipeline** if:

- Critical severity vulnerabilities are found
- High severity vulnerabilities are found
- Critical compliance issues are found
- High severity compliance issues are found

Medium and low severity findings are reported but do not block the pipeline.

## Registry Authentication

If your image is in a private registry, you must authenticate **before** calling this action. The action will provide helpful error messages if image pull fails.

### AWS ECR

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: us-east-1

- name: Login to Amazon ECR
  uses: aws-actions/amazon-ecr-login@v2
```

### Docker Hub

```yaml
- name: Login to Docker Hub
  uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKERHUB_USERNAME }}
    password: ${{ secrets.DOCKERHUB_TOKEN }}
```

### Google Container Registry (GCR)

```yaml
- name: Login to GCR
  uses: docker/login-action@v3
  with:
    registry: gcr.io
    username: _json_key
    password: ${{ secrets.GCR_JSON_KEY }}
```

### Other Registries

```yaml
- name: Login to Registry
  run: |
    echo "${{ secrets.REGISTRY_PASSWORD }}" | docker login <registry-url> \
      -u "${{ secrets.REGISTRY_USERNAME }}" --password-stdin
```

## How It Works

1. **Downloads twistcli**: The action downloads the `twistcli` binary directly from your Prisma Cloud Console
2. **Pulls the image**: Attempts to pull the Docker image from the specified registry
3. **Scans the image**: Uses `twistcli images scan` to analyze the image for vulnerabilities and compliance issues
4. **Parses results**: Extracts vulnerability and compliance counts from the scan results JSON
5. **Blocks on issues**: Fails the action if critical or high severity issues are found
6. **Outputs results**: Provides detailed counts as action outputs for downstream jobs

## Troubleshooting

### Image Pull Failures

If the image pull fails, the action will display helpful instructions for authenticating with your registry. Common issues:

1. **Missing authentication** - Add a login step before calling this action
2. **Wrong registry URL** - Verify the `image_registry` input matches your actual registry
3. **Wrong image tag** - Verify the `image_tag` is correct and the image exists
4. **Network issues** - Ensure the runner can reach the registry

### Scan Failures

If the scan itself fails:

1. **Invalid Prisma Cloud credentials** - Verify `pcc_user` and `pcc_pass` are correct
2. **Wrong Console URL** - Verify `pcc_console_url` is correct and accessible
3. **Network connectivity** - Ensure the runner can reach the Prisma Cloud Console

### Result Parsing Issues

The action attempts to parse scan results using the standard `twistcli` output format. If parsing fails:

1. The action will try alternate JSON paths (`vulnerabilityDistribution` and `complianceDistribution`)
2. Check the `pcc_scan_results.json` file for the actual structure
3. Review the action logs for JSON structure debugging output

## Example: Full CI/CD Pipeline

```yaml
name: Build, Scan, and Deploy

on:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.meta.outputs.version }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Login to Amazon ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Docker meta
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: 868978040651.dkr.ecr.us-east-1.amazonaws.com/${{ github.event.repository.name }}
          tags: |
            type=semver,pattern={{version}}
            type=sha,prefix={{version}}-sha-

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}

  security-scan:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Login to Amazon ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Scan Image with Prisma Cloud
        uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
        with:
          image_registry: "868978040651.dkr.ecr.us-east-1.amazonaws.com"
          image_tag: ${{ needs.build.outputs.image_tag }}
          pcc_console_url: "https://console.prisma.cloud"
          pcc_user: ${{ secrets.PRISMACLOUD_ACCESS_KEY_ID }}
          pcc_pass: ${{ secrets.PRISMACLOUD_SECRET_KEY }}

  deploy:
    needs: [build, security-scan]
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          echo "Deploying ${{ needs.build.outputs.image_tag }}"
          # Your deployment steps here
```

## Advanced Usage

### Scanning Without Publishing to Console

```yaml
- name: Scan Image (no publish)
  uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
  with:
    image_registry: "my-registry.example.com"
    image_tag: "test-123"
    pcc_console_url: ${{ secrets.PCC_CONSOLE_URL }}
    pcc_user: ${{ secrets.PCC_USER }}
    pcc_pass: ${{ secrets.PCC_PASS }}
    twistcli_publish: "false"
```

### Conditional Deployment Based on Scan Results

```yaml
- name: Scan Image
  id: scan
  uses: SolaceDev/solace-public-workflows/prisma-cloud-scan@main
  continue-on-error: true
  with:
    image_registry: "my-registry.example.com"
    image_tag: "v1.0.0"
    pcc_console_url: ${{ secrets.PCC_CONSOLE_URL }}
    pcc_user: ${{ secrets.PCC_USER }}
    pcc_pass: ${{ secrets.PCC_PASS }}

- name: Deploy only if scan passed
  if: steps.scan.outputs.scan_passed == 'true'
  run: |
    echo "Deploying secure image"
    # deployment commands
```

## Security Considerations

- Store Prisma Cloud credentials (`pcc_user` and `pcc_pass`) as GitHub Secrets
- Use repository or environment secrets for sensitive values
- Consider using OIDC authentication for AWS credentials instead of long-lived access keys
- Regularly rotate Prisma Cloud access keys
- Review and update your Prisma Cloud policies to match your security requirements

## License

This action is maintained by Solace and is available under the terms specified in the repository license.

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review the action logs for detailed error messages
3. Open an issue in the repository
4. Consult the [Prisma Cloud documentation](https://docs.paloaltonetworks.com/prisma/prisma-cloud)

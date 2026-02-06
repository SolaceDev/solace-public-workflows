# Shareable Workflows for Solace Organization

Reusable GitHub Actions workflows and actions for Solace repositories providing standardized CI/CD patterns for security scanning, compliance, and configuration management.

## Workflows

### SCA Scan and Guard

Software Composition Analysis (SCA) scanning for source code dependencies with FOSSA.

**Documentation**: [Complete Usage Guide](.github/workflows/docs/sca-scan-and-guard.md)

### Container Scan and Guard

Container image security scanning with FOSSA and optional Prisma Cloud integration.

**Documentation**: [Complete Usage Guide](.github/workflows/docs/container-scan-and-guard.md)

## Actions

### SCA Actions

- [sca-scan](`.github/actions/sca/sca-scan/`) - Generic SCA scan entrypoint with parameter routing
- [fossa-scan](`.github/actions/sca/fossa-scan/`) - FOSSA CLI integration with 48+ configurable parameters
- [fossa-guard](`.github/actions/fossa-guard/`) - Policy and vulnerability enforcement

### Container Actions

- [container-scan](container/container-scan/) - Multi-scanner orchestrator for container security
- [fossa-scan](container/fossa-scan/) - FOSSA container image analysis
- [prisma-scan](container/prisma-scan/) - Prisma Cloud security scanning

### Utility Actions

- [workflow-config-loader](workflow-config-loader/) - Centralized JSON config file parser
- [cicd-helper](`.github/actions/cicd-helper/`) - Common CI/CD utilities
- [pr-size-check](`.github/actions/pr-size-check/`) - Pull request size validation

## Configuration

All workflows support centralized configuration via `.github/workflow-config.json` files.

**Documentation**: [Workflow Config Schema](workflow-config-loader/workflow-config-schema.md)

## Support

- **Issues**: [GitHub Issues](https://github.com/SolaceDev/solace-public-workflows/issues)
- **Documentation**: See workflow and action READMEs linked above

## License

Copyright © Solace Corporation. All rights reserved.

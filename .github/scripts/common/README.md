# Common Workflow Python Helpers

Shared helpers for Python scripts used by reusable actions.

Current module:

- `github_reporting.py`
  - GitHub API requests
  - check-run create/resolve helpers
  - PR comment upsert helper
  - step-summary and output helpers
  - PR number normalization helpers

- `ci_payload.py`
  - safe boolean conversion for CI env vars
  - safe integer parsing for optional numeric fields
  - resilient JSON file loading with fallback defaults

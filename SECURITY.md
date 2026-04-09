# Security Policy

## Supported versions

Security fixes are provided on a best-effort basis for the latest `main` branch.

## Reporting a vulnerability

Please do not open a public issue for security vulnerabilities.

Use private reporting and include:

1. Affected component and version/commit.
2. Reproduction steps or proof of concept.
3. Impact assessment.
4. Suggested mitigation (if available).

The maintainers will acknowledge the report, triage impact, and coordinate
fix and disclosure timing.

## Secret handling

- Never commit API keys or credential-like values.
- Use environment variables or local untracked overrides.
- Rotate exposed keys immediately if leakage is suspected.

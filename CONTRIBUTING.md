# Contributing Guide

Thank you for contributing to docs_agent.

## Development setup

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Optional browser runtime for crawler: `playwright install chromium`.

## Branch and PR workflow

1. Create a feature branch from `main`.
2. Keep changes focused and atomic.
3. Open a Pull Request and describe:
   - motivation
   - implementation details
   - testing evidence

## Coding standards

1. Keep public behavior backward compatible unless the change explicitly breaks API.
2. Add concise comments only for non-obvious logic.
3. Do not commit secrets, API keys, runtime logs, or local data.

## Local checks before PR

1. Run static compile check:
   - `python -m compileall main.py ingestion core_agent "tools_&_rag" "output_&_delivery"`
2. Verify README changes when behavior/config is changed.

## Commit message suggestion

Use concise prefixes such as:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation only
- `refactor:` code refactor without behavior change
- `chore:` maintenance work

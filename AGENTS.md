# AGENTS.md

This repository contains a small Python CLI for diagnosing Model Context Protocol server configuration files.

## Development Rules

- Keep the package dependency-free unless a dependency removes substantial protocol or platform complexity.
- Support Python 3.10 and newer.
- Prefer focused checks with clear remediation hints over broad style opinions.
- Do not print secret values in findings, test failures, or debug output.
- Dynamic probing must only execute commands from user-provided local config files.
- Remote MCP transports are currently static-check only.

## Validation

Run before committing:

```bash
python -m unittest discover -s tests
python -m mcp_server_doctor check . --warnings-as-errors
python -m mcp_server_doctor check . --format sarif --output mcp-server-doctor.sarif
```

## Release Notes

When adding user-visible behavior, update:

- `README.md`
- `ROADMAP.md` if the change completes or changes a planned item
- tests for the new check or protocol behavior

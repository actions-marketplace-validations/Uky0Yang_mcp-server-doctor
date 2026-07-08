# Contributing

Thanks for improving `mcp-server-doctor`.

## Good First Contributions

- Add a new static check for a real MCP config failure mode.
- Add config path detection for another MCP-capable client.
- Improve protocol probing for resources, prompts, or transport edge cases.
- Add examples from common Claude, Cursor, VS Code, or Copilot setups.

## Local Setup

```bash
python -m pip install -e .
python -m unittest discover -s tests
mcp-server-doctor check . --warnings-as-errors
```

## Pull Request Expectations

- Keep changes small and focused.
- Include tests for new checks and bug fixes.
- Do not include real tokens, private config files, or machine-specific paths.
- Explain the user-facing problem the change solves.

## Security

If you find a security issue, please open a private disclosure or contact the maintainer before posting exploit details publicly.

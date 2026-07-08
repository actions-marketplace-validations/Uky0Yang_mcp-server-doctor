# mcp-server-doctor

Diagnose MCP server configs before Claude, Cursor, Copilot, or your coding agent fails to load tools.

`mcp-server-doctor` is a dependency-free Python CLI for people who install local Model Context Protocol servers and then get stuck with broken `mcp.json`, missing commands, hidden startup errors, or empty tool lists.

It checks MCP config files statically and can launch local stdio servers to run the same basic handshake a client needs: `initialize`, `notifications/initialized`, and capability listing such as `tools/list`.

## Why This Exists

MCP adoption is moving quickly across AI coding tools, IDEs, and desktop assistants. The painful part is still local setup:

- Config files live in different places across clients.
- `npx`, `uvx`, Docker, Python, and absolute-path commands fail differently.
- A server can show as configured but still expose no tools.
- Tokens often get pasted into config files during troubleshooting.
- Server logs accidentally written to stdout can break JSON-RPC.

This tool gives developers and maintainers a fast preflight check before opening the AI client.

## Install

From this repository:

```bash
python -m pip install -e .
```

After PyPI release:

```bash
python -m pip install mcp-server-doctor
```

## Quick Start

Check the current repository for MCP config files:

```bash
mcp-server-doctor .
```

Check a specific config file:

```bash
mcp-server-doctor check ~/.cursor/mcp.json
```

Run static checks plus stdio startup probes:

```bash
mcp-server-doctor doctor ~/.cursor/mcp.json
```

Probe one server:

```bash
mcp-server-doctor doctor ~/.cursor/mcp.json --server filesystem
```

Return JSON for CI or editor integrations:

```bash
mcp-server-doctor doctor . --format json
```

Write SARIF for GitHub code scanning:

```bash
mcp-server-doctor check . --format sarif --output mcp-server-doctor.sarif
```

Short alias:

```bash
mcp-doctor doctor .
```

## What It Checks

Static checks:

- Valid JSON
- Required `mcpServers` object
- Local stdio server command, args, env, and cwd types
- Missing executable on `PATH`
- Missing absolute command path
- Missing or invalid cwd
- Literal token-like values in `env` or `args`
- Secret-looking env values such as API keys and passwords
- Shell wrapper usage such as `bash -c` or `powershell -Command`
- Unpinned `npx`, `uvx`, or `bunx` package names
- Broad Docker volume mounts
- Remote MCP server configs, reported as static-check only

Dynamic stdio probe:

- Starts the configured command
- Sends `initialize`
- Sends `notifications/initialized`
- Lists tools when available
- Lists resources and prompts when advertised
- Detects non-JSON stdout before a protocol response
- Captures stderr tail on failures without exposing config secrets

## Example

Given:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  }
}
```

Run:

```bash
mcp-server-doctor check mcp.json
```

Output:

```text
mcp-server-doctor checked 1 config file(s), 1 server(s)
errors=0 warnings=1 info=0

Configs:
  - mcp.json
    - filesystem (stdio)

Findings:
  [warning] mcp.json#filesystem unpinned-package: npx package is not version-pinned: @modelcontextprotocol/server-filesystem
    hint: Pin package versions for reproducible MCP startup.
```

## Supported Config Locations

When no path is provided, the tool scans the current directory and common user-level locations when present:

- `mcp.json`
- `.mcp.json`
- `.cursor/mcp.json`
- `.vscode/mcp.json`
- `.github/copilot/mcp.json`
- Claude Desktop config on Windows, macOS, and Linux

Large generated folders such as `.git`, `node_modules`, `dist`, `build`, and virtual environments are skipped.

## CI

Use the packaged GitHub Action:

```yaml
name: MCP config check

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read
  security-events: write

jobs:
  mcp-doctor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7.0.0
      - uses: Uky0Yang/mcp-server-doctor@v0.2.0
        with:
          path: .
          command: check
          upload-results: "true"
          warnings-as-errors: "true"
```

Or install the CLI directly:

```yaml
name: MCP config check

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  mcp-doctor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7.0.0
      - uses: actions/setup-python@v6.3.0
        with:
          python-version: "3.12"
      - run: python -m pip install mcp-server-doctor
      - run: mcp-server-doctor check . --warnings-as-errors
```

Use `check` in CI unless your workflow intentionally installs and starts every configured MCP server.

## PyPI Release

This repository is prepared for PyPI Trusted Publishing. Configure a pending publisher on PyPI with:

- Project: `mcp-server-doctor`
- Owner: `Uky0Yang`
- Repository: `mcp-server-doctor`
- Workflow: `release.yml`
- Environment: `pypi`

Then publish with:

```bash
git tag v0.2.0
git push origin v0.2.0
```

See [docs/publishing.md](docs/publishing.md).

## Exit Codes

- `0`: no errors
- `1`: static check failed, or warnings failed under `--warnings-as-errors`
- `2`: static checks passed, but at least one stdio probe failed

## Design Principles

- No model calls
- No network calls by the doctor itself
- No runtime dependencies
- No secret values printed
- Clear findings that point to a fix
- Dynamic probing limited to local stdio commands from the provided config

## Current Limitations

- Streamable HTTP and OAuth flows are not dynamically probed yet.
- The stdio probe uses newline-delimited JSON-RPC, which is what common MCP SDK stdio transports use.
- The tool does not rewrite configs yet.
- It cannot know whether an MCP tool is safe to call; it only verifies discovery and startup.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Useful contributions are real-world diagnostics from broken MCP setups, additional client config locations, and tests for server startup edge cases.

## License

MIT

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from .models import ConfigDocument, Finding, ServerSpec

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "node_modules",
}

CONFIG_NAMES = {
    "mcp.json",
    ".mcp.json",
    "claude_desktop_config.json",
}


def default_config_paths() -> list[Path]:
    paths: list[Path] = []
    home = Path.home()
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    paths.extend(
        [
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / ".config" / "Claude" / "claude_desktop_config.json",
            home / ".cursor" / "mcp.json",
            home / ".config" / "Code" / "User" / "mcp.json",
        ]
    )
    return paths


def discover_config_paths(inputs: Iterable[str]) -> list[Path]:
    candidates: list[Path] = []
    explicit = [Path(item).expanduser() for item in inputs]
    if not explicit:
        explicit = [Path.cwd()]
        candidates.extend(path for path in default_config_paths() if path.exists())

    for item in explicit:
        if item.is_file():
            candidates.append(item)
        elif item.is_dir():
            candidates.extend(_walk_for_configs(item))
        else:
            candidates.append(item)

    return _dedupe_paths(candidates)


def _walk_for_configs(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRS]
        current = Path(dirpath)
        for filename in filenames:
            if filename in CONFIG_NAMES:
                found.append(current / filename)
    return found


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        normalized = path.resolve() if path.exists() else path.absolute()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(path)
    return result


def load_config(path: Path) -> ConfigDocument:
    findings: list[Finding] = []
    servers: list[ServerSpec] = []

    if not path.exists():
        return ConfigDocument(
            path=path,
            servers=(),
            findings=(
                Finding("error", "config-not-found", "Config file does not exist.", path),
            ),
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        return ConfigDocument(
            path=path,
            servers=(),
            findings=(Finding("error", "config-encoding", f"Config is not UTF-8: {exc}", path),),
        )
    except json.JSONDecodeError as exc:
        return ConfigDocument(
            path=path,
            servers=(),
            findings=(
                Finding(
                    "error",
                    "invalid-json",
                    f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                    path,
                ),
            ),
        )

    if not isinstance(data, dict):
        return ConfigDocument(
            path=path,
            servers=(),
            findings=(Finding("error", "config-root", "Config root must be a JSON object.", path),),
        )

    server_map = data.get("mcpServers")
    if server_map is None:
        findings.append(
            Finding(
                "error",
                "missing-mcpServers",
                "Config must contain an mcpServers object.",
                path,
                hint='Use {"mcpServers": {"name": {"command": "...", "args": []}}}.',
            )
        )
        return ConfigDocument(path=path, servers=(), findings=tuple(findings))

    if not isinstance(server_map, dict):
        findings.append(Finding("error", "invalid-mcpServers", "mcpServers must be an object.", path))
        return ConfigDocument(path=path, servers=(), findings=tuple(findings))

    for name, raw_server in server_map.items():
        if not isinstance(name, str) or not name.strip():
            findings.append(Finding("error", "invalid-server-name", "Server names must be non-empty strings.", path))
            continue
        if not isinstance(raw_server, dict):
            findings.append(
                Finding("error", "invalid-server", "Server config must be an object.", path, server=str(name))
            )
            continue

        server, server_findings = _parse_server(path, name, raw_server)
        findings.extend(server_findings)
        servers.append(server)

    if not servers and not any(f.severity == "error" for f in findings):
        findings.append(Finding("warning", "empty-config", "No MCP servers are configured.", path))

    return ConfigDocument(path=path, servers=tuple(servers), findings=tuple(findings))


def _parse_server(path: Path, name: str, raw: dict[str, Any]) -> tuple[ServerSpec, list[Finding]]:
    findings: list[Finding] = []
    command = raw.get("command")
    url = raw.get("url")
    args = raw.get("args", [])
    env = raw.get("env", {})
    cwd = raw.get("cwd")

    if command is not None and not isinstance(command, str):
        findings.append(Finding("error", "invalid-command", "command must be a string.", path, server=name))
        command = None
    if url is not None and not isinstance(url, str):
        findings.append(Finding("error", "invalid-url", "url must be a string.", path, server=name))
        url = None
    if not command and not url:
        findings.append(
            Finding(
                "error",
                "missing-transport",
                "Server must define command for local stdio or url for remote transport.",
                path,
                server=name,
            )
        )

    parsed_args: tuple[str, ...] = ()
    if isinstance(args, list) and all(isinstance(item, str) for item in args):
        parsed_args = tuple(args)
    else:
        findings.append(Finding("error", "invalid-args", "args must be a list of strings.", path, server=name))

    parsed_env: dict[str, str] = {}
    if isinstance(env, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        parsed_env = dict(env)
    else:
        findings.append(Finding("error", "invalid-env", "env must be an object of string values.", path, server=name))

    if cwd is not None and not isinstance(cwd, str):
        findings.append(Finding("error", "invalid-cwd", "cwd must be a string.", path, server=name))
        cwd = None

    return (
        ServerSpec(
            name=name,
            path=path,
            raw=raw,
            command=command,
            args=parsed_args,
            env=parsed_env,
            cwd=cwd,
            url=url,
        ),
        findings,
    )

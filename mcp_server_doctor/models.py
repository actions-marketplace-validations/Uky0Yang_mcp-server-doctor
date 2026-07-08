from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: Path
    server: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": str(self.path),
        }
        if self.server:
            data["server"] = self.server
        if self.hint:
            data["hint"] = self.hint
        return data


@dataclass(frozen=True)
class ServerSpec:
    name: str
    path: Path
    raw: dict[str, Any]
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None

    @property
    def transport(self) -> str:
        if self.command:
            return "stdio"
        if self.url:
            return "remote"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
            "cwd": self.cwd,
            "url": self.url,
            "env": sorted(self.env),
        }


@dataclass(frozen=True)
class ConfigDocument:
    path: Path
    servers: tuple[ServerSpec, ...]
    findings: tuple[Finding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "servers": [server.to_dict() for server in self.servers],
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class ProbeResult:
    server: ServerSpec
    ok: bool
    message: str
    capabilities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    resources: int | None = None
    prompts: int | None = None
    stderr_tail: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "server": self.server.to_dict(),
            "ok": self.ok,
            "message": self.message,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "resources": self.resources,
            "prompts": self.prompts,
            "stderr_tail": list(self.stderr_tail),
        }

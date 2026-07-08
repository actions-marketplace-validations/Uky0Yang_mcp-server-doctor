from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .models import ConfigDocument, Finding, ServerSpec

SECRET_KEYWORDS = ("TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY", "API_KEY")
SECRET_PATTERNS = (
    re.compile(r"gh[oprsu]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
SHELL_COMMANDS = {"bash", "sh", "zsh", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
SHELL_EXEC_FLAGS = {"-c", "/c", "-command", "-encodedcommand"}
PACKAGE_RUNNERS = {"npx", "uvx", "bunx"}


def run_static_checks(document: ConfigDocument) -> tuple[Finding, ...]:
    findings: list[Finding] = list(document.findings)
    for server in document.servers:
        findings.extend(_check_server(server))
    return tuple(findings)


def has_blocking_errors(findings: tuple[Finding, ...]) -> bool:
    return any(finding.severity == "error" for finding in findings)


def _check_server(server: ServerSpec) -> list[Finding]:
    findings: list[Finding] = []
    if server.transport == "remote":
        findings.append(
            Finding(
                "info",
                "remote-server",
                "Remote MCP server detected; static checks only. stdio probe is skipped.",
                server.path,
                server=server.name,
            )
        )
        return findings

    if server.transport != "stdio" or not server.command:
        return findings

    findings.extend(_check_command(server))
    findings.extend(_check_env(server))
    findings.extend(_check_args(server))
    findings.extend(_check_cwd(server))
    return findings


def _check_command(server: ServerSpec) -> list[Finding]:
    assert server.command is not None
    command = server.command
    executable = command.split()[0] if " " in command and not Path(command).exists() else command
    command_name = Path(executable).name.lower()
    findings: list[Finding] = []

    if command_name in SHELL_COMMANDS and any(arg.lower() in SHELL_EXEC_FLAGS for arg in server.args):
        findings.append(
            Finding(
                "warning",
                "shell-wrapper",
                "Server starts through a shell execution flag; prefer a direct executable plus args.",
                server.path,
                server=server.name,
            )
        )

    if _looks_like_path(executable):
        if not Path(os.path.expandvars(os.path.expanduser(executable))).exists():
            findings.append(
                Finding(
                    "error",
                    "command-path-not-found",
                    f"Command path was not found: {executable}",
                    server.path,
                    server=server.name,
                )
            )
    elif shutil.which(executable) is None:
        findings.append(
            Finding(
                "error",
                "command-not-found",
                f"Command is not on PATH: {executable}",
                server.path,
                server=server.name,
            )
        )

    return findings


def _check_env(server: ServerSpec) -> list[Finding]:
    findings: list[Finding] = []
    for key, value in server.env.items():
        upper_key = key.upper()
        if any(keyword in upper_key for keyword in SECRET_KEYWORDS) and _is_literal_secret(value):
            findings.append(
                Finding(
                    "warning",
                    "literal-secret-env",
                    f"Environment variable {key} appears to contain a literal secret.",
                    server.path,
                    server=server.name,
                    hint="Prefer referencing a machine-level environment variable instead of committing credentials.",
                )
            )
        if _contains_secret(value):
            findings.append(
                Finding(
                    "error",
                    "secret-value",
                    f"Environment variable {key} contains a token-like value.",
                    server.path,
                    server=server.name,
                )
            )
    return findings


def _check_args(server: ServerSpec) -> list[Finding]:
    findings: list[Finding] = []
    lowered_command = Path(server.command or "").name.lower()
    args = list(server.args)

    if lowered_command in PACKAGE_RUNNERS:
        package = _first_package_arg(args)
        if package and _is_unpinned_package(package):
            findings.append(
                Finding(
                    "warning",
                    "unpinned-package",
                    f"{lowered_command} package is not version-pinned: {package}",
                    server.path,
                    server=server.name,
                    hint="Pin package versions for reproducible MCP startup.",
                )
            )

    joined = "\n".join(args)
    if _contains_secret(joined):
        findings.append(
            Finding(
                "error",
                "secret-arg",
                "args contain a token-like value.",
                server.path,
                server=server.name,
            )
        )

    for index, arg in enumerate(args):
        if arg in ("-v", "--volume") and index + 1 < len(args):
            volume = args[index + 1]
            if _maps_broad_host_path(volume):
                findings.append(
                    Finding(
                        "warning",
                        "broad-docker-volume",
                        "Docker volume appears to mount a broad host path.",
                        server.path,
                        server=server.name,
                        hint="Prefer mounting the narrowest directory the MCP server needs.",
                    )
                )

    return findings


def _check_cwd(server: ServerSpec) -> list[Finding]:
    if not server.cwd:
        return []
    cwd = Path(os.path.expandvars(os.path.expanduser(server.cwd)))
    if not cwd.exists():
        return [
            Finding(
                "error",
                "cwd-not-found",
                f"cwd does not exist: {server.cwd}",
                server.path,
                server=server.name,
            )
        ]
    if not cwd.is_dir():
        return [
            Finding("error", "cwd-not-directory", f"cwd is not a directory: {server.cwd}", server.path, server=server.name)
        ]
    return []


def _looks_like_path(value: str) -> bool:
    return any(separator in value for separator in ("/", "\\")) or Path(value).is_absolute()


def _contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_PATTERNS)


def _is_literal_secret(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith(("$", "${", "%")) or stripped.endswith("%"):
        return False
    return len(stripped) >= 12 or _contains_secret(stripped)


def _first_package_arg(args: list[str]) -> str | None:
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in ("-y", "--yes", "--quiet"):
            continue
        if arg in ("--package", "-p"):
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None


def _is_unpinned_package(package: str) -> bool:
    if package.startswith("@"):
        parts = package.split("@")
        return len(parts) < 3 or not parts[-1]
    return "@" not in package


def _maps_broad_host_path(volume: str) -> bool:
    host = volume.split(":", 1)[0]
    normalized = host.replace("\\", "/").rstrip("/")
    if normalized in ("", "/", "~"):
        return True
    if re.fullmatch(r"[A-Za-z]", normalized):
        return True
    if re.fullmatch(r"[A-Za-z]:", normalized):
        return True
    return normalized.lower() in (str(Path.home()).replace("\\", "/").lower().rstrip("/"),)

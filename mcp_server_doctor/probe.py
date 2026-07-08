from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import __version__
from .models import ProbeResult, ServerSpec


def probe_stdio_server(server: ServerSpec, timeout: float = 8.0) -> ProbeResult:
    if server.transport == "remote":
        return ProbeResult(server=server, ok=True, message="Remote server skipped; stdio probe does not apply.")
    if server.transport != "stdio" or not server.command:
        return ProbeResult(server=server, ok=False, message="Server has no local stdio command to probe.")

    command = [server.command, *server.args]
    cwd = _resolve_cwd(server)
    env = os.environ.copy()
    env.update(_expand_env(server.env))
    output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    stderr_lines: list[str] = []
    process: subprocess.Popen[str] | None = None

    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdin and process.stdout and process.stderr
        _start_reader("stdout", process.stdout, output_queue)
        _start_reader("stderr", process.stderr, output_queue)

        deadline = time.monotonic() + timeout
        _send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-server-doctor", "version": __version__},
                },
            },
        )
        init_response, stderr_lines = _read_response(process, output_queue, request_id=1, deadline=deadline, stderr=stderr_lines)
        if "error" in init_response:
            return ProbeResult(
                server=server,
                ok=False,
                message=f"initialize returned error: {_format_rpc_error(init_response['error'])}",
                stderr_tail=tuple(stderr_lines[-8:]),
            )

        result = init_response.get("result", {})
        capabilities = tuple(sorted((result.get("capabilities") or {}).keys())) if isinstance(result, dict) else ()
        _send(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        tools: tuple[str, ...] = ()
        resources: int | None = None
        prompts: int | None = None
        if not capabilities or "tools" in capabilities:
            _send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tools_response, stderr_lines = _read_response(
                process, output_queue, request_id=2, deadline=deadline, stderr=stderr_lines
            )
            if "error" in tools_response:
                if not capabilities:
                    return ProbeResult(
                        server=server,
                        ok=False,
                        message=f"tools/list returned error: {_format_rpc_error(tools_response['error'])}",
                        capabilities=capabilities,
                        stderr_tail=tuple(stderr_lines[-8:]),
                    )
            else:
                tools = _extract_tool_names(tools_response.get("result", {}))

        if "resources" in capabilities:
            _send(process, {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}})
            resources_response, stderr_lines = _read_response(
                process, output_queue, request_id=3, deadline=deadline, stderr=stderr_lines
            )
            resources = _count_items(resources_response.get("result", {}), "resources")

        if "prompts" in capabilities:
            _send(process, {"jsonrpc": "2.0", "id": 4, "method": "prompts/list", "params": {}})
            prompts_response, stderr_lines = _read_response(
                process, output_queue, request_id=4, deadline=deadline, stderr=stderr_lines
            )
            prompts = _count_items(prompts_response.get("result", {}), "prompts")

        detail = _success_message(tools, resources, prompts)
        return ProbeResult(
            server=server,
            ok=True,
            message=detail,
            capabilities=capabilities,
            tools=tools,
            resources=resources,
            prompts=prompts,
            stderr_tail=tuple(stderr_lines[-8:]),
        )
    except FileNotFoundError as exc:
        return ProbeResult(server=server, ok=False, message=f"Failed to start command: {exc}")
    except OSError as exc:
        return ProbeResult(server=server, ok=False, message=f"Process start failed: {exc}")
    except TimeoutError as exc:
        return ProbeResult(server=server, ok=False, message=str(exc), stderr_tail=tuple(stderr_lines[-8:]))
    except ProtocolError as exc:
        return ProbeResult(server=server, ok=False, message=str(exc), stderr_tail=tuple(stderr_lines[-8:]))
    finally:
        if process is not None:
            _stop_process(process)


class ProtocolError(RuntimeError):
    pass


def _resolve_cwd(server: ServerSpec) -> Path | None:
    if not server.cwd:
        return None
    return Path(os.path.expandvars(os.path.expanduser(server.cwd)))


def _expand_env(env: dict[str, str]) -> dict[str, str]:
    return {key: os.path.expandvars(value) for key, value in env.items()}


def _start_reader(name: str, stream: Any, output_queue: queue.Queue[tuple[str, str]]) -> None:
    def read_lines() -> None:
        for line in iter(stream.readline, ""):
            output_queue.put((name, line))

    thread = threading.Thread(target=read_lines, daemon=True)
    thread.start()


def _send(process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    if not process.stdin:
        raise ProtocolError("Server stdin is not available.")
    process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    process.stdin.flush()


def _read_response(
    process: subprocess.Popen[str],
    output_queue: queue.Queue[tuple[str, str]],
    request_id: int,
    deadline: float,
    stderr: list[str],
) -> tuple[dict[str, Any], list[str]]:
    while time.monotonic() < deadline:
        if process.poll() is not None and output_queue.empty():
            raise ProtocolError(f"Server exited before response id={request_id} was received.")
        try:
            stream_name, line = output_queue.get(timeout=0.05)
        except queue.Empty:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stream_name == "stderr":
            stderr.append(stripped)
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ProtocolError(
                f"Server wrote non-JSON data to stdout before response id={request_id}: {stripped[:120]} ({exc.msg})."
            ) from exc
        if message.get("id") == request_id:
            return message, stderr
    raise TimeoutError(f"Timed out waiting for response id={request_id}.")


def _format_rpc_error(error: Any) -> str:
    if not isinstance(error, dict):
        return str(error)
    code = error.get("code", "unknown")
    message = error.get("message", "unknown error")
    return f"{code} {message}"


def _extract_tool_names(result: Any) -> tuple[str, ...]:
    if not isinstance(result, dict):
        return ()
    tools = result.get("tools", [])
    if not isinstance(tools, list):
        return ()
    names = [item.get("name") for item in tools if isinstance(item, dict) and isinstance(item.get("name"), str)]
    return tuple(sorted(names))


def _count_items(result: Any, key: str) -> int | None:
    if not isinstance(result, dict):
        return None
    items = result.get(key)
    return len(items) if isinstance(items, list) else None


def _success_message(tools: tuple[str, ...], resources: int | None, prompts: int | None) -> str:
    parts: list[str] = ["initialize ok"]
    if tools:
        parts.append(f"{len(tools)} tool(s)")
    elif tools == ():
        parts.append("0 tool(s)")
    if resources is not None:
        parts.append(f"{resources} resource(s)")
    if prompts is not None:
        parts.append(f"{prompts} prompt(s)")
    return ", ".join(parts)


def _stop_process(process: subprocess.Popen[str]) -> None:
    try:
        if process.stdin:
            process.stdin.close()
    except OSError:
        pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
    for stream in (process.stdout, process.stderr):
        try:
            if stream:
                stream.close()
        except OSError:
            pass

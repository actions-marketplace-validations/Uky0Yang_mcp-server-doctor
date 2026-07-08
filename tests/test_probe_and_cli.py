import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp_server_doctor.cli import main
from mcp_server_doctor.config import load_config
from mcp_server_doctor.probe import probe_stdio_server


FAKE_SERVER = r"""
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "0.1.0"}
            }
        }), flush=True)
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}
        }), flush=True)
"""


class ProbeAndCliTest(unittest.TestCase):
    def test_probe_stdio_server_lists_tools(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            server_py = root / "fake_server.py"
            server_py.write_text(textwrap.dedent(FAKE_SERVER), encoding="utf-8")
            config = root / "mcp.json"
            config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "fake": {
                                "command": sys.executable,
                                "args": [str(server_py)],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            server = load_config(config).servers[0]
            result = probe_stdio_server(server, timeout=3)

            self.assertTrue(result.ok, result.message)
            self.assertEqual(result.tools, ("echo",))

    def test_cli_check_returns_zero_for_valid_config(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "mcp.json"
            config.write_text(
                json.dumps({"mcpServers": {"python": {"command": sys.executable, "args": ["-V"]}}}),
                encoding="utf-8",
            )

            self.assertEqual(main(["check", str(config), "--format", "json"]), 0)

    def test_installed_module_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "mcp_server_doctor", "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Diagnose MCP server config files", result.stdout)


if __name__ == "__main__":
    unittest.main()

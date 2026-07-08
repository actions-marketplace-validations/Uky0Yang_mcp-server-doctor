import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp_server_doctor.checks import run_static_checks
from mcp_server_doctor.config import discover_config_paths, load_config


class ConfigAndChecksTest(unittest.TestCase):
    def test_loads_mcp_servers(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "mcp.json"
            config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "fake": {
                                "command": sys.executable,
                                "args": ["server.py"],
                                "env": {"SAFE_FLAG": "1"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            document = load_config(config)

            self.assertEqual(len(document.servers), 1)
            self.assertEqual(document.servers[0].name, "fake")
            self.assertEqual(document.servers[0].transport, "stdio")

    def test_reports_invalid_json(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "mcp.json"
            config.write_text('{"mcpServers": ', encoding="utf-8")

            document = load_config(config)

            self.assertEqual(document.findings[0].code, "invalid-json")
            self.assertEqual(document.findings[0].severity, "error")

    def test_static_checks_find_missing_command_and_secret(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "mcp.json"
            config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "bad": {
                                "command": "definitely-not-a-real-command",
                                "env": {"OPENAI_API_KEY": "sk-" + ("a" * 32)},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            findings = run_static_checks(load_config(config))
            codes = {finding.code for finding in findings}

            self.assertIn("command-not-found", codes)
            self.assertIn("secret-value", codes)

    def test_discovers_project_config_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".cursor").mkdir()
            (root / ".cursor" / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")

            found = discover_config_paths([str(root)])

            self.assertEqual(found, [root / ".cursor" / "mcp.json"])


if __name__ == "__main__":
    unittest.main()

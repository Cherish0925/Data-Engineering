import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CLITests(unittest.TestCase):
    def test_installed_cli_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run([sys.executable, "-m", "ai_data", "build", str(EXAMPLES / "local.recipe.json"),
                                     "--output", str(root / "发布")], cwd=root, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["counts"]["splits"], {"train": 3, "validation": 1, "test": 1})
            verify = subprocess.run([sys.executable, "-m", "ai_data", "verify", str(root / "发布")],
                                    cwd=root, capture_output=True, timeout=30)
            self.assertEqual(verify.returncode, 0, verify.stderr.decode("utf-8"))
            self.assertTrue(json.loads(verify.stdout)["ok"])
            config = root / "server.json"
            connect = subprocess.run([sys.executable, "-m", "ai_data", "connect", "--root", str(root), "--output", str(config)],
                                     cwd=root, capture_output=True, timeout=30)
            self.assertEqual(connect.returncode, 0, connect.stderr.decode("utf-8"))
            value = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["data-engineering"]
            self.assertEqual(value["command"], sys.executable)
            self.assertEqual(value["args"][-1], str(root.resolve()))

    def test_bad_recipe_returns_json_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.json").write_text('{"schema_version":"unsupported"}')
            result = subprocess.run([sys.executable, "-m", "ai_data", "build", str(root / "bad.json"),
                                     "--output", str(root / "output")], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertIn("error", json.loads(result.stderr))
            self.assertFalse((root / "output").exists())


@unittest.skipUnless(importlib.util.find_spec("mcp"), "optional MCP SDK not installed")
class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_tools_and_workspace(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("records.jsonl", "local.recipe.json"):
                shutil.copyfile(EXAMPLES / name, root / name)
            env = dict(os.environ)
            params = StdioServerParameters(command=sys.executable,
                                           args=["-m", "ai_data", "serve", "--root", str(root)], env=env)
            async with asyncio.timeout(30):
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        names = {t.name for t in (await session.list_tools()).tools}
                        self.assertEqual(names, {"data_capabilities", "data_profile", "data_build", "data_inspect", "data_verify"})
                        result = await session.call_tool("data_build", {"recipe": "local.recipe.json", "output": "release"})
                        self.assertFalse(result.isError, result.content)
                        result = await session.call_tool("data_verify", {"path": "release"})
                        self.assertFalse(result.isError, result.content)
                        self.assertTrue(json.loads(result.content[0].text)["ok"])
                        forbidden = await session.call_tool("data_profile", {"path": "../outside.jsonl"})
                        self.assertTrue(forbidden.isError)
                        overwrite = await session.call_tool("data_build", {"recipe": "local.recipe.json", "output": "release"})
                        self.assertTrue(overwrite.isError)


if __name__ == "__main__":
    unittest.main()

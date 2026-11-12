"""Tests for the MCP server — handler unit tests + a stdio smoke test."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from skribe import mcp_server

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


class HandlerTests(unittest.TestCase):
    def test_initialize(self):
        response = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {}})
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["serverInfo"]["name"],
                         "skribe")
        self.assertIn("protocolVersion", response["result"])
        self.assertIn("tools",
                      response["result"]["capabilities"])

    def test_notification_gets_no_response(self):
        self.assertIsNone(mcp_server.handle_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_ping(self):
        response = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(response["result"], {})

    def test_tools_list(self):
        response = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        names = {t["name"] for t in response["result"]["tools"]}
        self.assertEqual(names, {"skribe_grade", "skribe_polish",
                                 "skribe_verify"})
        for tool in response["result"]["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertIn("text",
                          tool["inputSchema"]["properties"])

    def test_unknown_method_errors(self):
        response = mcp_server.handle_message(
            {"jsonrpc": "2.0", "id": 4, "method": "nope/nothing"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_non_object_message_errors(self):
        response = mcp_server.handle_message([1, 2, 3])
        self.assertEqual(response["error"]["code"], -32600)

    def test_grade_tool(self):
        response = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "skribe_grade",
                       "arguments": {"text": "# Title\n\nText.\n"}}})
        payload = json.loads(
            response["result"]["content"][0]["text"])
        self.assertIn("fzi", payload)
        self.assertEqual(len(payload["metrics"]), 6)

    def test_polish_tool(self):
        response = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "skribe_polish",
                       "arguments": {"text": "# T\n\n### Deep\n\nX.\n"}}})
        payload = json.loads(
            response["result"]["content"][0]["text"])
        self.assertIn("text", payload)
        self.assertIn("final_fzi", payload)
        self.assertIn("## Deep", payload["text"])

    def test_verify_tool(self):
        response = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "skribe_verify",
                       "arguments": {"text": "# T\n\nText.\n"}}})
        payload = json.loads(
            response["result"]["content"][0]["text"])
        self.assertIn("passed", payload)
        self.assertIn("checks", payload)

    def test_unknown_tool_is_error_content(self):
        response = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "skribe_nope", "arguments": {}}})
        self.assertTrue(response["result"]["isError"])

    def test_missing_text_is_error_content(self):
        response = mcp_server.handle_message({
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "skribe_grade", "arguments": {}}})
        self.assertTrue(response["result"]["isError"])


class StdioSmokeTests(unittest.TestCase):
    def test_stdio_session(self):
        env = dict(os.environ, PYTHONPATH=str(SRC))
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "skribe_grade",
                        "arguments": {"text": "# T\n\nText.\n"}}},
            "this is not json",
        ]
        input_text = "\n".join(
            line if isinstance(line, str) else json.dumps(line)
            for line in lines) + "\n"
        proc = subprocess.run(
            [sys.executable, "-m", "skribe", "mcp"],
            input=input_text, capture_output=True, text=True,
            env=env, cwd=ROOT, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        responses = [json.loads(line) for line in
                     proc.stdout.strip().split("\n")]
        # initialize, tools/list, tools/call, parse-error = 4
        # replies (the notification gets none).
        self.assertEqual(len(responses), 4)
        self.assertEqual(responses[0]["id"], 1)
        self.assertEqual(responses[1]["id"], 2)
        self.assertEqual(responses[2]["id"], 3)
        self.assertEqual(responses[3]["error"]["code"], -32700)
        payload = json.loads(
            responses[2]["result"]["content"][0]["text"])
        self.assertIn("fzi", payload)


if __name__ == "__main__":
    unittest.main()

"""SKRIBE's MCP server — the same operations, for agents.

Stdio JSON-RPC, no SDK, standard library only. Speak the Model
Context Protocol just far enough to be useful: initialize,
tools/list, tools/call, ping. Nothing but JSON-RPC goes to stdout;
anything diagnostic goes to stderr.

Tools:
- skribe_grade:   {text, purpose?, audience?, scorer?, api_key?}
- skribe_polish:  {text, max_cycles?, target?, min_gain?}
- skribe_verify:  {text}

Run it with `skribe mcp`. An API key passed to skribe_grade for
the Decisions scorer is used for that one call only — never
printed, logged, or stored.
"""
from __future__ import annotations

import json
import sys

from . import __version__, api as api_mod
from .loop import LoopConfig
from .prompt import ScorerError

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "skribe"
SERVER_VERSION = __version__

TOOLS = [
    {
        "name": "skribe_grade",
        "description": "Score a document against the SKRIBE FZI "
                       "rubric. Returns the FZI (0-100), the score "
                       "band, and a per-metric breakdown with "
                       "reasons.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "The document text to grade."},
                "purpose": {"type": "string",
                            "description": "Stated purpose of the "
                                           "document (optional)."},
                "audience": {"type": "string",
                             "description": "Intended audience "
                                            "(optional)."},
                "scorer": {"type": "string", "enum": ["deterministic",
                                                       "decisions"],
                           "description": "Scorer to use (default: "
                                          "deterministic)."},
                "api_key": {"type": "string",
                            "description": "Gemini API key, only "
                                           "needed for the Decisions "
                                           "scorer."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "skribe_polish",
        "description": "Grade and revise a document through the "
                       "SKRIBE loop (grade, revise, re-grade until "
                       "the target is met, gains flatten, or the "
                       "cycle cap is hit). Returns the best version "
                       "with its scores and exit reason.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "The document text to polish."},
                "max_cycles": {"type": "integer",
                               "description": "Most revision cycles "
                                              "(default: 5)."},
                "target": {"type": "number",
                           "description": "Stop when FZI reaches this "
                                          "(default: 90)."},
                "min_gain": {"type": "number",
                             "description": "Stop when a cycle gains "
                                            "this or less (default: 1)."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "skribe_verify",
        "description": "Run SKRIBE's output-verification checks on a "
                       "document: size cap, scaffold compliance, "
                       "unique and complete sections, no placeholders, "
                       "metadata present.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "The document text to verify."},
            },
            "required": ["text"],
        },
    },
]


def _text_content(payload):
    return {"content": [{"type": "text",
                         "text": json.dumps(payload, indent=2)}]}


def _error_content(message):
    return {"content": [{"type": "text", "text": f"Error: {message}"}],
            "isError": True}


def _call_tool(name, arguments):
    args = arguments if isinstance(arguments, dict) else {}
    if name == "skribe_grade":
        text = args.get("text")
        if not isinstance(text, str):
            return _error_content("skribe_grade needs a 'text' string")
        try:
            result = api_mod.grade(
                text, scorer=args.get("scorer", "deterministic"),
                api_key=args.get("api_key"),
                purpose=args.get("purpose"),
                audience=args.get("audience"))
        except (ScorerError, ValueError) as exc:
            return _error_content(str(exc))
        return _text_content(result.to_dict())
    if name == "skribe_polish":
        text = args.get("text")
        if not isinstance(text, str):
            return _error_content("skribe_polish needs a 'text' string")
        config = LoopConfig(
            target_fzi=args.get("target", 90.0),
            min_gain=args.get("min_gain", 1.0),
            max_cycles=args.get("max_cycles", 5))
        try:
            result = api_mod.polish(text, config=config)
        except (ScorerError, ValueError) as exc:
            return _error_content(str(exc))
        payload = result.to_dict()
        payload["text"] = result.text
        return _text_content(payload)
    if name == "skribe_verify":
        text = args.get("text")
        if not isinstance(text, str):
            return _error_content("skribe_verify needs a 'text' string")
        return _text_content(api_mod.verify(text).to_dict())
    return _error_content(f"unknown tool: {name}")


def handle_message(message):
    """Handle one decoded JSON-RPC message. Returns the response
    dict, or None for notifications (no reply)."""
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    method = message.get("method", "")
    msg_id = message.get("id")
    is_notification = "id" not in message

    def result(payload):
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": payload}

    def error(code, text):
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": code, "message": text}}

    if method == "initialize":
        return result({
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME,
                           "version": SERVER_VERSION},
        })
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return result({})
    if method == "tools/list":
        return result({"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            return result(_call_tool(name, arguments))
        except Exception as exc:  # never drop the connection
            return result(_error_content(f"tool failed: {exc}"))
    return error(-32601, f"Method not found: {method}")


def serve(in_stream=None, out_stream=None):
    """Serve JSON-RPC over stdio until stdin closes. Returns 0."""
    in_stream = in_stream or sys.stdin
    out_stream = out_stream or sys.stdout
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700,
                                  "message": "Parse error"}}
            out_stream.write(json.dumps(response) + "\n")
            out_stream.flush()
            continue
        response = handle_message(message)
        if response is not None:
            out_stream.write(json.dumps(response) + "\n")
            out_stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())

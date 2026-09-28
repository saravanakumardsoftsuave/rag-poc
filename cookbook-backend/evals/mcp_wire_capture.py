"""W9 requirement 4: capture the raw JSON-RPC exchange (initialize ->
tools/list -> tools/call) against ingredient_server.py at the stdio-pipe
level - not through the mcp SDK's ClientSession, so what's captured is the
literal bytes on the wire, newline-delimited JSON-RPC with no
Content-Length framing (confirmed against this SDK version by inspecting
mcp.client.stdio's read loop).
"""

import json
import subprocess
import sys

REQUESTS = [
    {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "wire-capture-script", "version": "0.1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "lookup_ingredient", "arguments": {"name": "paneer"}},
    },
]


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp_servers.ingredient_server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    exchange = []
    try:
        for req in REQUESTS:
            line = json.dumps(req)
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            exchange.append({"direction": "client->server", "message": req})
            if "id" in req:  # only requests with an id get a response
                response_line = proc.stdout.readline()
                response = json.loads(response_line)
                exchange.append({"direction": "server->client", "message": response})
    finally:
        proc.stdin.close()
        proc.terminate()

    annotated = {
        "transport": "stdio, newline-delimited JSON-RPC 2.0 (no Content-Length framing)",
        "model_call_location": (
            "The model runs ONLY inside the host process (app/agent/core/loop.py), "
            "never inside ingredient_server.py - this server has zero imports of "
            "app.rag or any generation code, it only serves lookup_ingredient over "
            "its own static dataset."
        ),
        "field_annotations": {
            "jsonrpc": "protocol version literal, always \"2.0\"",
            "id": "correlates a response to its request; notifications (no id) get no reply",
            "method": "the JSON-RPC method name: initialize, tools/list, or tools/call",
            "params.protocolVersion": "MCP protocol version the client speaks",
            "params.capabilities": "client-advertised capabilities (empty here - this script is a raw probe, not a full client)",
            "params.clientInfo": "identifies the calling client for the server's logs",
            "params.name": "(tools/call) which tool to invoke",
            "params.arguments": "(tools/call) the tool's input arguments as a JSON object",
            "result.tools": "(tools/list response) the array of {name, description, inputSchema} the server exposes",
            "result.content": "(tools/call response) the tool's return value, wrapped as MCP content blocks",
        },
        "exchange": exchange,
    }

    with open("evals/wire.json", "w") as f:
        json.dump(annotated, f, indent=2, default=str)
    print(f"Captured {len(exchange)} messages to evals/wire.json")


if __name__ == "__main__":
    main()

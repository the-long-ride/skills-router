"""MCP Client layer to manage external MCP server subprocesses."""

from __future__ import annotations

import json
import os
import subprocess
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cache of tool list results to avoid launching subprocesses repeatedly
_DISCOVERED_TOOLS_CACHE: dict[str, list[dict[str, Any]]] = {}


class MCPClient:
    """Manages spawning, querying, and calling tools via subprocess MCP stdio."""

    def __init__(
        self,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.args = args
        self.env = env
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        """Spawn the MCP server process."""
        merged_env = dict(os.environ)
        if self.env:
            merged_env.update(self.env)

        try:
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=merged_env,
                bufsize=1,  # Line buffered
            )
        except Exception as e:
            logger.exception(
                f"Failed to start MCP server process '{self.command}': {e}"
            )
            raise

    def stop(self) -> None:
        """Clean up the spawned process."""
        if self.process:
            try:
                self.process.stdin.close()
            except Exception:
                pass
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def send_request(
        self,
        method: str,
        params: dict[str, Any],
        msg_id: int,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and block until the matching response ID is received."""
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("MCP process not running")

        req = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }
        self.process.stdin.write(json.dumps(req) + "\n")
        self.process.stdin.flush()

        while True:
            line = self.process.stdout.readline()
            if not line:
                # If EOF occurs, fetch stderr output to assist debugging
                stderr_text = ""
                try:
                    stderr_text = self.process.stderr.read()
                except Exception:
                    pass
                raise RuntimeError(
                    f"Subprocess stdout closed before receiving response for ID {msg_id}. "
                    f"Stderr: {stderr_text}"
                )

            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("id") == msg_id:
                    return msg
            except Exception:
                # Non-JSON or debug logging lines are ignored
                continue

    def discover_tools(self) -> list[dict[str, Any]]:
        """Query the tool list from the MCP server (cached)."""
        cache_key = f"{self.command} {' '.join(self.args)}"
        if cache_key in _DISCOVERED_TOOLS_CACHE:
            return _DISCOVERED_TOOLS_CACHE[cache_key]

        try:
            self.start()
            self.send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "skills-router-gateway",
                        "version": "1.0.0",
                    },
                },
                1,
            )
            res = self.send_request("tools/list", {}, 2)
            tools = res.get("result", {}).get("tools", [])
            _DISCOVERED_TOOLS_CACHE[cache_key] = tools
            return tools
        finally:
            self.stop()

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a specific tool on the MCP server."""
        try:
            self.start()
            self.send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "skills-router-gateway",
                        "version": "1.0.0",
                    },
                },
                1,
            )
            res = self.send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments,
                },
                2,
            )
            return res.get("result", {})
        finally:
            self.stop()

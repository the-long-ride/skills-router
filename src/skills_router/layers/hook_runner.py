"""Hook runner layer to execute lifecycle hooks from active installed skills."""

from __future__ import annotations

import json
import os
import subprocess
import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_hooks_for_event(
    event_name: str,
    active_hooks: dict[str, list[dict[str, Any]]],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute all active hooks registered for a lifecycle event.

    Args:
        event_name: Name of the hook event (e.g. "SessionStart").
        active_hooks: Dictionary of active hook definitions.
        context: Optional dictionary of context variables to pass to the hook environment.

    Returns:
        Dict containing accumulated "additional_context" and execution "status".
    """
    combined_additional_context = ""
    specs = active_hooks.get(event_name, [])

    for spec in specs:
        if spec.get("type") == "command":
            cmd = spec.get("command")
            if not cmd:
                continue

            try:
                env = dict(os.environ)
                if context:
                    # Pass whole context as JSON string and separate env variables
                    env["SKILLS_ROUTER_CONTEXT"] = json.dumps(context)
                    for k, v in context.items():
                        if isinstance(v, (str, int, float, bool)):
                            env[f"SKILLS_ROUTER_{k.upper()}"] = str(v)
                        elif isinstance(v, dict) or isinstance(v, list):
                            env[f"SKILLS_ROUTER_{k.upper()}"] = json.dumps(v)

                # Run hook command
                res = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    env=env,
                    check=False,
                )

                if res.returncode == 0:
                    # Parse command output. If JSON, extract additional_context or additionalContext
                    stdout_str = res.stdout.strip()
                    if stdout_str:
                        try:
                            data = json.loads(stdout_str)
                            extracted = None
                            if "additional_context" in data:
                                extracted = data["additional_context"]
                            elif "hookSpecificOutput" in data and isinstance(data["hookSpecificOutput"], dict):
                                extracted = data["hookSpecificOutput"].get("additionalContext")
                            elif "additionalContext" in data:
                                extracted = data["additionalContext"]

                            if isinstance(extracted, str):
                                combined_additional_context += "\n\n" + extracted
                            else:
                                # Not formatted as standard hook payload, append whole JSON string
                                combined_additional_context += "\n\n" + stdout_str
                        except Exception:
                            # Not valid JSON, append raw stdout
                            combined_additional_context += "\n\n" + stdout_str
                else:
                    logger.error(
                        f"Hook '{cmd}' failed with code {res.returncode}: {res.stderr}"
                    )
            except Exception as e:
                logger.exception(f"Error running hook command '{cmd}': {e}")

    return {
        "status": "OK",
        "additional_context": combined_additional_context.strip(),
    }


def format_hook_response(
    event_name: str,
    additional_context: str,
    target: str | None = None,
) -> dict[str, Any]:
    """Format the additional context to match the target agent's hook schema.

    Args:
        event_name: Lifecycle event name.
        additional_context: Accumulated raw hook output.
        target: Optional target agent identifier. If omitted, attempts to auto-detect
                based on environment variables.

    Returns:
        Structured JSON-RPC-friendly dictionary payload.
    """
    if not target:
        if "CURSOR_PLUGIN_ROOT" in os.environ:
            target = "cursor"
        elif "CLAUDE_PLUGIN_ROOT" in os.environ:
            target = "claude"
        elif "COPILOT_CLI" in os.environ:
            target = "github-copilot"
        else:
            target = "generic"

    normalized = target.lower().strip()
    if normalized in ("cursor", "cursorrules", "cursor-agent"):
        return {"additional_context": additional_context}
    elif normalized in ("claude", "claude-code", "anthropic-claude"):
        return {
            "hookSpecificOutput": {
                "hookEventName": event_name,
                "additionalContext": additional_context,
            }
        }
    else:
        # Default generic standard (Copilot/Cline etc.)
        return {"additionalContext": additional_context}

"""Workspace/Global notification dispatcher.

For MVP: prints to console via rich.  In production, dispatches to
agent channels.  Falls back to admin channel when agent_id is None (v5).
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)


class WGNotifier:
    """Dispatches Workspace/Global notifications to agents or the system admin channel."""

    def __init__(self, admin_channel_id: str = "system-admin", quiet: bool = False):
        self.admin_channel_id = admin_channel_id
        self.quiet = quiet
        self.console = Console()
        self._history: list[dict] = []

    def send(
        self,
        agent_id: str | None,
        title: str,
        body: str,
        action: str = "",
        wg_case: str = "",
        payload: dict | None = None,
    ) -> None:
        """Send a Workspace/Global notification.

        If ``agent_id`` is None, falls back to the admin channel (v5).
        """
        target = agent_id or self.admin_channel_id

        record = {
            "target": target,
            "title": title,
            "body": body,
            "action": action,
            "wg_case": wg_case,
            "payload": payload or {},
        }
        self._history.append(record)

        if self.quiet:
            logger.info(
                "Workspace/Global notification recorded: target=%s action=%s case=%s",
                target, action, wg_case,
            )
            return

        # MVP: print to console
        if target == self.admin_channel_id:
            subtitle = f"[dim]-> Admin channel ({self.admin_channel_id})[/dim]"
        else:
            subtitle = f"[dim]-> Agent: {target}[/dim]"

        self.console.print(
            Panel(
                f"{body}\n\n{subtitle}",
                title=f"[bold]{title}[/bold]",
                border_style="yellow",
            )
        )

        logger.info(
            "Workspace/Global notification sent: target=%s action=%s case=%s",
            target, action, wg_case,
        )

    @property
    def history(self) -> list[dict]:
        """Return all sent notifications (useful for testing)."""
        return list(self._history)

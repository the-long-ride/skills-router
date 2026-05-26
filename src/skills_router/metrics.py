"""Tiny Prometheus-style metrics registry for local daemon mode."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MetricsRegistry:
    """In-process counters and gauges rendered as Prometheus text format."""

    def __init__(self):
        self._lock = threading.Lock()
        self._values: dict[str, float] = {}

    def inc(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._values[name] = self._values.get(name, 0.0) + amount

    def set(self, name: str, value: float) -> None:
        with self._lock:
            self._values[name] = value

    def render(self) -> str:
        with self._lock:
            items = sorted(self._values.items())
        lines = []
        for name, value in items:
            safe_name = "skills_router_" + name
            lines.append(f"# TYPE {safe_name} gauge")
            lines.append(f"{safe_name} {value:g}")
        return "\n".join(lines) + "\n"


REGISTRY = MetricsRegistry()


def start_metrics_server(port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Start a background HTTP server serving ``/metrics``."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib handler naming
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            payload = REGISTRY.render().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            return

    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

"""Tests for lightweight metrics rendering."""

import urllib.request

from skills_router.metrics import REGISTRY, MetricsRegistry, start_metrics_server


def test_metrics_registry_renders_prometheus_text():
    registry = MetricsRegistry()
    registry.inc("installs_total")
    registry.set("registry_watch_degraded_tools", 2)

    rendered = registry.render()

    assert "skills_router_installs_total 1" in rendered
    assert "skills_router_registry_watch_degraded_tools 2" in rendered


def test_metrics_server_serves_metrics():
    REGISTRY.inc("test_requests_total")
    server = start_metrics_server(0)
    port = server.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics") as response:
            body = response.read().decode("utf-8")
    finally:
        server.shutdown()

    assert response.status == 200
    assert "skills_router_" in body

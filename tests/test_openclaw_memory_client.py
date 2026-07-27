"""Tests for the desktop client of the OpenClaw managed-memory API."""

from __future__ import annotations

import httpx
import pytest

from desktop_pet.openclaw_memory_client import (
    DEFAULT_OPENCLAW_HOOKS_URL,
    OpenClawMemoryClient,
    OpenClawMemoryError,
    memory_api_url,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, *, json_error=False):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._json_error:
            raise ValueError("invalid json")
        return self._payload


def test_memory_api_url_uses_hooks_origin_only():
    assert memory_api_url("https://localhost:18789/custom/hooks?x=1") == (
        "https://localhost:18789/pet-bubble-memory"
    )
    assert memory_api_url("not-a-url") == memory_api_url(DEFAULT_OPENCLAW_HOOKS_URL)


def test_list_memories_sends_agent_and_secret(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return FakeResponse(200, {"agentId": "healer-cat", "memories": [{"id": "m_1", "text": "tea"}]})

    monkeypatch.setattr("desktop_pet.openclaw_memory_client.httpx.request", fake_request)
    client = OpenClawMemoryClient("http://127.0.0.1:18789/hooks/agent", "secret", timeout=3.0)

    assert client.list_memories("healer-cat") == [{"id": "m_1", "text": "tea"}]
    assert captured == {
        "method": "GET",
        "url": "http://127.0.0.1:18789/pet-bubble-memory",
        "headers": {"Accept": "application/json", "X-Pet-Bubble-Secret": "secret"},
        "timeout": 3.0,
        "params": {"agentId": "healer-cat"},
    }


@pytest.mark.parametrize(
    ("operation", "expected_json"),
    [
        (lambda client: client.add_memory("agent-a", "remember this"), {"action": "add", "agentId": "agent-a", "text": "remember this"}),
        (lambda client: client.delete_memory("agent-a", "m_123456"), {"action": "delete", "agentId": "agent-a", "memoryId": "m_123456"}),
        (lambda client: client.clear_memories("agent-a"), {"action": "clear", "agentId": "agent-a", "confirm": True}),
    ],
)
def test_write_operations_send_expected_payload(monkeypatch, operation, expected_json):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(200, {"success": True})

    monkeypatch.setattr("desktop_pet.openclaw_memory_client.httpx.request", fake_request)
    result = operation(OpenClawMemoryClient("", ""))

    assert result == {"success": True}
    assert calls[0][0] == "POST"
    assert calls[0][2]["json"] == expected_json
    assert "X-Pet-Bubble-Secret" not in calls[0][2]["headers"]


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "auth"), (403, "auth"), (409, "conflict"), (500, "server")],
)
def test_http_errors_are_categorized(monkeypatch, status, kind):
    monkeypatch.setattr(
        "desktop_pet.openclaw_memory_client.httpx.request",
        lambda *args, **kwargs: FakeResponse(status, {"error": "request rejected"}),
    )

    with pytest.raises(OpenClawMemoryError) as error:
        OpenClawMemoryClient("", "secret").list_memories("agent-a")

    assert error.value.kind == kind
    assert error.value.status_code == status
    assert str(error.value) == "request rejected"


@pytest.mark.parametrize("exception", [httpx.ConnectError("offline"), httpx.ReadTimeout("slow")])
def test_connection_errors_are_categorized(monkeypatch, exception):
    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr("desktop_pet.openclaw_memory_client.httpx.request", fail)

    with pytest.raises(OpenClawMemoryError) as error:
        OpenClawMemoryClient("", "secret").list_memories("agent-a")

    assert error.value.kind == "connection"


def test_invalid_success_payload_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "desktop_pet.openclaw_memory_client.httpx.request",
        lambda *args, **kwargs: FakeResponse(200, ["not", "an", "object"]),
    )
    with pytest.raises(OpenClawMemoryError, match="invalid response"):
        OpenClawMemoryClient("", "secret").list_memories("agent-a")


def test_invalid_memory_list_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "desktop_pet.openclaw_memory_client.httpx.request",
        lambda *args, **kwargs: FakeResponse(200, {"memories": "not-a-list"}),
    )
    with pytest.raises(OpenClawMemoryError, match="invalid memory list"):
        OpenClawMemoryClient("", "secret").list_memories("agent-a")

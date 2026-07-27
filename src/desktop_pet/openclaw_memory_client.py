"""HTTP client for the OpenClaw pet-bubble managed-memory API."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import httpx


DEFAULT_OPENCLAW_HOOKS_URL = "http://127.0.0.1:18789/hooks/agent"
MEMORY_API_PATH = "/pet-bubble-memory"


class OpenClawMemoryError(RuntimeError):
    """A categorized OpenClaw memory API failure."""

    def __init__(self, message: str, *, kind: str = "server", status_code: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


def memory_api_url(hooks_url: str) -> str:
    """Derive the plugin memory endpoint from the configured Hooks URL."""
    raw = (hooks_url or DEFAULT_OPENCLAW_HOOKS_URL).strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        parsed = urlsplit(DEFAULT_OPENCLAW_HOOKS_URL)
    return urlunsplit((parsed.scheme, parsed.netloc, MEMORY_API_PATH, "", ""))


class OpenClawMemoryClient:
    """Small synchronous client intended to run from a worker thread."""

    def __init__(self, hooks_url: str, secret: str, *, timeout: float = 5.0):
        self.url = memory_api_url(hooks_url)
        self.secret = secret or ""
        self.timeout = timeout

    def list_memories(self, agent_id: str) -> list[dict]:
        data = self._request("GET", params={"agentId": agent_id})
        memories = data.get("memories", [])
        if not isinstance(memories, list):
            raise OpenClawMemoryError("OpenClaw returned an invalid memory list")
        return memories

    def add_memory(self, agent_id: str, text: str) -> dict:
        return self._request(
            "POST", json={"action": "add", "agentId": agent_id, "text": text}
        )

    def delete_memory(self, agent_id: str, memory_id: str) -> dict:
        return self._request(
            "POST",
            json={"action": "delete", "agentId": agent_id, "memoryId": memory_id},
        )

    def clear_memories(self, agent_id: str) -> dict:
        return self._request(
            "POST", json={"action": "clear", "agentId": agent_id, "confirm": True}
        )

    def _request(self, method: str, **kwargs) -> dict:
        headers = {"Accept": "application/json"}
        if self.secret:
            headers["X-Pet-Bubble-Secret"] = self.secret
        try:
            response = httpx.request(
                method, self.url, headers=headers, timeout=self.timeout, **kwargs
            )
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            raise OpenClawMemoryError(
                "Unable to connect to the OpenClaw memory service",
                kind="connection",
            ) from error
        except httpx.HTTPError as error:
            raise OpenClawMemoryError(str(error), kind="connection") from error

        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_success:
            if not isinstance(payload, dict):
                raise OpenClawMemoryError("OpenClaw returned an invalid response")
            return payload

        message = payload.get("error") if isinstance(payload, dict) else None
        message = str(message or f"OpenClaw memory request failed ({response.status_code})")
        if response.status_code in {401, 403}:
            kind = "auth"
        elif response.status_code == 409:
            kind = "conflict"
        else:
            kind = "server"
        raise OpenClawMemoryError(message, kind=kind, status_code=response.status_code)

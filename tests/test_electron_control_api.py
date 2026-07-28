"""HTTP coverage for Electron control-center API endpoints."""

import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from desktop_pet.api_server import ApiServer


class _GlobalConfig:
    def __init__(self):
        self.config = {
            "api": {"enabled": True, "host": "127.0.0.1", "port": 8080, "allowed_ips": ["127.0.0.1"]},
            "tray": {"enabled": True, "minimize_to_tray": True},
            "startup": {"enabled": False, "start_hidden": False},
            "display": {},
            "llm": {"enabled": False, "api_key": "stored-secret"},
            "mcp": {"enabled": False, "openclaw_secret_token": "stored-token"},
        }
        self.saved = None

    @property
    def api(self):
        return self.config["api"]

    @property
    def mcp(self):
        return self.config["mcp"]

    def save_global_settings(self, sections):
        self.saved = sections
        self.config.update(sections)


class _Platform:
    def __init__(self):
        self.global_config = _GlobalConfig()
        self.pet_loader = SimpleNamespace(scan_pets=lambda: [], load_pet=lambda _: None)
        self.pet_packages = {}
        self.api_server = None

    def get_instance_config(self, pet_id):
        if pet_id != "pet-1":
            return None
        return SimpleNamespace(agent={"enabled": True, "agent_id": "test-agent"})


class _MemoryClient:
    def __init__(self):
        self.calls = []

    def list_memories(self, agent_id):
        self.calls.append(("list", agent_id))
        return [{"id": "memory-1", "text": "existing memory"}]

    def add_memory(self, agent_id, text):
        self.calls.append(("add", agent_id, text))
        return {"id": "memory-2", "text": text}

    def delete_memory(self, agent_id, memory_id):
        self.calls.append(("delete", agent_id, memory_id))
        return {"success": True}

    def clear_memories(self, agent_id):
        self.calls.append(("clear", agent_id))
        return {"success": True}


async def _client(server: ApiServer) -> TestClient:
    server._app = web.Application()
    server._setup_ip_filter()
    server._setup_routes()
    server._setup_cors()
    client = TestClient(TestServer(server._app))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_control_center_health_and_masked_global_settings():
    platform = _Platform()
    server = ApiServer(platform)
    platform.api_server = server
    server._run_in_main_thread = lambda func: _resolved(func())
    client = await _client(server)
    try:
        health = await client.get("/api/control-center/health")
        assert health.status == 200
        assert await health.json() == {"connected": True, "api_running": False}

        settings = await client.get("/api/control-center/global-settings")
        assert settings.status == 200
        payload = await settings.json()
        assert payload["llm"]["api_key_configured"] is True
        assert "api_key" not in payload["llm"]
        assert payload["mcp"]["openclaw_secret_token_configured"] is True
        assert "openclaw_secret_token" not in payload["mcp"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_control_center_updates_global_settings_without_overwriting_secret():
    platform = _Platform()
    server = ApiServer(platform)
    platform.api_server = server
    server._run_in_main_thread = lambda func: _resolved(func())
    client = await _client(server)
    try:
        response = await client.patch(
            "/api/control-center/global-settings",
            json={"api": {"enabled": True, "host": "127.0.0.1", "port": 8090, "allowed_ips": ["127.0.0.1"]}, "llm": {"enabled": True}},
        )
        assert response.status == 200
        assert platform.global_config.saved["api"]["port"] == 8090
        assert platform.global_config.config["llm"]["api_key"] == "stored-secret"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_control_center_package_endpoints_use_real_http_requests(tmp_path, monkeypatch):
    pets_path = tmp_path / "pets"
    preview_path = pets_path / "existing" / "animations" / "idle.png"
    preview_path.parent.mkdir(parents=True)
    preview_path.write_bytes(b"preview image")
    package = SimpleNamespace(
        name="existing",
        meta=SimpleNamespace(
            author="Test",
            version="1.0.0",
            description="Preview pet",
            preview="missing-preview.png",
            regular_image="idle.png",
        ),
        actions=[SimpleNamespace(), SimpleNamespace()],
        animations_dir=preview_path.parent,
    )
    platform = _Platform()
    platform.pet_loader = SimpleNamespace(
        scan_pets=lambda: [package],
        load_pet=lambda name: package if name == "existing" else None,
    )
    server = ApiServer(platform)
    platform.api_server = server
    server._run_in_main_thread = lambda func: _resolved(func())
    monkeypatch.setattr("desktop_pet.api_server.get_pets_path", lambda: pets_path)
    client = await _client(server)
    try:
        pets = await client.get("/api/control-center/pets")
        assert pets.status == 200
        assert await pets.json() == {"pets": [{
            "name": "existing",
            "author": "Test",
            "version": "1.0.0",
            "description": "Preview pet",
            "preview_available": True,
            "action_count": 2,
        }]}

        preview = await client.get("/api/control-center/pets/existing/preview")
        assert preview.status == 200
        assert await preview.read() == b"preview image"

        create_form = FormData()
        create_form.add_field("name", "new-pet")
        create_form.add_field("author", "Creator")
        create_form.add_field("image", b"new image", filename="idle.png", content_type="image/png")
        created = await client.post("/api/control-center/pets", data=create_form)
        assert created.status == 201
        assert await created.json() == {"name": "new-pet"}
        assert (pets_path / "new-pet" / "meta.json").is_file()

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            archive.writestr("imported/meta.json", json.dumps({"name": "imported-pet", "author": "Importer", "version": "1.0.0"}))
            archive.writestr("imported/animations/idle.png", b"imported image")
        import_form = FormData()
        import_form.add_field("archive", archive_buffer.getvalue(), filename="import.zip", content_type="application/zip")
        imported = await client.post("/api/control-center/pets/import", data=import_form)
        assert imported.status == 201
        assert await imported.json() == {"name": "imported-pet", "overwritten": False}
        assert (pets_path / "imported-pet" / "animations" / "idle.png").read_bytes() == b"imported image"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_control_center_memory_endpoints_use_real_http_requests():
    platform = _Platform()
    server = ApiServer(platform)
    platform.api_server = server
    server._run_in_main_thread = lambda func: _resolved(func())
    memory_client = _MemoryClient()
    server._control_center_memory_client = lambda pet_id: memory_client
    client = await _client(server)
    try:
        memories = await client.get("/api/control-center/pets/pet-1/memories")
        assert memories.status == 200
        assert await memories.json() == {"memories": [{"id": "memory-1", "text": "existing memory"}]}

        added = await client.post("/api/control-center/pets/pet-1/memories", json={"text": " remember this "})
        assert added.status == 201
        assert await added.json() == {"id": "memory-2", "text": "remember this"}

        deleted = await client.delete("/api/control-center/pets/pet-1/memories/memory-1")
        assert deleted.status == 200
        assert await deleted.json() == {"success": True}

        cleared = await client.delete("/api/control-center/pets/pet-1/memories")
        assert cleared.status == 200
        assert await cleared.json() == {"success": True}
        assert memory_client.calls == [
            ("list", "test-agent"),
            ("add", "test-agent", "remember this"),
            ("delete", "test-agent", "memory-1"),
            ("clear", "test-agent"),
        ]
    finally:
        await client.close()


async def _resolved(value):
    return value

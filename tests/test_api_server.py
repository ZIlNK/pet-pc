"""Tests for API server utilities.

覆盖：
- 旧模式（单宠物，仅传 ``pet``）的现有测试保留不变
- 多宠物模式（platform）下：
  - 构造函数与 ``_resolve_pet`` 路由解析
  - ``_build_tools`` 包含实例管理工具及 ``pet_id`` 参数
  - ``_tool_handlers`` 注册实例管理处理器
  - HTTP 端点（``/api/pets/{pet_id}/*`` 和 ``/api/instances*``）
  - 工具处理器（``list_pets`` / ``create_pet`` / ``remove_pet`` 等）
"""
import asyncio
import socket
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from desktop_pet.api_server import ApiServer
from desktop_pet.instances_store import InstancesStoreError
from desktop_pet.pet_instance import (
    InstanceConfigError,
    InstanceConflictError,
    InstanceNotFoundError,
    PackageNotFoundError,
    PetInstanceConfig,
)


# ---------------------------------------------------------------------------
# Mock 对象
# ---------------------------------------------------------------------------
class MockAPI:
    """Mock pet.api 接口。"""

    def __init__(
        self,
        position=None,
        state="IDLE",
        mode="random",
        animations=None,
    ):
        self._position = position or {"x": 100, "y": 200, "screen": 0}
        self._state = state
        self._mode = mode
        self._animations = (
            animations if animations is not None else ["sit", "walk", "sleep"]
        )

    def get_position(self):
        return self._position

    def get_state(self):
        return self._state

    def get_mode(self):
        return self._mode

    def get_available_animations(self):
        return self._animations

    def set_mode(self, mode):
        self._mode = mode
        return True

    def move_to(self, x, y, screen=None):
        return True

    def move_by(self, dx, dy):
        return True

    def move_to_edge(self, edge, screen=None):
        return True

    def play_animation(self, name):
        return True

    def play_walk(self, direction, screen=None):
        return True


class MockPet:
    """旧模式 mock pet（与原始测试兼容）。"""

    def __init__(self):
        self.api = MockAPI()
        # Qt signal mock（emit 是同步调用）
        self.show_custom_bubble_requested = MagicMock()
        self.show_chat_bubble_requested = MagicMock()
        self.hide_chat_bubble_requested = MagicMock()
        self.screen_manager = None
        self.config_manager = None
        self.current_pet_package = None


class MockWidget:
    """多宠物模式下的 mock widget。"""

    def __init__(self, pet_id, package="default"):
        self.pet_id = pet_id
        self.package = package
        self.api = MockAPI(position={"x": 50, "y": 60, "screen": 0})
        self.show_custom_bubble_requested = MagicMock()
        self.show_chat_bubble_requested = MagicMock()
        self.hide_chat_bubble_requested = MagicMock()
        self.screen_manager = None
        self.config_manager = None
        self.current_pet_package = None


class MockPlatform:
    """PetPlatform mock，用于多宠物模式测试。

    模拟 PetPlatform 的公开 API：get_pet_widget / list_instances /
    get_instance_config / get_primary_instance / create_instance /
    destroy_instance / update_instance_config。
    """

    def __init__(self):
        self._widgets: dict[str, MockWidget] = {}
        self._configs: dict[str, PetInstanceConfig] = {}
        self.global_config = None
        self._next_id = 0

    def add_instance(
        self,
        pet_id: str,
        package: str = "default",
        primary: bool = False,
        position: dict | None = None,
    ) -> str:
        """测试辅助方法：添加一个已存在的实例。"""
        widget = MockWidget(pet_id, package)
        config = PetInstanceConfig(
            pet_id=pet_id,
            package=package,
            primary=primary,
            position=position or {"x": 100, "y": 100},
        )
        self._widgets[pet_id] = widget
        self._configs[pet_id] = config
        return pet_id

    def get_pet_widget(self, pet_id: str):
        return self._widgets.get(pet_id)

    def list_instances(self):
        return list(self._configs.values())

    def get_instance_config(self, pet_id: str):
        return self._configs.get(pet_id)

    def get_primary_instance(self):
        for cfg in self._configs.values():
            if cfg.primary:
                return cfg
        return None

    def create_instance(self, package_name, position=None, config=None):
        self._next_id += 1
        pet_id = f"newpet{self._next_id:03d}"
        return self.add_instance(
            pet_id,
            package=package_name,
            primary=False,
            position=position,
        )

    def destroy_instance(self, pet_id: str) -> bool:
        self._widgets.pop(pet_id, None)
        removed = self._configs.pop(pet_id, None) is not None
        return removed

    def update_instance_config(self, pet_id: str, updates: dict):
        cfg = self._configs.get(pet_id)
        if cfg is None:
            raise InstanceNotFoundError(f"pet instance not found: {pet_id}")
        for k, v in updates.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


def make_single_pet_platform() -> MockPlatform:
    platform = MockPlatform()
    platform.add_instance("primary1", primary=True)
    return platform


# ---------------------------------------------------------------------------
# 辅助：构造 TestClient（不调用 start() 以避免端口绑定）
# ---------------------------------------------------------------------------
async def _make_client(server: ApiServer) -> TestClient:
    """构造 in-process TestClient，跳过 start() 的端口绑定。"""
    server._app = web.Application()
    server._setup_ip_filter()
    server._setup_routes()
    server._setup_cors()
    client = TestClient(TestServer(server._app))
    await client.start_server()
    return client


@pytest.fixture
def mock_run_in_main_thread(monkeypatch):
    """将 ``_run_in_main_thread`` 替换为直接同步执行（测试无 Qt 事件循环）。"""

    async def _mock_run(self, func):
        return func()

    monkeypatch.setattr(ApiServer, "_run_in_main_thread", _mock_run)


@pytest.fixture
def platform_with_two_pets() -> MockPlatform:
    """构造带 2 个实例（1 主 1 从）的 mock platform。"""
    p = MockPlatform()
    p.add_instance("primary1", package="default", primary=True, position={"x": 100, "y": 100})
    p.add_instance("secondary2", package="cat", primary=False, position={"x": 500, "y": 300})
    return p


# ---------------------------------------------------------------------------
# 旧模式测试（保留原有断言）
# ---------------------------------------------------------------------------
def test_api_server_configure():
    """Test API server configuration."""
    server = ApiServer(make_single_pet_platform())

    server.configure("127.0.0.1", 9000)

    assert server._host == "127.0.0.1"
    assert server._port == 9000


def test_api_server_defaults_to_localhost_only():
    """API server defaults should be safe for local desktop use."""
    server = ApiServer(make_single_pet_platform())

    assert server._host == "127.0.0.1"
    assert server.get_allowed_ips() == ["127.0.0.1", "::1"]


def test_api_server_ip_whitelist():
    """Test IP whitelist management."""
    server = ApiServer(make_single_pet_platform())

    # Default whitelist
    assert "127.0.0.1" in server.get_allowed_ips()

    # Add IP
    server.add_allowed_ip("192.168.1.1")
    assert "192.168.1.1" in server.get_allowed_ips()

    # Remove IP
    server.remove_allowed_ip("192.168.1.1")
    assert "192.168.1.1" not in server.get_allowed_ips()

    # Set custom whitelist
    server.set_allowed_ips(["10.0.0.1"])
    assert server.get_allowed_ips() == ["10.0.0.1"]


def test_validate_coordinates():
    """Test coordinate validation."""
    server = ApiServer(make_single_pet_platform())

    # Valid coordinates
    assert server._validate_coordinates({"x": 100, "y": 200}) == (100, 200)
    assert server._validate_coordinates({"x": 0, "y": 0}) == (0, 0)

    # Invalid coordinates
    assert server._validate_coordinates({"x": 99999, "y": 0}) is None
    assert server._validate_coordinates({"x": -99999, "y": 0}) is None


def test_validate_delta():
    """Test movement delta validation."""
    server = ApiServer(make_single_pet_platform())

    assert server._validate_delta({"dx": 50, "dy": -30}) == (50, -30)
    assert server._validate_delta({"dx": 0, "dy": 0}) == (0, 0)


def test_is_safe_callback_url():
    """Test callback URL safety validation."""
    server = ApiServer(make_single_pet_platform())

    # Safe URLs
    assert server._is_safe_callback_url("https://example.com/callback") is True
    assert server._is_safe_callback_url("http://api.example.com/webhook") is True

    # Unsafe URLs (internal networks)
    assert server._is_safe_callback_url("http://localhost/callback") is False
    assert server._is_safe_callback_url("http://127.0.0.1/callback") is False
    assert server._is_safe_callback_url("http://192.168.1.1/callback") is False
    assert server._is_safe_callback_url("http://10.0.0.1/callback") is False

    # Invalid schemes
    assert server._is_safe_callback_url("ftp://example.com/callback") is False
    assert server._is_safe_callback_url("javascript:alert(1)") is False


def test_get_client_ip_x_forwarded_for():
    """Proxy headers are ignored unless explicitly trusted."""
    server = ApiServer(make_single_pet_platform())

    class MockRequest:
        headers = {"X-Forwarded-For": "203.0.113.1, 70.41.3.18"}
        remote = "192.168.1.1"

    ip = server._get_client_ip(MockRequest())
    assert ip == "192.168.1.1"


def test_get_client_ip_x_forwarded_for_when_trusted():
    """Trusted proxy mode uses X-Forwarded-For for deployments behind a proxy."""
    server = ApiServer(make_single_pet_platform())
    server.set_trust_proxy_headers(True)

    class MockRequest:
        headers = {"X-Forwarded-For": "203.0.113.1, 70.41.3.18"}
        remote = "192.168.1.1"

    ip = server._get_client_ip(MockRequest())
    assert ip == "203.0.113.1"


def test_get_client_ip_x_real_ip():
    """X-Real-IP is ignored unless proxy headers are trusted."""
    server = ApiServer(make_single_pet_platform())

    class MockRequest:
        headers = {"X-Real-IP": "203.0.113.2"}
        remote = "192.168.1.1"

    ip = server._get_client_ip(MockRequest())
    assert ip == "192.168.1.1"


def test_get_client_ip_x_real_ip_when_trusted():
    """Trusted proxy mode can use X-Real-IP."""
    server = ApiServer(make_single_pet_platform())
    server.set_trust_proxy_headers(True)

    class MockRequest:
        headers = {"X-Real-IP": "203.0.113.2"}
        remote = "192.168.1.1"

    ip = server._get_client_ip(MockRequest())
    assert ip == "203.0.113.2"


def test_get_client_ip_remote():
    """Test client IP extraction from remote address."""
    server = ApiServer(make_single_pet_platform())

    class MockRequest:
        headers = {}
        remote = "192.168.1.100"

    ip = server._get_client_ip(MockRequest())
    assert ip == "192.168.1.100"


# ---------------------------------------------------------------------------
# 构造函数与 _resolve_pet
# ---------------------------------------------------------------------------

def test_init_platform_mode_stores_platform():
    platform = make_single_pet_platform()
    server = ApiServer(platform)
    assert server._platform is platform

async def test_resolve_pet_path_prefix(platform_with_two_pets):
    """多宠物模式：路径前缀 /api/pets/<pet_id>/... 解析。"""
    server = ApiServer(platform=platform_with_two_pets)
    req = SimpleNamespace(match_info={"pet_id": "secondary2"}, query={})
    widget = await server._resolve_pet(req)
    assert widget is not None
    assert widget.pet_id == "secondary2"


async def test_resolve_pet_query_param(platform_with_two_pets):
    """多宠物模式：查询参数 ?pet_id=xxx 解析。"""
    server = ApiServer(platform=platform_with_two_pets)
    req = SimpleNamespace(match_info={}, query={"pet_id": "secondary2"})
    widget = await server._resolve_pet(req)
    assert widget is not None
    assert widget.pet_id == "secondary2"


async def test_resolve_pet_path_prefix_takes_priority_over_query(platform_with_two_pets):
    """路径前缀优先于查询参数。"""
    server = ApiServer(platform=platform_with_two_pets)
    req = SimpleNamespace(match_info={"pet_id": "primary1"}, query={"pet_id": "secondary2"})
    widget = await server._resolve_pet(req)
    assert widget.pet_id == "primary1"


async def test_resolve_pet_default_to_primary(platform_with_two_pets):
    """多宠物模式：无 pet_id 时返回主实例。"""
    server = ApiServer(platform=platform_with_two_pets)
    req = SimpleNamespace(match_info={}, query={})
    widget = await server._resolve_pet(req)
    assert widget is not None
    assert widget.pet_id == "primary1"


async def test_resolve_pet_not_found_returns_none(platform_with_two_pets):
    """多宠物模式：pet_id 不存在返回 None。"""
    server = ApiServer(platform=platform_with_two_pets)
    req = SimpleNamespace(match_info={"pet_id": "nonexistent"}, query={})
    assert await server._resolve_pet(req) is None


async def test_resolve_pet_no_primary_returns_none():
    """多宠物模式：无主实例时返回 None。"""
    p = MockPlatform()
    p.add_instance("only1", primary=False)
    server = ApiServer(platform=p)
    req = SimpleNamespace(match_info={}, query={})
    # 无主实例时 get_primary_instance() 返回 None
    assert await server._resolve_pet(req) is None


# ---------------------------------------------------------------------------
# _build_tools
# ---------------------------------------------------------------------------

def test_build_tools_platform_mode_includes_instance_tools(platform_with_two_pets):
    """多宠物模式下 _build_tools 包含 list_pets/create_pet/remove_pet。"""
    server = ApiServer(platform=platform_with_two_pets)
    tools = server._build_tools()
    names = [t["function"]["name"] for t in tools]
    assert "list_pets" in names
    assert "create_pet" in names
    assert "remove_pet" in names


def test_build_tools_platform_mode_has_pet_id_param(platform_with_two_pets):
    """多宠物模式下所有控制工具均有 pet_id 可选参数。"""
    server = ApiServer(platform=platform_with_two_pets)
    tools = server._build_tools()
    control_tools = {
        "get_pet_status", "set_pet_mode", "move_pet_to", "move_pet_by",
        "move_pet_to_edge", "walk_pet", "get_screens", "play_animation",
        "show_message", "show_chat_bubble", "hide_chat_bubble",
    }
    for t in tools:
        name = t["function"]["name"]
        if name in control_tools:
            props = t["function"]["parameters"].get("properties", {})
            assert "pet_id" in props, f"{name} missing pet_id param"



# ---------------------------------------------------------------------------
# _tool_handlers
# ---------------------------------------------------------------------------

def test_tool_handlers_platform_mode_registers_instance_handlers(platform_with_two_pets):
    """多宠物模式下 _tool_handlers 注册 list_pets/create_pet/remove_pet。"""
    server = ApiServer(platform=platform_with_two_pets)
    handlers = server._tool_handlers
    assert "list_pets" in handlers
    assert "create_pet" in handlers
    assert "remove_pet" in handlers


# ---------------------------------------------------------------------------
# HTTP 端点测试 - 旧模式
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# HTTP 端点测试 - 多宠物模式
# ---------------------------------------------------------------------------
async def test_http_status_without_instances_returns_404():
    server = ApiServer(MockPlatform())
    client = await _make_client(server)
    try:
        resp = await client.get("/api/status")
        assert resp.status == 404
    finally:
        await client.close()


async def test_http_status_platform_default_primary():
    """多宠物模式 GET /api/status 默认作用于主实例。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/status")
        assert resp.status == 200
        data = await resp.json()
        # MockWidget 默认 position x=50
        assert data["position"]["x"] == 50
    finally:
        await client.close()


async def test_http_status_pet_not_found_returns_404():
    """多宠物模式 GET /api/pets/nonexistent/status 返回 404。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/pets/nonexistent/status")
        assert resp.status == 404
        data = await resp.json()
        assert data["error"] == "pet not found: nonexistent"
    finally:
        await client.close()


async def test_http_status_with_pet_id_path():
    """多宠物模式 GET /api/pets/{pet_id}/status 路由到指定实例。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    p.add_instance("secondary2", package="cat")
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/pets/secondary2/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["position"]["x"] == 50
    finally:
        await client.close()


async def test_http_status_with_pet_id_query():
    """多宠物模式 GET /api/status?pet_id=xxx 路由到指定实例。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    p.add_instance("secondary2", package="cat")
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/status?pet_id=secondary2")
        assert resp.status == 200
    finally:
        await client.close()


async def test_http_move_with_pet_id():
    """多宠物模式 POST /api/pets/{pet_id}/move。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    p.add_instance("secondary2", package="cat")
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/pets/secondary2/move", json={"x": 300, "y": 400}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
    finally:
        await client.close()


async def test_http_move_pet_not_found_returns_404():
    """多宠物模式 POST /api/pets/nonexistent/move 返回 404。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/pets/nonexistent/move", json={"x": 300, "y": 400}
        )
        assert resp.status == 404
    finally:
        await client.close()


async def test_http_animations_with_pet_id():
    """多宠物模式 GET /api/pets/{pet_id}/animations。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/pets/primary1/animations")
        assert resp.status == 200
        data = await resp.json()
        assert "animations" in data
    finally:
        await client.close()


async def test_http_chat_bubble_show_with_pet_id():
    """多宠物模式 POST /api/pets/{pet_id}/chat_bubble/show。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/pets/primary1/chat_bubble/show", json={"message": "hi"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
    finally:
        await client.close()


async def test_http_chat_bubble_hide_with_pet_id():
    """多宠物模式 POST /api/pets/{pet_id}/chat_bubble/hide。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post("/api/pets/primary1/chat_bubble/hide")
        assert resp.status == 200
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# HTTP 端点测试 - 实例管理
# ---------------------------------------------------------------------------
async def test_http_instances_list_platform():
    """多宠物模式 GET /api/instances 返回所有实例。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    p.add_instance("secondary2", package="cat")
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/instances")
        assert resp.status == 200
        data = await resp.json()
        assert len(data["instances"]) == 2
        ids = [i["pet_id"] for i in data["instances"]]
        assert "primary1" in ids
        assert "secondary2" in ids
    finally:
        await client.close()


async def test_http_instances_create_platform(mock_run_in_main_thread):
    """多宠物模式 POST /api/instances 创建新实例。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/instances",
            json={"package": "default", "position": {"x": 700, "y": 800}},
        )
        assert resp.status == 201
        data = await resp.json()
        assert "pet_id" in data
        assert data["package"] == "default"
        assert data["position"] == {"x": 700, "y": 800}
    finally:
        await client.close()


async def test_http_instances_create_invalid_json():
    """多宠物模式 POST /api/instances 非法 JSON 返回 400。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/instances", data="not json", headers={"Content-Type": "application/json"}
        )
        assert resp.status == 400
    finally:
        await client.close()


async def test_http_instance_get_platform():
    """多宠物模式 GET /api/instances/{pet_id} 返回单个实例状态。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/instances/primary1")
        assert resp.status == 200
        data = await resp.json()
        assert data["pet_id"] == "primary1"
        assert "state" in data
        assert "mode" in data
    finally:
        await client.close()


async def test_http_instance_get_not_found():
    """多宠物模式 GET /api/instances/nonexistent 返回 404。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.get("/api/instances/nonexistent")
        assert resp.status == 404
    finally:
        await client.close()


async def test_http_instance_update_platform(mock_run_in_main_thread):
    """多宠物模式 PATCH /api/instances/{pet_id} 更新配置。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.patch("/api/instances/primary1", json={"size": 300})
        assert resp.status == 200
        data = await resp.json()
        assert data["size"] == 300
    finally:
        await client.close()


async def test_http_instance_update_not_found(mock_run_in_main_thread):
    """多宠物模式 PATCH /api/instances/nonexistent 返回 404。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.patch("/api/instances/nonexistent", json={"size": 300})
        assert resp.status == 404
    finally:
        await client.close()


async def test_http_instance_delete_platform(mock_run_in_main_thread):
    """多宠物模式 DELETE /api/instances/{pet_id} 销毁实例。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    p.add_instance("secondary2", package="cat")
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.delete("/api/instances/secondary2")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        # 销毁后再 GET 应 404
        resp2 = await client.get("/api/instances/secondary2")
        assert resp2.status == 404
    finally:
        await client.close()


async def test_http_instance_delete_not_found(mock_run_in_main_thread):
    """多宠物模式 DELETE /api/instances/nonexistent 返回 404。"""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.delete("/api/instances/nonexistent")
        assert resp.status == 404
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# 工具处理器测试（多宠物模式）
# ---------------------------------------------------------------------------
async def test_tool_get_pet_status_with_pet_id(platform_with_two_pets):
    """_tool_get_pet_status 支持 pet_id 参数路由。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_get_pet_status({"pet_id": "secondary2"})
    assert result["success"] is True
    assert result["data"]["position"]["x"] == 50


async def test_tool_get_pet_status_default_primary(platform_with_two_pets):
    """_tool_get_pet_status 默认作用于主实例。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_get_pet_status({})
    assert result["success"] is True


async def test_tool_get_pet_status_pet_not_found(platform_with_two_pets):
    """_tool_get_pet_status 不存在的 pet_id 返回失败。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_get_pet_status({"pet_id": "nonexistent"})
    assert result["success"] is False
    assert "not found" in result["error"]


async def test_tool_move_pet_to_with_pet_id(platform_with_two_pets):
    """_tool_move_pet_to 支持 pet_id 参数路由。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_move_pet_to({"x": 300, "y": 400, "pet_id": "secondary2"})
    assert result["success"] is True


async def test_tool_list_pets(platform_with_two_pets):
    """_tool_list_pets 返回所有实例。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_list_pets({})
    assert result["success"] is True
    assert len(result["data"]["instances"]) == 2


async def test_tool_create_pet(mock_run_in_main_thread, platform_with_two_pets):
    """_tool_create_pet 创建新实例。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_create_pet({"package": "default", "x": 100, "y": 200})
    assert result["success"] is True
    assert "pet_id" in result["data"]
    assert result["data"]["position"] == {"x": 100, "y": 200}


async def test_tool_create_pet_invalid_coords(mock_run_in_main_thread, platform_with_two_pets):
    """_tool_create_pet 非法坐标返回失败。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_create_pet({"x": "abc", "y": 200})
    assert result["success"] is False


async def test_tool_remove_pet(mock_run_in_main_thread, platform_with_two_pets):
    """_tool_remove_pet 销毁指定实例。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_remove_pet({"pet_id": "secondary2"})
    assert result["success"] is True
    assert result["data"]["pet_id"] == "secondary2"


async def test_tool_remove_pet_not_found(mock_run_in_main_thread, platform_with_two_pets):
    """_tool_remove_pet 不存在的 pet_id 返回失败。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_remove_pet({"pet_id": "nonexistent"})
    assert result["success"] is False


async def test_tool_remove_pet_no_pet_id(mock_run_in_main_thread, platform_with_two_pets):
    """_tool_remove_pet 缺少 pet_id 返回失败。"""
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_remove_pet({})
    assert result["success"] is False
    assert "pet_id" in result["error"]



# ---------------------------------------------------------------------------
# _get_llm_config 多宠物模式
# ---------------------------------------------------------------------------
def test_get_llm_config_platform_uses_global_config():
    """多宠物模式下 _get_llm_config 优先使用 platform.global_config。"""
    p = MockPlatform()
    # 构造 mock global_config
    llm = MagicMock()
    llm.enabled = True
    llm.api_key = "sk-test"
    llm.base_url = "https://api.example.com/v1"
    llm.model = "gpt-4o"
    llm.system_prompt = "you are a pet"
    llm.max_history = 10
    p.global_config = MagicMock()
    p.global_config.llm = llm

    server = ApiServer(platform=p)
    config = server._get_llm_config()
    assert config["enabled"] is True
    assert config["api_key"] == "sk-test"
    assert config["model"] == "gpt-4o"



def test_get_llm_config_no_config_returns_empty():
    """无任何配置时返回空 dict。"""
    server = ApiServer(make_single_pet_platform())
    assert server._get_llm_config() == {}


# ---------------------------------------------------------------------------
# OpenClaw http-channel 接收端测试
# ---------------------------------------------------------------------------
async def test_openclaw_reply_without_to_falls_back_to_primary():
    platform = make_single_pet_platform()
    server = ApiServer(platform)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply",
            json={
                "channel": "pet-bubble",
                "accountId": "default",
                "text": "hello",
                "timestamp": 1751487600000,
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["received"] is True
        platform.get_pet_widget("primary1").show_chat_bubble_requested.emit.assert_called_once_with(
            "hello"
        )
    finally:
        await client.close()

async def test_openclaw_reply_platform_routes_by_to():
    """A non-empty to value is the exact target pet_id."""
    p = MockPlatform()
    p.add_instance("primary1", primary=True)
    p.add_instance("petB")
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply",
            json={"to": "petB", "text": "hi from agent"},
        )
        assert resp.status == 200
        p.get_pet_widget("primary1").show_chat_bubble_requested.emit.assert_not_called()
        p.get_pet_widget("petB").show_chat_bubble_requested.emit.assert_called_once_with(
            "hi from agent"
        )
    finally:
        await client.close()


async def test_openclaw_reply_unknown_to_returns_404_without_fallback():
    p = make_single_pet_platform()
    server = ApiServer(platform=p)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply", json={"to": "missing", "text": "hello"}
        )
        assert resp.status == 404
        p.get_pet_widget("primary1").show_chat_bubble_requested.emit.assert_not_called()
    finally:
        await client.close()

async def test_openclaw_reply_empty_to_does_not_fall_back():
    platform = make_single_pet_platform()
    server = ApiServer(platform=platform)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply", json={"to": "   ", "text": "hello"}
        )
        assert resp.status == 404
        platform.get_pet_widget(
            "primary1"
        ).show_chat_bubble_requested.emit.assert_not_called()
    finally:
        await client.close()


async def test_openclaw_reply_null_to_is_invalid():
    platform = make_single_pet_platform()
    server = ApiServer(platform=platform)
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply", json={"to": None, "text": "hello"}
        )
        assert resp.status == 400
        platform.get_pet_widget(
            "primary1"
        ).show_chat_bubble_requested.emit.assert_not_called()
    finally:
        await client.close()


async def test_openclaw_reply_wrong_method():
    """GET /api/openclaw/reply → 405。"""
    server = ApiServer(make_single_pet_platform())
    client = await _make_client(server)
    try:
        resp = await client.get("/api/openclaw/reply")
        assert resp.status == 405
    finally:
        await client.close()


async def test_openclaw_reply_invalid_body_missing_text():
    """缺 text 字段 → 400。"""
    server = ApiServer(make_single_pet_platform())
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply",
            json={"to": "boss"},
        )
        assert resp.status == 400
    finally:
        await client.close()


async def test_openclaw_reply_invalid_json():
    """非法 JSON → 400。"""
    server = ApiServer(make_single_pet_platform())
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
    finally:
        await client.close()


async def test_openclaw_reply_secret_token_mismatch():
    """配置 secret_token 后 header 不匹配 → 401。"""
    server = ApiServer(make_single_pet_platform())
    server.set_openclaw_config("", "", "my-secret")
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply",
            json={"to": "boss", "text": "hi"},
            headers={"X-HTTP-Channel-Secret": "wrong"},
        )
        assert resp.status == 401
    finally:
        await client.close()


async def test_openclaw_reply_secret_token_correct_passes():
    """配置 secret_token 且 header 匹配 → 200。"""
    server = ApiServer(make_single_pet_platform())
    server.set_openclaw_config("", "", "my-secret")
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply",
            json={"text": "hi"},
            headers={"X-HTTP-Channel-Secret": "my-secret"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["received"] is True
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# _forward_to_openclaw 新协议格式测试
# ---------------------------------------------------------------------------
async def test_forward_to_openclaw_new_format(monkeypatch):
    """_forward_to_openclaw 转发 body 为 {from, text, chatType} 格式。"""
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"dispatched": True}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["body"] = json
            captured["headers"] = headers
            return FakeResp()

    import sys
    import types

    fake_httpx = types.ModuleType("httpx")
    fake_httpx.AsyncClient = FakeClient
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    server = ApiServer(make_single_pet_platform())
    server.set_openclaw_config("http://localhost:18789/webhooks/http-channel", "boss")
    await server._forward_to_openclaw("hello", "2026-01-01T00:00:00")

    assert captured["url"] == "http://localhost:18789/webhooks/http-channel"
    assert captured["body"] == {"from": "boss", "text": "hello", "chatType": "direct"}


# ---------------------------------------------------------------------------
# Background lifecycle and strict error semantics
# ---------------------------------------------------------------------------
def test_background_lifecycle_is_idempotent_and_clears_references():
    server = ApiServer(make_single_pet_platform())
    server.configure("127.0.0.1", 0)

    assert server.start_background(timeout=2) is True
    assert server.start_background(timeout=2) is True
    assert server.is_running is True

    assert server.stop_background(timeout=2) is True
    assert server.stop_background(timeout=2) is True
    assert server.is_running is False
    assert server._thread is None
    assert server._loop is None
    assert server._runner is None
    assert server._site is None


def test_background_start_bind_failure_has_no_residual_thread():
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    server = ApiServer(make_single_pet_platform())
    server.configure("127.0.0.1", port)
    try:
        assert server.start_background(timeout=2) is False
        deadline = time.monotonic() + 2
        while server._thread is not None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.last_error is not None
        assert server.is_running is False
        assert server._thread is None
        assert server._loop is None
        assert server._runner is None
        assert server._site is None
    finally:
        blocker.close()


def test_background_start_timeout_eventually_cleans_up(monkeypatch):
    server = ApiServer(make_single_pet_platform())

    async def slow_start():
        await asyncio.sleep(0.2)
        return True

    monkeypatch.setattr(server, "start", slow_start)
    assert server.start_background(timeout=0.02) is False
    deadline = time.monotonic() + 2
    while server._thread is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert isinstance(server.last_error, TimeoutError)
    assert server.is_running is False
    assert server._thread is None
    assert server._loop is None


async def test_chat_bubble_rejects_non_object_json():
    server = ApiServer(make_single_pet_platform())
    client = await _make_client(server)
    try:
        resp = await client.post("/api/chat_bubble/show", json=["hello"])
        assert resp.status == 400
    finally:
        await client.close()


async def test_tools_call_rejects_non_object_body_and_arguments():
    server = ApiServer(make_single_pet_platform())
    client = await _make_client(server)
    try:
        resp = await client.post("/api/tools/call", json=["list_pets"])
        assert resp.status == 400
        resp = await client.post(
            "/api/tools/call",
            json={"name": "list_pets", "arguments": []},
        )
        assert resp.status == 400
    finally:
        await client.close()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (InstanceConfigError("bad config"), 400),
        (InstanceNotFoundError("missing"), 404),
        (PackageNotFoundError("missing package"), 404),
        (InstanceConflictError("conflict"), 409),
        (InstancesStoreError("disk failed"), 500),
        (RuntimeError("unexpected"), 500),
    ],
)
async def test_tools_call_maps_typed_errors(error, expected_status):
    class ErrorServer(ApiServer):
        @property
        def _tool_handlers(self):
            async def fail(_arguments):
                raise error
            return {"fail": fail}

    server = ErrorServer(make_single_pet_platform())
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/tools/call",
            json={"name": "fail", "arguments": {}},
        )
        assert resp.status == expected_status
        data = await resp.json()
        assert data["success"] is False
        assert data["error_type"] == type(error).__name__
    finally:
        await client.close()


async def test_forward_to_openclaw_independent_agent_hook(monkeypatch, platform_with_two_pets):
    captured = {}

    class FakeResp:
        status_code = 202
        text = "accepted"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured.update(url=url, body=json, headers=headers)
            return FakeResp()

    import sys
    import types
    fake_httpx = types.ModuleType("httpx")
    fake_httpx.AsyncClient = FakeClient
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    server = ApiServer(platform=platform_with_two_pets)
    server.set_openclaw_config(
        "", "", "callback-secret",
        hooks_url="http://127.0.0.1:18789/hooks/agent",
        hooks_token="hooks-token",
    )
    agent = {
        "enabled": True,
        "provider": "openclaw",
        "agent_id": "healer-cat",
        "session_key": "hook:pet:secondary2",
        "reply_length": "short",
        "initiative": "low",
    }
    await server._forward_to_openclaw("hello", "ignored", "secondary2", agent)

    assert captured["url"].endswith("/hooks/agent")
    assert captured["headers"]["Authorization"] == "Bearer hooks-token"
    assert captured["body"]["agentId"] == "healer-cat"
    assert captured["body"]["sessionKey"] == "hook:pet:secondary2"
    assert captured["body"]["channel"] == "pet-bubble"
    assert captured["body"]["to"] == "secondary2"
    runtime_message = captured["body"]["message"]
    assert "exactly one final JSON object" in runtime_message
    assert '"duration":15000' in runtime_message
    assert "do not call respond_as_pet" in runtime_message
    assert "do not include pet_id" in runtime_message.lower()
    assert "any desktop-pet MCP tool" in runtime_message


async def test_forward_to_openclaw_independent_agent_channel(
    monkeypatch, platform_with_two_pets
):
    captured = {"calls": 0}

    class FakeResp:
        status_code = 202
        text = "accepted"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured["calls"] += 1
            captured.update(url=url, body=json, headers=headers)
            return FakeResp()

    import sys
    import types
    fake_httpx = types.ModuleType("httpx")
    fake_httpx.AsyncClient = FakeClient
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    server = ApiServer(platform=platform_with_two_pets)
    server.set_openclaw_config(
        "",
        "",
        "channel-secret",
        hooks_url="http://127.0.0.1:18789/hooks/agent",
        hooks_token="hooks-token",
        channel_url="http://127.0.0.1:18789/pet-bubble-webhook",
        agent_transport="channel",
    )
    agent = {
        "enabled": True,
        "provider": "openclaw",
        "agent_id": "healer-cat",
        "session_key": "hook:pet:secondary2",
        "reply_length": "short",
        "initiative": "high",
    }
    await server._forward_to_openclaw(
        "hello", "2026-07-24T12:30:25", "secondary2", agent
    )

    assert captured["calls"] == 1
    assert captured["url"].endswith("/pet-bubble-webhook")
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "X-Pet-Bubble-Secret": "channel-secret",
    }
    assert captured["body"] == {
        "from": "secondary2",
        "agentId": "healer-cat",
        "text": "hello",
        "chatType": "direct",
        "timestamp": "2026-07-24T12:30:25",
        "runtime": {"replyLength": "short", "initiative": "high"},
    }
    assert "sessionKey" not in captured["body"]
    assert "Authorization" not in captured["headers"]


def test_add_user_message_records_pet_and_agent(platform_with_two_pets):
    config = platform_with_two_pets.get_instance_config("secondary2")
    config.agent = {"enabled": True, "agent_id": "healer-cat"}
    server = ApiServer(platform=platform_with_two_pets)

    server.add_user_message("hello", pet_id="secondary2")

    queued = server._user_messages[-1]
    assert queued["text"] == "hello"
    assert queued["pet_id"] == "secondary2"
    assert queued["agent_id"] == "healer-cat"


async def test_respond_as_pet_plays_animation_and_shows_text(
    mock_run_in_main_thread, platform_with_two_pets
):
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_respond_as_pet({
        "pet_id": "secondary2", "text": " good job ", "animation": "sit"
    })

    assert result == {
        "success": True,
        "data": {
            "pet_id": "secondary2",
            "text": "good job",
            "duration": 15000,
            "requested_animation": "sit",
            "played_animation": "sit",
            "fallback": None,
        },
    }
    widget = platform_with_two_pets.get_pet_widget("secondary2")
    widget.show_custom_bubble_requested.emit.assert_called_once_with("good job", 15000)


async def test_respond_as_pet_missing_animation_falls_back_to_text(
    mock_run_in_main_thread, platform_with_two_pets
):
    server = ApiServer(platform=platform_with_two_pets)
    result = await server._tool_respond_as_pet({
        "pet_id": "secondary2",
        "text": "hello",
        "animation": "missing",
        "duration": 0,
    })

    assert result["success"] is True
    assert result["data"]["played_animation"] is None
    assert result["data"]["fallback"] == "text_only"
    platform_with_two_pets.get_pet_widget(
        "secondary2"
    ).show_custom_bubble_requested.emit.assert_called_once_with("hello", 0)


@pytest.mark.parametrize(
    "args,error",
    [
        ({"pet_id": "missing", "text": "hello"}, "not found"),
        ({"pet_id": "secondary2", "text": "   "}, "text"),
        ({"pet_id": "secondary2", "text": "hello", "duration": -1}, "duration"),
        ({"pet_id": "secondary2", "text": "hello", "duration": True}, "duration"),
    ],
)
async def test_respond_as_pet_rejects_invalid_arguments(
    mock_run_in_main_thread, platform_with_two_pets, args, error
):
    result = await ApiServer(platform=platform_with_two_pets)._tool_respond_as_pet(args)
    assert result["success"] is False
    assert error in result["error"]


def test_tools_expose_respond_as_pet(platform_with_two_pets):
    tools = ApiServer(platform=platform_with_two_pets)._build_tools()
    definition = next(
        item["function"] for item in tools
        if item["function"]["name"] == "respond_as_pet"
    )
    assert definition["parameters"]["required"] == ["pet_id", "text"]
    assert definition["parameters"]["properties"]["duration"]["default"] == 15000


async def test_openclaw_reply_suppresses_recent_respond_as_pet_duplicate(
    mock_run_in_main_thread, platform_with_two_pets
):
    server = ApiServer(platform=platform_with_two_pets)
    await server._tool_respond_as_pet({"pet_id": "secondary2", "text": "same reply"})
    widget = platform_with_two_pets.get_pet_widget("secondary2")
    client = await _make_client(server)
    try:
        resp = await client.post(
            "/api/openclaw/reply", json={"to": "secondary2", "text": "same   reply"}
        )
        assert resp.status == 200
        assert await resp.json() == {"received": True, "suppressed": True}
        widget.show_chat_bubble_requested.emit.assert_not_called()
    finally:
        await client.close()


async def test_openclaw_reply_fingerprint_expires(monkeypatch, platform_with_two_pets):
    server = ApiServer(platform=platform_with_two_pets)
    current_time = [10.0]
    monkeypatch.setattr(
        "desktop_pet.api_server.time.monotonic", lambda: current_time[0]
    )
    server._record_response_fingerprint("secondary2", "reply")
    current_time[0] = 21.0
    assert server._consume_response_fingerprint("secondary2", "reply") is False

"""多实例端到端集成测试。

验证平台化重构后的关键端到端场景：
- SubTask 12.1: 多实例 API 分别控制互不干扰
- SubTask 12.2: 向后兼容（旧 API 作用于主实例）
- SubTask 12.3: 重启恢复（instances.json 持久化）
- SubTask 12.4: MCP 工具动态发现（pet_id 参数注入）

测试策略：
- 使用真实 PetPlatform + mock widget_factory（参考 test_pet_platform.py）
- 使用 aiohttp TestClient 进行 HTTP 端到端验证（参考 test_api_server.py）
- 用 tmp_path 隔离 config_dir，避免污染真实配置
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from desktop_pet.api_server import ApiServer
from desktop_pet.pet_instance import PetInstanceConfig
from desktop_pet.pet_loader import PetAction, PetMeta, PetPackage
from desktop_pet.pet_platform import PetPlatform


# ---------------------------------------------------------------------------
# Fixtures：与 test_pet_platform.py 保持一致的样本数据构造
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_meta() -> PetMeta:
    """构造测试用 PetMeta。"""
    return PetMeta(
        name="default",
        author="tester",
        version="1.0.0",
        description="test pet",
        regular_image="idle.png",
        flying_image="flying.png",
        rest_animation="hui.webp",
    )


@pytest.fixture
def sample_actions() -> list[PetAction]:
    """构造测试用 PetAction 列表。"""
    return [
        PetAction(
            name="sit",
            type="animation",
            weight=1,
            animation_files=["animations/sit/sit.gif"],
            enabled=True,
            config={"min_distance": 30, "max_distance": 100},
            zone_actions={"head": "pat"},
        ),
        PetAction(
            name="walk",
            type="movement",
            weight=2,
            animation_files=[],
            enabled=False,
            config={},
            zone_actions={},
        ),
    ]


@pytest.fixture
def sample_package(
    sample_meta: PetMeta, sample_actions: list[PetAction], tmp_path: Path
) -> PetPackage:
    """构造测试用 PetPackage。"""
    return PetPackage(
        name="default",
        path=tmp_path / "default",
        meta=sample_meta,
        actions=sample_actions,
        animations_dir=tmp_path / "default" / "animations",
        config_dir=tmp_path / "default" / "config",
    )


@pytest.fixture
def patched_pet_loader(sample_package: PetPackage):
    """Patch PetLoader 在 pet_platform 模块中的引用，返回 mock 实例。

    mock 实例的 scan_pets() 返回 [sample_package]，load_pet() 返回 sample_package。
    """
    with patch("desktop_pet.pet_platform.PetLoader") as MockLoader:
        instance = MockLoader.return_value
        instance.scan_pets.return_value = [sample_package]
        instance.load_pet.return_value = sample_package
        yield instance


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """创建空的临时配置目录，用于隔离 instances.json 等持久化文件。"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


# ---------------------------------------------------------------------------
# Mock widget：记录 move_to 调用，用于端到端断言
# ---------------------------------------------------------------------------
class _MockAPI:
    """记录 move_to 调用的 mock API。

    与 test_api_server.py 的 MockAPI 不同，本类会真实记录并更新位置，
    以便验证不同实例的移动互不干扰。
    """

    def __init__(self, position=None, state="IDLE", mode="random", animations=None):
        self._position = position or {"x": 100, "y": 200, "screen": 0}
        self._state = state
        self._mode = mode
        self._animations = (
            animations if animations is not None else ["sit", "walk", "sleep"]
        )
        # 记录所有 move_to 调用 (x, y, screen)
        self.move_to_calls: list[tuple] = []

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
        # 真实更新位置，便于验证最终状态
        self._position = {
            "x": x,
            "y": y,
            "screen": screen if screen is not None else self._position.get("screen", 0),
        }
        self.move_to_calls.append((x, y, screen))
        return True

    def move_by(self, dx, dy):
        return True

    def move_to_edge(self, edge, screen=None):
        return True

    def play_animation(self, name):
        return True

    def play_walk(self, direction, screen=None):
        return True


class _MockWidget:
    """集成测试用 mock widget，记录 move_to 调用并暴露 ApiServer 所需的全部接口。"""

    def __init__(self, pet_id: str, package: str = "default"):
        self.pet_id = pet_id
        self.package = package
        self.api = _MockAPI()
        # Qt signal mocks（ApiServer 通过 emit 投递消息）
        self.show_custom_bubble_requested = MagicMock()
        self.show_chat_bubble_requested = MagicMock()
        self.hide_chat_bubble_requested = MagicMock()
        self.screen_manager = None
        self.config_manager = None
        self.current_pet_package = None

    def close(self):
        """模拟 widget 关闭。"""

    def on_config_updated(self, config):
        """模拟 widget 配置更新通知。"""


@pytest.fixture
def mock_widget_factory():
    """返回 mock widget 工厂；创建的 widget 收集在 factory.created 列表中。

    每个 widget 的 api.move_to_calls 记录所有移动调用，用于断言不同实例互不干扰。
    """
    created: list[_MockWidget] = []

    def factory(
        pet_id: str, config: PetInstanceConfig, package: PetPackage
    ) -> _MockWidget:
        widget = _MockWidget(pet_id, package.name)
        created.append(widget)
        return widget

    factory.created = created  # type: ignore[attr-defined]
    return factory


# ---------------------------------------------------------------------------
# 辅助：构造 in-process TestClient（跳过 start() 端口绑定）
# ---------------------------------------------------------------------------
async def _make_client(server: ApiServer) -> TestClient:
    """构造 aiohttp TestClient，跳过 start() 的端口绑定。

    参考 test_api_server.py 的 _make_client 实现。
    """
    server._app = web.Application()
    server._setup_ip_filter()
    server._setup_routes()
    server._setup_cors()
    client = TestClient(TestServer(server._app))
    await client.start_server()
    return client


# ===========================================================================
# SubTask 12.1: 多实例 API 分别控制互不干扰
# ===========================================================================
class TestMultiInstanceApiIsolation:
    """验证多实例通过 /api/pets/{pet_id}/move 路径分别控制，互不干扰。"""

    async def test_move_each_pet_independently(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
    ):
        """通过 /api/pets/{pet_id}/move 分别移动两个实例到不同位置。

        验证：
        - 两次 API 调用均成功
        - 两个 widget 的 move_to 调用参数互不干扰
        - 最终位置反映各自的移动目标
        """
        # 1. 创建平台与 2 个实例
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id_1 = platform.create_instance("default", position={"x": 10, "y": 10})
        pet_id_2 = platform.create_instance("default", position={"x": 20, "y": 20})

        widget_1 = platform.get_pet_widget(pet_id_1)
        widget_2 = platform.get_pet_widget(pet_id_2)
        assert widget_1 is not None
        assert widget_2 is not None

        # 2. 通过 API 路径前缀分别移动到不同位置
        server = ApiServer(platform=platform)
        client = await _make_client(server)
        try:
            resp1 = await client.post(
                f"/api/pets/{pet_id_1}/move", json={"x": 300, "y": 400}
            )
            assert resp1.status == 200
            data1 = await resp1.json()
            assert data1["success"] is True

            resp2 = await client.post(
                f"/api/pets/{pet_id_2}/move", json={"x": 500, "y": 600}
            )
            assert resp2.status == 200
            data2 = await resp2.json()
            assert data2["success"] is True
        finally:
            await client.close()

        # 3. 验证两个 widget 的 move_to 调用互不干扰
        assert widget_1.api.move_to_calls == [(300, 400, None)]
        assert widget_2.api.move_to_calls == [(500, 600, None)]

        # 4. 验证最终位置互不污染
        assert widget_1.api.get_position()["x"] == 300
        assert widget_1.api.get_position()["y"] == 400
        assert widget_2.api.get_position()["x"] == 500
        assert widget_2.api.get_position()["y"] == 600

    async def test_instances_list_returns_two(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
    ):
        """GET /api/instances 返回两个实例，且 pet_id 与创建时一致。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id_1 = platform.create_instance("default")
        pet_id_2 = platform.create_instance("default")

        server = ApiServer(platform=platform)
        client = await _make_client(server)
        try:
            resp = await client.get("/api/instances")
            assert resp.status == 200
            data = await resp.json()
            assert len(data["instances"]) == 2
            ids = {i["pet_id"] for i in data["instances"]}
            assert ids == {pet_id_1, pet_id_2}
        finally:
            await client.close()


# ===========================================================================
# SubTask 12.2: 向后兼容（旧 API 作用于主实例）
# ===========================================================================
class TestBackwardCompatibility:
    """验证旧版 /api/move（无 pet_id）仅作用于主实例。"""

    async def test_legacy_move_affects_only_primary(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
        sample_package: PetPackage,
    ):
        """旧版 /api/move（无 pet_id 路径前缀、无查询参数）仅移动 primary 实例。

        验证：
        - primary 实例的 widget 被 move_to 调用
        - 非 primary 实例的 widget 未被 move_to 调用
        """
        # 1. 创建平台
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )

        # 2. 创建 1 个 primary 实例 + 1 个非 primary 实例
        primary_config = PetInstanceConfig.from_package_defaults(
            sample_package, pet_id="pri00001"
        )
        primary_config.primary = True
        pet_id_primary = platform.create_instance("default", config=primary_config)

        pet_id_secondary = platform.create_instance("default")

        widget_primary = platform.get_pet_widget(pet_id_primary)
        widget_secondary = platform.get_pet_widget(pet_id_secondary)
        assert widget_primary is not None
        assert widget_secondary is not None

        # 3. 调用旧版 /api/move（无 pet_id 路径前缀、无查询参数）
        server = ApiServer(platform=platform)
        client = await _make_client(server)
        try:
            resp = await client.post("/api/move", json={"x": 700, "y": 800})
            assert resp.status == 200
            data = await resp.json()
            assert data["success"] is True
        finally:
            await client.close()

        # 4. 验证只有 primary 实例的 widget 被移动
        assert widget_primary.api.move_to_calls == [(700, 800, None)]
        assert widget_secondary.api.move_to_calls == []


# ===========================================================================
# SubTask 12.3: 重启恢复
# ===========================================================================
class TestRestartRecovery:
    """验证 instances.json 持久化与重启后完整恢复。"""

    def test_restart_recovers_instances(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
    ):
        """销毁平台后重建，实例列表完整恢复，widget_factory 被调用 2 次。

        验证：
        - instances.json 已持久化到磁盘
        - 重建平台并 start() 后，list_instances() 返回的实例列表与原配置一致
        - widget_factory 在 start() 期间被调用 2 次（每个实例一次）
        """
        # 1. 第一个平台：创建 2 个实例并持久化
        platform1 = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id_1 = platform1.create_instance(
            "default", position={"x": 100, "y": 100}
        )
        pet_id_2 = platform1.create_instance(
            "default", position={"x": 200, "y": 200}
        )

        # 记录原始配置用于后续比对
        original_configs = {c.pet_id: c for c in platform1.list_instances()}
        assert len(original_configs) == 2

        # 验证 instances.json 已写入磁盘
        instances_path = temp_config_dir / "instances.json"
        assert instances_path.exists()

        # 2. 销毁第一个平台（模拟重启）
        del platform1

        # 3. 重新创建平台并 start()
        # 使用独立的 widget_factory 计数器，验证 start() 期间被调用次数
        restart_created: list[_MockWidget] = []

        def restart_factory(
            pet_id: str, config: PetInstanceConfig, package: PetPackage
        ) -> _MockWidget:
            widget = _MockWidget(pet_id, package.name)
            restart_created.append(widget)
            return widget

        platform2 = PetPlatform(
            config_dir=temp_config_dir, widget_factory=restart_factory
        )
        platform2.start()

        # 4. 验证实例列表完整恢复
        recovered = platform2.list_instances()
        assert len(recovered) == 2
        recovered_ids = {c.pet_id for c in recovered}
        assert recovered_ids == {pet_id_1, pet_id_2}

        # 5. 验证配置完整恢复（位置等关键字段）
        recovered_configs = {c.pet_id: c for c in recovered}
        assert recovered_configs[pet_id_1].position == {"x": 100, "y": 100}
        assert recovered_configs[pet_id_2].position == {"x": 200, "y": 200}
        assert recovered_configs[pet_id_1].package == "default"
        assert recovered_configs[pet_id_2].package == "default"

        # 6. 验证 widget_factory 在 start() 期间被调用 2 次
        assert len(restart_created) == 2

        # 7. 验证 widget 已正确创建并绑定到对应 pet_id
        assert platform2.get_pet_widget(pet_id_1) is not None
        assert platform2.get_pet_widget(pet_id_2) is not None


# ===========================================================================
# SubTask 12.4: MCP 工具动态发现
# ===========================================================================
class TestMcpToolDiscovery:
    """验证多宠物模式下 _build_tools 包含实例管理工具与 pet_id 参数。"""

    def test_build_tools_includes_instance_management_tools(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
    ):
        """_build_tools 包含 list_pets / create_pet / remove_pet / get_pet_status。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        platform.create_instance("default")

        server = ApiServer(platform=platform)
        tools = server._build_tools()
        names = [t["function"]["name"] for t in tools]

        # 验证实例管理工具存在
        assert "list_pets" in names
        assert "create_pet" in names
        assert "remove_pet" in names
        assert "get_pet_status" in names

    def test_build_tools_control_tools_have_pet_id_param(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
    ):
        """控制工具（move_pet_to / play_animation）的 parameters 包含 pet_id 参数。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        platform.create_instance("default")

        server = ApiServer(platform=platform)
        tools = server._build_tools()

        # 按 function.name 索引
        tools_by_name = {t["function"]["name"]: t["function"] for t in tools}

        # move_pet_to 应有 pet_id 参数
        assert "move_pet_to" in tools_by_name
        move_props = tools_by_name["move_pet_to"]["parameters"].get("properties", {})
        assert "pet_id" in move_props

        # play_animation 应有 pet_id 参数
        assert "play_animation" in tools_by_name
        anim_props = tools_by_name["play_animation"]["parameters"].get("properties", {})
        assert "pet_id" in anim_props

    async def test_http_tools_endpoint_returns_pet_id_params(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
    ):
        """GET /api/tools 返回的工具列表包含实例管理工具与 pet_id 参数。

        端到端验证：通过 HTTP 端点访问 _build_tools 的输出。
        """
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        platform.create_instance("default")

        server = ApiServer(platform=platform)
        client = await _make_client(server)
        try:
            resp = await client.get("/api/tools")
            assert resp.status == 200
            data = await resp.json()
            tools = data["tools"]
            names = [t["function"]["name"] for t in tools]

            # 验证实例管理工具存在
            assert "list_pets" in names
            assert "create_pet" in names
            assert "remove_pet" in names
            assert "get_pet_status" in names

            # 验证 move_pet_to 包含 pet_id 参数
            move_tool = next(
                t["function"] for t in tools if t["function"]["name"] == "move_pet_to"
            )
            assert "pet_id" in move_tool["parameters"].get("properties", {})

            # 验证 play_animation 包含 pet_id 参数
            anim_tool = next(
                t["function"] for t in tools if t["function"]["name"] == "play_animation"
            )
            assert "pet_id" in anim_tool["parameters"].get("properties", {})
        finally:
            await client.close()

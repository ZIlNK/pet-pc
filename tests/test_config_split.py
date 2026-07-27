"""Tests for GlobalConfigManager and InstancesStore (config split).

覆盖：
- GlobalConfigManager 仅含全局字段（不含 actions/rest_reminder 等实例字段）
- GlobalConfigManager 正确加载 api/tray/display 等全局配置
- InstancesStore 增删改查（add/get/update/remove/list/get_primary）
- InstancesStore 文件不存在时返回空列表
- InstancesStore 往返序列化一致
- ensure_initial_instance 迁移逻辑（有实例时不迁移、无实例有包时创建 primary）
"""
import json
from pathlib import Path

import pytest

from desktop_pet.config_manager import GlobalConfigManager
from desktop_pet.instances_store import InstancesStore, InstancesStoreError
from desktop_pet.pet_instance import PetInstanceConfig
from desktop_pet.pet_loader import PetAction, PetMeta, PetPackage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """创建包含全局 + 实例级字段的临时配置目录。"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    default_config = {
        # 全局字段
        "api": {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 8080,
            "allowed_ips": ["127.0.0.1", "::1"],
        },
        "startup": {"enabled": False, "start_hidden": False},
        "tray": {"enabled": True, "minimize_to_tray": True},
        "display": {
            "cross_screen_drag": True,
            "cross_screen_random_walk": True,
            "cross_screen_walk_probability": 0.3,
            "remember_last_screen": True,
            "default_screen_index": None,
            "last_screen_index": None,
        },
        "llm": {
            "enabled": False,
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "system_prompt": "你是一个桌面宠物助手。",
            "max_history": 20,
        },
        "mcp": {
            "enabled": True,
            "api_base": "http://127.0.0.1:8080/api",
            "openclaw_webhook_url": "http://127.0.0.1:18789/pet-bubble-webhook",
            "openclaw_peer": "boss",
        },
        # 实例级字段（应被 GlobalConfigManager 排除）
        "actions": {"sit": {"enabled": True, "weight": 1}},
        "rest_reminder": {"enabled": True, "interval_minutes": 55},
        "movement": {"random_interval_min_ms": 3000},
        "behavior": {"quiet_mode_enabled": False},
        "motion_mode": {"default_mode": "random"},
        "click_detection": {"enabled": False},
        "pet": {"size": 200},
    }

    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump(default_config, f, ensure_ascii=False, indent=2)

    return config_dir


@pytest.fixture
def sample_meta() -> PetMeta:
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
    ]


@pytest.fixture
def sample_package(
    sample_meta: PetMeta, sample_actions: list[PetAction], tmp_path: Path
) -> PetPackage:
    return PetPackage(
        name="default",
        path=tmp_path,
        meta=sample_meta,
        actions=sample_actions,
        animations_dir=tmp_path / "animations",
        config_dir=tmp_path / "config",
    )


# ---------------------------------------------------------------------------
# GlobalConfigManager
# ---------------------------------------------------------------------------
class TestGlobalConfigManager:
    def test_config_only_contains_global_fields(self, temp_config_dir: Path):
        """GlobalConfigManager.config 应仅含全局字段，不含实例级字段。"""
        mgr = GlobalConfigManager(config_dir=temp_config_dir)

        for key in ("api", "tray", "startup", "display", "mcp", "llm"):
            assert key in mgr.config, f"全局字段 {key} 应存在"

        # 实例级字段不应存在
        for key in (
            "actions",
            "rest_reminder",
            "movement",
            "behavior",
            "motion_mode",
            "click_detection",
            "pet",
        ):
            assert key not in mgr.config, f"实例级字段 {key} 不应存在"

    def test_loads_global_config_values(self, temp_config_dir: Path):
        """正确加载 api/tray/display 等全局配置。"""
        mgr = GlobalConfigManager(config_dir=temp_config_dir)

        # api / mcp 为原始 dict
        assert mgr.api["host"] == "127.0.0.1"
        assert mgr.api["port"] == 8080
        assert mgr.api["allowed_ips"] == ["127.0.0.1", "::1"]
        assert mgr.mcp["api_base"] == "http://127.0.0.1:8080/api"
        assert mgr.mcp["openclaw_peer"] == "boss"

        # dataclass 属性
        assert mgr.tray.enabled is True
        assert mgr.tray.minimize_to_tray is True
        assert mgr.startup.enabled is False
        assert mgr.startup.start_hidden is False
        assert mgr.display.cross_screen_drag is True
        assert mgr.display.cross_screen_walk_probability == pytest.approx(0.3)
        assert mgr.display.default_screen_index is None
        assert mgr.llm.model == "gpt-4o-mini"
        assert mgr.llm.enabled is False

    def test_user_config_overrides_default(self, temp_config_dir: Path):
        """user_config 应覆盖 default_config 的全局字段。"""
        user_config = {
            "api": {"port": 9090},
            "tray": {"minimize_to_tray": False},
            "display": {"last_screen_index": 1},
        }
        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            json.dump(user_config, f, ensure_ascii=False, indent=2)

        mgr = GlobalConfigManager(config_dir=temp_config_dir)

        assert mgr.api["port"] == 9090  # overridden
        assert mgr.api["host"] == "127.0.0.1"  # 保留默认
        assert mgr.tray.minimize_to_tray is False  # overridden
        assert mgr.tray.enabled is True  # 保留默认
        assert mgr.display.last_screen_index == 1  # overridden

    def test_save_global_settings_preserves_other_sections(self, temp_config_dir: Path):
        """保存全局设置时应保留 user_config.json 中已有的实例级字段。"""
        existing_user_config = {
            "actions": {"sit": {"enabled": False}},
            "api": {"port": 8080},
        }
        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            json.dump(existing_user_config, f, ensure_ascii=False, indent=2)

        mgr = GlobalConfigManager(config_dir=temp_config_dir)
        mgr.save_global_settings({"tray": {"minimize_to_tray": False}})

        with open(temp_config_dir / "user_config.json", encoding="utf-8") as f:
            saved = json.load(f)

        # 实例级字段保留
        assert saved["actions"] == existing_user_config["actions"]
        # 全局字段更新
        assert saved["tray"]["minimize_to_tray"] is False
        # 原有 api 段保留
        assert saved["api"]["port"] == 8080

    def test_reload_config(self, temp_config_dir: Path):
        """reload_config 应重新读取磁盘。"""
        mgr = GlobalConfigManager(config_dir=temp_config_dir)
        assert mgr.api["port"] == 8080

        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            json.dump({"api": {"port": 7070}}, f, ensure_ascii=False, indent=2)

        mgr.reload_config()
        assert mgr.api["port"] == 7070

    def test_default_values_when_config_missing(self, tmp_path: Path):
        """default_config.json 不含全局字段时使用 dataclass 默认值。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
            json.dump({"actions": {}}, f)  # 无全局字段

        mgr = GlobalConfigManager(config_dir=config_dir)

        assert mgr.tray.enabled is True  # TrayConfig 默认
        assert mgr.startup.enabled is False  # StartupConfig 默认
        assert mgr.display.cross_screen_drag is True  # DisplayConfig 默认
        assert mgr.llm.model == "gpt-4o-mini"  # LLMConfig 默认
        assert mgr.api == {}  # 无 api 段
        assert mgr.mcp == {
            "openclaw_hooks_url": "http://127.0.0.1:18789/hooks/agent",
            "openclaw_hooks_token": "",
            "openclaw_channel_url": "http://127.0.0.1:18789/pet-bubble-webhook",
            "openclaw_agent_transport": "hooks",
            "openclaw_secret_token": "",
        }


# ---------------------------------------------------------------------------
# InstancesStore
# ---------------------------------------------------------------------------
class TestInstancesStore:
    def test_file_not_exists_returns_empty_list(self, tmp_path: Path):
        """文件不存在时返回空列表，不报错。"""
        store = InstancesStore(config_dir=tmp_path)
        assert store.list_instances() == []
        assert store.get_primary_instance() is None

    def test_corrupted_file_raises_and_preserves_original(self, tmp_path: Path):
        """Corrupt JSON must abort recovery without overwriting user data."""
        store = InstancesStore(config_dir=tmp_path)
        original = "{ not valid json"
        store.instances_path.write_text(original, encoding="utf-8")

        with pytest.raises(InstancesStoreError):
            store.list_instances()
        assert store.instances_path.read_text(encoding="utf-8") == original

    def test_add_and_get_instance(self, tmp_path: Path, sample_package: PetPackage):
        store = InstancesStore(config_dir=tmp_path)
        config = PetInstanceConfig.from_package_defaults(sample_package, pet_id="abc12345")

        store.add_instance(config)

        fetched = store.get_instance("abc12345")
        assert fetched is not None
        assert fetched.pet_id == "abc12345"
        assert fetched.package == "default"

    def test_add_instance_overwrites_existing_pet_id(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        """同 pet_id 再添加应覆盖原实例。"""
        store = InstancesStore(config_dir=tmp_path)
        config = PetInstanceConfig.from_package_defaults(sample_package, pet_id="dup00001")
        config.size = 200
        store.add_instance(config)

        config2 = PetInstanceConfig.from_package_defaults(sample_package, pet_id="dup00001")
        config2.size = 300
        store.add_instance(config2)

        assert len(store.list_instances()) == 1
        assert store.get_instance("dup00001").size == 300

    def test_list_instances(self, tmp_path: Path, sample_package: PetPackage):
        store = InstancesStore(config_dir=tmp_path)
        for pid in ("aaa00001", "aaa00002", "aaa00003"):
            store.add_instance(
                PetInstanceConfig.from_package_defaults(sample_package, pet_id=pid)
            )

        result = store.list_instances()
        assert len(result) == 3
        assert {c.pet_id for c in result} == {"aaa00001", "aaa00002", "aaa00003"}

    def test_get_instance_returns_none_for_missing(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        store = InstancesStore(config_dir=tmp_path)
        store.add_instance(
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="xxx00001")
        )

        assert store.get_instance("nonexistent") is None

    def test_update_instance(self, tmp_path: Path, sample_package: PetPackage):
        store = InstancesStore(config_dir=tmp_path)
        store.add_instance(
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="upd00001")
        )

        updated = store.update_instance("upd00001", {"size": 250, "primary": True})
        assert updated is not None
        assert updated.size == 250
        assert updated.primary is True

        # 持久化验证
        fetched = store.get_instance("upd00001")
        assert fetched.size == 250
        assert fetched.primary is True

    def test_update_instance_returns_none_for_missing(self, tmp_path: Path):
        store = InstancesStore(config_dir=tmp_path)
        assert store.update_instance("nonexist", {"size": 100}) is None

    def test_update_instance_deep_merges_dict_fields(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        """dict 字段做一层浅 merge：仅更新 position.x 保留 y。"""
        store = InstancesStore(config_dir=tmp_path)
        config = PetInstanceConfig.from_package_defaults(sample_package, pet_id="mrg00001")
        config.position = {"x": 100, "y": 100}
        store.add_instance(config)

        updated = store.update_instance("mrg00001", {"position": {"x": 500}})
        assert updated.position == {"x": 500, "y": 100}

    def test_update_instance_rejects_pet_id_change(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        store = InstancesStore(config_dir=tmp_path)
        store.add_instance(
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="pid00001")
        )

        with pytest.raises(InstancesStoreError, match="pet_id"):
            store.update_instance("pid00001", {"pet_id": "hacked123"})
        assert store.get_instance("hacked123") is None
        assert store.get_instance("pid00001") is not None

    def test_remove_instance(self, tmp_path: Path, sample_package: PetPackage):
        store = InstancesStore(config_dir=tmp_path)
        store.add_instance(
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="rem00001")
        )
        store.add_instance(
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="rem00002")
        )

        assert store.remove_instance("rem00001") is True
        assert store.get_instance("rem00001") is None
        assert len(store.list_instances()) == 1

        # 再次移除已不存在的返回 False
        assert store.remove_instance("rem00001") is False

    def test_save_all(self, tmp_path: Path, sample_package: PetPackage):
        store = InstancesStore(config_dir=tmp_path)
        configs = [
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="sav00001"),
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="sav00002"),
        ]
        store.save_all(configs)

        assert len(store.list_instances()) == 2
        # save_all 覆盖现有文件
        store.save_all([configs[0]])
        assert len(store.list_instances()) == 1

    def test_get_primary_instance_returns_primary(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        store = InstancesStore(config_dir=tmp_path)
        c1 = PetInstanceConfig.from_package_defaults(sample_package, pet_id="pri00001")
        c1.primary = False
        c2 = PetInstanceConfig.from_package_defaults(sample_package, pet_id="pri00002")
        c2.primary = True
        store.save_all([c1, c2])

        primary = store.get_primary_instance()
        assert primary is not None
        assert primary.pet_id == "pri00002"

    def test_get_primary_instance_falls_back_to_first(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        """无 primary 标记时返回第一个。"""
        store = InstancesStore(config_dir=tmp_path)
        c1 = PetInstanceConfig.from_package_defaults(sample_package, pet_id="fb000001")
        c2 = PetInstanceConfig.from_package_defaults(sample_package, pet_id="fb000002")
        store.save_all([c1, c2])

        primary = store.get_primary_instance()
        assert primary is not None
        assert primary.pet_id == "fb000001"

    def test_get_primary_instance_empty(self, tmp_path: Path):
        store = InstancesStore(config_dir=tmp_path)
        assert store.get_primary_instance() is None

    def test_round_trip_serialization(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        """往返序列化一致：add 后 get 应得到等价配置。"""
        store = InstancesStore(config_dir=tmp_path)
        original = PetInstanceConfig.from_package_defaults(sample_package, pet_id="rt000001")
        original.primary = True
        original.position = {"x": 250, "y": 300}
        original.screen_index = 1
        original.size = 256

        store.add_instance(original)
        fetched = store.get_instance("rt000001")

        assert fetched.pet_id == original.pet_id
        assert fetched.package == original.package
        assert fetched.primary == original.primary
        assert fetched.position == original.position
        assert fetched.screen_index == original.screen_index
        assert fetched.size == original.size
        assert fetched.actions == original.actions
        assert fetched.rest_reminder == original.rest_reminder
        assert fetched.movement == original.movement
        assert fetched.behavior == original.behavior
        assert fetched.motion_mode == original.motion_mode
        assert fetched.click_detection == original.click_detection

    def test_file_format(self, tmp_path: Path, sample_package: PetPackage):
        """文件结构应为 {"instances": [...]} 且 ensure_ascii=False。"""
        store = InstancesStore(config_dir=tmp_path)
        store.add_instance(
            PetInstanceConfig.from_package_defaults(sample_package, pet_id="fmt00001")
        )

        raw_text = store.instances_path.read_text(encoding="utf-8")
        # 中文应原样保留（ensure_ascii=False）
        data = json.loads(raw_text)
        assert "instances" in data
        assert isinstance(data["instances"], list)
        assert data["instances"][0]["pet_id"] == "fmt00001"

    def test_ensure_initial_instance_returns_none_when_no_package(
        self, tmp_path: Path
    ):
        """无实例且无包时返回 None。"""
        store = InstancesStore(config_dir=tmp_path)
        assert store.ensure_initial_instance(pet_package=None) is None

    def test_ensure_initial_instance_creates_primary(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        """无实例且有包时创建 primary 实例并写入磁盘。"""
        store = InstancesStore(config_dir=tmp_path)

        result = store.ensure_initial_instance(pet_package=sample_package)

        assert result is not None
        assert result.primary is True
        assert result.package == "default"
        assert len(result.pet_id) == 8  # 短 UUID
        # 已写入磁盘
        assert len(store.list_instances()) == 1
        assert store.get_primary_instance().pet_id == result.pet_id

    def test_ensure_initial_instance_no_migration_when_instances_exist(
        self, tmp_path: Path, sample_package: PetPackage
    ):
        """已有实例时不迁移，返回 None。"""
        store = InstancesStore(config_dir=tmp_path)
        existing = PetInstanceConfig.from_package_defaults(sample_package, pet_id="old00001")
        store.add_instance(existing)

        result = store.ensure_initial_instance(pet_package=sample_package)

        assert result is None
        # 不应新增
        assert len(store.list_instances()) == 1
        assert store.get_instance("old00001") is not None

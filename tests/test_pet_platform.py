"""Tests for PetPlatform.

覆盖：
- __init__：正确初始化各组件，加载宠物包
- create_instance：创建实例配置并持久化，返回 pet_id；同包多实例独立
- destroy_instance：销毁后配置和 widget 都移除
- get_instance_config / list_instances / get_primary_instance
- update_instance_config：更新后 store 和 widget 都更新
- persist_instance_position / persist_instance_screen / persist_instance_config
- _migrate_legacy_if_needed：无实例时从 legacy 迁移
- widget_factory 为 None 时：仅管理配置，不创建 widget
- widget_factory 注入时：创建 mock widget 并跟踪
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop_pet.instances_store import InstancesStoreError
from desktop_pet.pet_instance import (
    InstanceConfigError,
    InstanceConflictError,
    InstanceNotFoundError,
    PackageNotFoundError,
    PetInstanceConfig,
)
from desktop_pet.pet_loader import PetAction, PetMeta, PetPackage
from desktop_pet.pet_platform import PetPlatform, PlatformLifecycleError


# ---------------------------------------------------------------------------
# Fixtures
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
def mock_widget_factory():
    """返回 mock widget 工厂；创建的 widget 收集在 factory.created 列表中。"""
    created: list[object] = []

    def factory(
        pet_id: str, config: PetInstanceConfig, package: PetPackage
    ) -> MagicMock:
        widget = MagicMock()
        widget.pet_id = pet_id
        created.append(widget)
        return widget

    factory.created = created  # type: ignore[attr-defined]
    return factory


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """创建空的临时配置目录。"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------
class TestPetPlatformInit:
    def test_init_initializes_components(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """__init__ 应正确初始化各组件。"""
        platform = PetPlatform(config_dir=temp_config_dir)

        assert platform.config_dir == temp_config_dir
        assert platform.global_config is not None
        assert platform.pet_loader is patched_pet_loader
        assert platform.instances_store is not None
        assert isinstance(platform.pet_packages, dict)
        assert isinstance(platform._widgets, dict)
        assert platform._widget_factory is None
        assert platform.api_server is None
        assert platform.system_tray is None
        assert platform.screen_manager is None

    def test_init_loads_pet_packages(
        self, temp_config_dir: Path, patched_pet_loader, sample_package: PetPackage
    ):
        """__init__ 应预加载所有宠物包到 pet_packages。"""
        platform = PetPlatform(config_dir=temp_config_dir)

        patched_pet_loader.scan_pets.assert_called_once()
        assert "default" in platform.pet_packages
        assert platform.pet_packages["default"] is sample_package

    def test_init_with_widget_factory(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        """widget_factory 应被存储到 _widget_factory。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        assert platform._widget_factory is mock_widget_factory

    def test_init_handles_scan_failure(self, temp_config_dir: Path):
        """scan_pets 抛异常时不应崩溃，pet_packages 为空。"""
        with patch("desktop_pet.pet_platform.PetLoader") as MockLoader:
            instance = MockLoader.return_value
            instance.scan_pets.side_effect = OSError("disk error")

            platform = PetPlatform(config_dir=temp_config_dir)
            assert platform.pet_packages == {}

    def test_init_default_config_dir(self, patched_pet_loader):
        """config_dir 为 None 时应使用 get_config_path() 默认目录。"""
        platform = PetPlatform()
        # 默认目录应存在且为 Path 对象
        assert isinstance(platform.config_dir, Path)


# ---------------------------------------------------------------------------
# create_instance
# ---------------------------------------------------------------------------
class TestCreateInstance:
    def test_create_instance_returns_pet_id(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """create_instance 应返回 8 位 pet_id 并持久化配置。"""
        platform = PetPlatform(config_dir=temp_config_dir)

        pet_id = platform.create_instance("default")

        assert len(pet_id) == 8
        int(pet_id, 16)  # 校验十六进制

        config = platform.get_instance_config(pet_id)
        assert config is not None
        assert config.package == "default"
        assert config.pet_id == pet_id

    def test_create_instance_with_position(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """position 参数应覆盖默认位置。"""
        platform = PetPlatform(config_dir=temp_config_dir)

        pet_id = platform.create_instance("default", position={"x": 300, "y": 400})

        config = platform.get_instance_config(pet_id)
        assert config.position == {"x": 300, "y": 400}

    def test_create_instance_with_explicit_config(
        self, temp_config_dir: Path, patched_pet_loader, sample_package: PetPackage
    ):
        """显式传入 config 时应使用该配置。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        explicit = PetInstanceConfig.from_package_defaults(
            sample_package, pet_id="custom01"
        )
        explicit.size = 256

        pet_id = platform.create_instance("default", config=explicit)

        assert pet_id == "custom01"
        config = platform.get_instance_config(pet_id)
        assert config.size == 256

    def test_create_instance_same_package_multiple(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """同包多实例：pet_id 不同，配置独立。"""
        platform = PetPlatform(config_dir=temp_config_dir)

        pet_id_1 = platform.create_instance("default", position={"x": 10, "y": 10})
        pet_id_2 = platform.create_instance("default", position={"x": 20, "y": 20})

        assert pet_id_1 != pet_id_2

        c1 = platform.get_instance_config(pet_id_1)
        c2 = platform.get_instance_config(pet_id_2)
        assert c1.position == {"x": 10, "y": 10}
        assert c2.position == {"x": 20, "y": 20}

    def test_create_instance_unknown_package_raises(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """未知包名应抛 ValueError。"""
        patched_pet_loader.load_pet.return_value = None

        platform = PetPlatform(config_dir=temp_config_dir)

        with pytest.raises(ValueError, match="not found"):
            platform.create_instance("nonexistent")

    def test_create_instance_no_factory_skips_widget(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """widget_factory 为 None 时仅管理配置，不创建 widget。"""
        platform = PetPlatform(config_dir=temp_config_dir)

        pet_id = platform.create_instance("default")

        assert platform.get_pet_widget(pet_id) is None
        assert platform.list_pet_widgets() == {}

    def test_create_instance_with_factory_creates_widget(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        """widget_factory 注入时应创建并跟踪 widget。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )

        pet_id = platform.create_instance("default")

        widget = platform.get_pet_widget(pet_id)
        assert widget is not None
        assert len(mock_widget_factory.created) == 1
        # 工厂应收到正确的 pet_id 和 config
        assert mock_widget_factory.created[0].pet_id == pet_id

    def test_create_instance_lazy_loads_package(
        self, temp_config_dir: Path, sample_package: PetPackage
    ):
        """包未在 scan_pets 返回时应通过 load_pet 懒加载并缓存。"""
        with patch("desktop_pet.pet_platform.PetLoader") as MockLoader:
            instance = MockLoader.return_value
            # scan_pets 返回空，load_pet 返回 sample_package
            instance.scan_pets.return_value = []
            instance.load_pet.return_value = sample_package

            platform = PetPlatform(config_dir=temp_config_dir)
            assert platform.pet_packages == {}

            pet_id = platform.create_instance("default")

            assert pet_id
            # 包应被缓存
            assert "default" in platform.pet_packages
            instance.load_pet.assert_called_with("default")

    def test_create_instance_with_empty_pet_id_generates_one(
        self, temp_config_dir: Path, patched_pet_loader, sample_package: PetPackage
    ):
        """config.pet_id 为空时应自动生成。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        config = PetInstanceConfig.from_package_defaults(sample_package, pet_id="")
        # from_package_defaults 可能不为空字符串生成 id，直接构造空 id 的 config
        config.pet_id = ""

        pet_id = platform.create_instance("default", config=config)

        assert len(pet_id) == 8
        int(pet_id, 16)


# ---------------------------------------------------------------------------
# destroy_instance
# ---------------------------------------------------------------------------
class TestDestroyInstance:
    def test_destroy_instance_removes_config_and_widget(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        """销毁后配置和 widget 都应移除，widget.close() 应被调用。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")

        widget = platform.get_pet_widget(pet_id)
        assert widget is not None

        result = platform.destroy_instance(pet_id)

        assert result is True
        assert platform.get_instance_config(pet_id) is None
        assert platform.get_pet_widget(pet_id) is None
        widget.close.assert_called_once()

    def test_destroy_instance_unknown_returns_false(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """销毁不存在的实例返回 False。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        assert platform.destroy_instance("nonexistent") is False

    def test_destroy_instance_calls_deleteLater_if_no_close(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """widget 无 close() 方法时应尝试 deleteLater()。"""
        platform = PetPlatform(
            config_dir=temp_config_dir,
            widget_factory=lambda pid, cfg, pkg: MagicMock(spec=["deleteLater"]),
        )
        pet_id = platform.create_instance("default")
        widget = platform.get_pet_widget(pet_id)
        assert widget is not None

        platform.destroy_instance(pet_id)

        widget.deleteLater.assert_called_once()

    def test_destroy_instance_removes_widget_even_if_config_missing(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        """即使 store 中配置已被外部删除，也应清理 widget 跟踪。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")

        # 外部删除配置
        platform.instances_store.remove_instance(pet_id)

        # destroy 应清理 widget，但返回 False（配置已不存在）
        result = platform.destroy_instance(pet_id)
        assert result is False
        assert platform.get_pet_widget(pet_id) is None


# ---------------------------------------------------------------------------
# 查询方法
# ---------------------------------------------------------------------------
class TestQueryMethods:
    def test_get_instance_config(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        platform = PetPlatform(config_dir=temp_config_dir)
        pet_id = platform.create_instance("default")

        config = platform.get_instance_config(pet_id)
        assert config is not None
        assert config.pet_id == pet_id

        assert platform.get_instance_config("nonexistent") is None

    def test_list_instances(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        platform = PetPlatform(config_dir=temp_config_dir)
        id1 = platform.create_instance("default")
        id2 = platform.create_instance("default")

        instances = platform.list_instances()
        assert len(instances) == 2
        assert {c.pet_id for c in instances} == {id1, id2}

    def test_get_primary_instance(
        self, temp_config_dir: Path, patched_pet_loader, sample_package: PetPackage
    ):
        """应返回 primary=True 的实例。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        # 创建 primary 实例
        config = PetInstanceConfig.from_package_defaults(
            sample_package, pet_id="pri000001"
        )
        config.primary = True
        platform.instances_store.add_instance(config)
        # 创建非 primary 实例
        platform.create_instance("default")

        primary = platform.get_primary_instance()
        assert primary is not None
        assert primary.pet_id == "pri000001"
        assert primary.primary is True

    def test_get_primary_instance_empty(self, temp_config_dir: Path, patched_pet_loader):
        """无实例时返回 None。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        assert platform.get_primary_instance() is None

    def test_get_pet_widget(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")

        assert platform.get_pet_widget(pet_id) is not None
        assert platform.get_pet_widget("nonexistent") is None

    def test_list_pet_widgets_returns_shallow_copy(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        """list_pet_widgets 返回浅拷贝，修改不影响内部状态。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        id1 = platform.create_instance("default")
        id2 = platform.create_instance("default")

        widgets = platform.list_pet_widgets()
        assert set(widgets.keys()) == {id1, id2}

        # 修改返回值不影响内部
        widgets.clear()
        assert len(platform.list_pet_widgets()) == 2


# ---------------------------------------------------------------------------
# update_instance_config
# ---------------------------------------------------------------------------
class TestUpdateInstanceConfig:
    def test_update_instance_config_persists(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """更新应持久化到 store。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        pet_id = platform.create_instance("default")

        updated = platform.update_instance_config(pet_id, {"size": 300})

        assert updated is not None
        assert updated.size == 300
        # 持久化验证
        assert platform.get_instance_config(pet_id).size == 300

    def test_update_instance_config_notifies_widget(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        """更新后应调用 widget.on_config_updated。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")
        widget = platform.get_pet_widget(pet_id)

        updated = platform.update_instance_config(pet_id, {"size": 300})

        widget.on_config_updated.assert_called_once()
        called_with = widget.on_config_updated.call_args[0][0]
        assert called_with.size == 300
        assert called_with.pet_id == pet_id

    def test_update_instance_config_unknown_raises_not_found(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """Unknown instances raise a typed not-found error."""
        platform = PetPlatform(config_dir=temp_config_dir)
        with pytest.raises(InstanceNotFoundError):
            platform.update_instance_config("nonexistent", {"size": 100})

    def test_update_instance_config_without_widget(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """无 widget 时更新应仍持久化。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        pet_id = platform.create_instance("default")

        updated = platform.update_instance_config(pet_id, {"size": 250})

        assert updated is not None
        assert updated.size == 250

    def test_update_instance_config_deep_merges_position(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """position 字段应做浅 merge：仅更新 x 保留 y。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        pet_id = platform.create_instance(
            "default", position={"x": 100, "y": 100}
        )

        updated = platform.update_instance_config(
            pet_id, {"position": {"x": 500}}
        )

        assert updated.position == {"x": 500, "y": 100}


# ---------------------------------------------------------------------------
# 持久化回调
# ---------------------------------------------------------------------------
class TestPersistCallbacks:
    def test_persist_instance_position(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """persist_instance_position 应更新位置到 store。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        pet_id = platform.create_instance("default")

        platform.persist_instance_position(pet_id, 500, 600)

        config = platform.get_instance_config(pet_id)
        assert config.position == {"x": 500, "y": 600}

    def test_persist_instance_screen(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """persist_instance_screen 应更新 screen_index 到 store。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        pet_id = platform.create_instance("default")
        assert platform.get_instance_config(pet_id).screen_index is None

        platform.persist_instance_screen(pet_id, 2)

        config = platform.get_instance_config(pet_id)
        assert config.screen_index == 2

    def test_persist_instance_config(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        """persist_instance_config 应从 widget 读取配置并全量保存。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")
        widget = platform.get_pet_widget(pet_id)

        # 模拟 widget 内配置已变更
        modified = platform.get_instance_config(pet_id)
        modified.size = 350
        widget.get_config.return_value = modified

        platform.persist_instance_config(pet_id)

        fetched = platform.get_instance_config(pet_id)
        assert fetched.size == 350

    def test_persist_instance_config_no_widget(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """无 widget 时应安全跳过，不抛异常。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        pet_id = platform.create_instance("default")

        # 不应抛异常
        platform.persist_instance_config(pet_id)

    def test_persist_instance_config_widget_without_get_config(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """widget 无 get_config() 方法时应安全跳过。"""
        # 使用 spec 限制 mock 只有 close 方法
        platform = PetPlatform(
            config_dir=temp_config_dir,
            widget_factory=lambda pid, cfg, pkg: MagicMock(spec=["close"]),
        )
        pet_id = platform.create_instance("default")

        # 不应抛异常
        platform.persist_instance_config(pet_id)


# ---------------------------------------------------------------------------
# start() / _migrate_legacy_if_needed
# ---------------------------------------------------------------------------
class TestStartAndMigration:
    def test_start_with_existing_instances_creates_widgets(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
        sample_package: PetPackage,
    ):
        """start() 应为已有实例创建 widget。"""
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        # 预先添加一个实例到 store（不通过 create_instance，避免创建 widget）
        config = PetInstanceConfig.from_package_defaults(
            sample_package, pet_id="start001"
        )
        platform.instances_store.add_instance(config)

        assert platform.list_pet_widgets() == {}

        platform.start()

        assert platform.get_pet_widget("start001") is not None
        assert len(mock_widget_factory.created) == 1

    def test_start_no_factory_skips_widgets(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """widget_factory 为 None 时 start() 仅管理配置。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        platform.create_instance("default")

        # 清空 widget 跟踪模拟尚未创建
        platform._widgets.clear()

        platform.start()

        assert platform.list_pet_widgets() == {}

    def test_migrate_legacy_creates_primary(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """无实例时从 legacy current_pet 迁移，创建 primary 实例。"""
        # 写入 user_config.json
        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            json.dump({"app": {"current_pet": "default"}}, f)

        platform = PetPlatform(config_dir=temp_config_dir)
        assert platform.list_instances() == []

        platform.start()

        instances = platform.list_instances()
        assert len(instances) == 1
        assert instances[0].package == "default"
        assert instances[0].primary is True

    def test_migrate_legacy_skipped_when_instances_exist(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """已有实例时不迁移。"""
        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            json.dump({"app": {"current_pet": "default"}}, f)

        platform = PetPlatform(config_dir=temp_config_dir)
        # 预先添加实例
        platform.create_instance("default")

        platform.start()

        # 不应新增
        assert len(platform.list_instances()) == 1

    def test_migrate_legacy_no_user_config(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """无 user_config.json 时不迁移。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        platform.start()
        assert platform.list_instances() == []

    def test_migrate_legacy_no_current_pet(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """user_config.json 无 app.current_pet 时不迁移。"""
        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            json.dump({"app": {}}, f)

        platform = PetPlatform(config_dir=temp_config_dir)
        platform.start()
        assert platform.list_instances() == []

    def test_migrate_legacy_package_not_loaded(
        self, temp_config_dir: Path
    ):
        """legacy 包未加载时不迁移。"""
        with patch("desktop_pet.pet_platform.PetLoader") as MockLoader:
            instance = MockLoader.return_value
            # scan_pets 返回空，不加载任何包
            instance.scan_pets.return_value = []

            with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
                json.dump({"app": {"current_pet": "default"}}, f)

            platform = PetPlatform(config_dir=temp_config_dir)
            platform.start()

            assert platform.list_instances() == []

    def test_migrate_legacy_corrupted_user_config(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """user_config.json 损坏时不迁移，不抛异常。"""
        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            f.write("{ not valid json")

        platform = PetPlatform(config_dir=temp_config_dir)
        platform.start()
        assert platform.list_instances() == []

    def test_start_migrates_then_creates_widget(
        self,
        temp_config_dir: Path,
        patched_pet_loader,
        mock_widget_factory,
    ):
        """start() 应先迁移再为迁移出的实例创建 widget。"""
        with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
            json.dump({"app": {"current_pet": "default"}}, f)

        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )

        platform.start()

        instances = platform.list_instances()
        assert len(instances) == 1
        # 迁移出的实例应有对应的 widget
        assert platform.get_pet_widget(instances[0].pet_id) is not None


# ---------------------------------------------------------------------------
# 后续 Task 注入点
# ---------------------------------------------------------------------------
class TestInjectionPoints:
    def test_api_server_default_none(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """api_server 初始为 None。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        assert platform.api_server is None

    def test_system_tray_default_none(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """system_tray 初始为 None。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        assert platform.system_tray is None

    def test_screen_manager_default_none(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        """screen_manager 初始为 None。"""
        platform = PetPlatform(config_dir=temp_config_dir)
        assert platform.screen_manager is None


class TestPlatformTransactions:
    def test_start_closes_all_candidates_when_restore_fails(
        self, temp_config_dir: Path, patched_pet_loader, sample_package: PetPackage
    ):
        first = PetInstanceConfig.from_package_defaults(sample_package, pet_id="start001")
        second = PetInstanceConfig.from_package_defaults(sample_package, pet_id="start002")
        widgets = []

        def factory(pet_id, config, package):
            if pet_id == "start002":
                raise RuntimeError("widget construction failed")
            widget = MagicMock()
            widgets.append(widget)
            return widget

        platform = PetPlatform(config_dir=temp_config_dir, widget_factory=factory)
        platform.instances_store.save_all([first, second])

        with pytest.raises(RuntimeError, match="construction failed"):
            platform.start()

        assert platform.list_pet_widgets() == {}
        widgets[0].hide.assert_called_once()
        widgets[0].show.assert_not_called()
        widgets[0].close.assert_called_once()

    def test_start_validation_failure_preserves_original_instances_file(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        original = json.dumps(
            {
                "instances": [
                    {
                        "pet_id": "invalid1",
                        "package": "default",
                        "primary": False,
                        "position": {"x": 100, "y": 100},
                        "size": 20,
                    }
                ]
            },
            indent=2,
        )
        path = temp_config_dir / "instances.json"
        path.write_text(original, encoding="utf-8")
        platform = PetPlatform(config_dir=temp_config_dir)

        with pytest.raises(InstanceConfigError, match="size"):
            platform.start()

        assert path.read_text(encoding="utf-8") == original
        assert platform.list_pet_widgets() == {}

    def test_start_aborts_when_persisted_package_is_missing(
        self, temp_config_dir: Path, patched_pet_loader, sample_package: PetPackage
    ):
        config = PetInstanceConfig.from_package_defaults(sample_package, pet_id="missing1")
        config.package = "missing"
        platform = PetPlatform(config_dir=temp_config_dir)
        platform.instances_store.save_all([config])
        platform.pet_packages.clear()
        patched_pet_loader.load_pet.return_value = None

        with pytest.raises(PackageNotFoundError, match="missing"):
            platform.start()
        assert platform.list_pet_widgets() == {}

    def test_shutdown_save_failure_leaves_services_and_widgets_running(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")
        widget = platform.get_pet_widget(pet_id)
        platform.api_server = MagicMock()
        platform.system_tray = MagicMock()
        platform.instances_store.save_all = MagicMock(
            side_effect=InstancesStoreError("disk full")
        )

        with pytest.raises(InstancesStoreError, match="disk full"):
            platform.shutdown()

        platform.api_server.stop_background.assert_not_called()
        platform.system_tray.hide.assert_not_called()
        widget.close.assert_not_called()
        assert platform.get_pet_widget(pet_id) is widget

    def test_shutdown_api_stop_failure_does_not_close_widgets(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")
        widget = platform.get_pet_widget(pet_id)
        platform.api_server = MagicMock()
        platform.api_server.stop_background.return_value = False
        platform.api_server.last_error = RuntimeError("loop stuck")
        platform.system_tray = MagicMock()

        with pytest.raises(PlatformLifecycleError, match="loop stuck"):
            platform.shutdown()

        platform.system_tray.hide.assert_not_called()
        widget.close.assert_not_called()
        assert platform.get_pet_widget(pet_id) is widget

    def test_shutdown_persists_without_deleting_instance(
        self, temp_config_dir: Path, patched_pet_loader, mock_widget_factory
    ):
        platform = PetPlatform(
            config_dir=temp_config_dir, widget_factory=mock_widget_factory
        )
        pet_id = platform.create_instance("default")
        widget = platform.get_pet_widget(pet_id)
        widget.get_config.return_value = platform.get_instance_config(pet_id)
        widget.x.return_value = 321
        widget.y.return_value = 654
        platform.api_server = MagicMock()
        platform.api_server.stop_background.return_value = True
        platform.system_tray = MagicMock()

        platform.shutdown()

        saved = platform.instances_store.get_instance(pet_id)
        assert saved is not None
        assert saved.position == {"x": 321, "y": 654}
        platform.system_tray.hide.assert_called_once()
        widget.close.assert_called_once()
        assert platform.list_pet_widgets() == {}


class TestIndependentAgentBindings:
    def test_enabled_agent_id_must_be_unique(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        platform = PetPlatform(config_dir=temp_config_dir)
        first = platform.create_instance("default")
        second = platform.create_instance("default")
        platform.update_instance_config(first, {
            "agent": {"enabled": True, "agent_id": "healer-cat"}
        })

        with pytest.raises(InstanceConflictError, match="already bound"):
            platform.update_instance_config(second, {
                "agent": {"enabled": True, "agent_id": "healer-cat"}
            })

    def test_disabled_bindings_may_share_agent_id(
        self, temp_config_dir: Path, patched_pet_loader
    ):
        platform = PetPlatform(config_dir=temp_config_dir)
        first = platform.create_instance("default")
        second = platform.create_instance("default")

        platform.update_instance_config(first, {
            "agent": {"enabled": False, "agent_id": "healer-cat"}
        })
        updated = platform.update_instance_config(second, {
            "agent": {"enabled": False, "agent_id": "healer-cat"}
        })

        assert updated.agent["agent_id"] == "healer-cat"

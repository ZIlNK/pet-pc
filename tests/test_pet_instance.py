"""Tests for PetInstanceConfig."""
import json
from pathlib import Path

import pytest

from desktop_pet.pet_instance import (
    InstanceConfigError,
    PetInstanceConfig,
    generate_pet_id,
    _DEFAULT_BEHAVIOR,
    _DEFAULT_CLICK_DETECTION,
    _DEFAULT_MOTION_MODE,
    _DEFAULT_MOVEMENT,
    _DEFAULT_REST_REMINDER,
)
from desktop_pet.pet_loader import PetAction, PetMeta, PetPackage


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
def sample_package(sample_meta: PetMeta, sample_actions: list[PetAction], tmp_path: Path) -> PetPackage:
    """构造测试用 PetPackage。"""
    return PetPackage(
        name="default",
        path=tmp_path,
        meta=sample_meta,
        actions=sample_actions,
        animations_dir=tmp_path / "animations",
        config_dir=tmp_path / "config",
    )


# ---------------------------------------------------------------------------
# from_package_defaults
# ---------------------------------------------------------------------------
def test_from_package_defaults_builds_config(sample_package: PetPackage):
    """from_package_defaults 应正确从 PetPackage 构建配置。"""
    config = PetInstanceConfig.from_package_defaults(sample_package, pet_id="abc12345")

    # 基础字段
    assert config.pet_id == "abc12345"
    assert config.package == "default"
    assert config.primary is False
    assert config.size == 200
    assert config.screen_index is None
    assert config.position == {"x": 100, "y": 100}

    # actions 来自 PetAction 列表
    assert set(config.actions.keys()) == {"sit", "walk"}

    sit = config.actions["sit"]
    assert sit["enabled"] is True
    assert sit["weight"] == 1
    assert sit["type"] == "animation"
    assert sit["description"] == ""
    assert sit["animation_files"] == ["animations/sit/sit.gif"]
    assert sit["config"] == {"min_distance": 30, "max_distance": 100}
    assert sit["zone_actions"] == {"head": "pat"}

    walk = config.actions["walk"]
    assert walk["enabled"] is False
    assert walk["weight"] == 2
    assert walk["type"] == "movement"
    assert walk["animation_files"] == []

    # 其他字段使用合理默认值（参考 default_config.json）
    assert config.rest_reminder == _DEFAULT_REST_REMINDER
    assert config.movement == _DEFAULT_MOVEMENT
    assert config.behavior == _DEFAULT_BEHAVIOR
    assert config.motion_mode == _DEFAULT_MOTION_MODE
    assert config.click_detection == _DEFAULT_CLICK_DETECTION


def test_from_package_defaults_auto_generates_pet_id(sample_package: PetPackage):
    """pet_id 为 None 时应自动生成 8 位短 UUID。"""
    config = PetInstanceConfig.from_package_defaults(sample_package)

    assert config.pet_id
    assert len(config.pet_id) == 8
    # 十六进制字符
    int(config.pet_id, 16)


def test_from_package_defaults_with_empty_actions(tmp_path: Path, sample_meta: PetMeta):
    """actions 为空时配置应正常构建。"""
    pkg = PetPackage(
        name="empty",
        path=tmp_path,
        meta=sample_meta,
        actions=[],
        animations_dir=tmp_path / "animations",
        config_dir=tmp_path / "config",
    )
    config = PetInstanceConfig.from_package_defaults(pkg, pet_id="empty000")

    assert config.actions == {}
    assert config.package == "empty"


# ---------------------------------------------------------------------------
# to_dict / from_dict 往返序列化
# ---------------------------------------------------------------------------
def test_to_dict_from_dict_round_trip(sample_package: PetPackage):
    """to_dict / from_dict 往返序列化应保持一致。"""
    original = PetInstanceConfig.from_package_defaults(sample_package, pet_id="roundtrip1")
    original.primary = True
    original.position = {"x": 250, "y": 300}
    original.screen_index = 1
    original.size = 256

    serialized = original.to_dict()

    # 所有字段都应存在
    assert set(serialized.keys()) == {
        "pet_id", "package", "primary", "position", "screen_index",
        "size", "actions", "rest_reminder", "movement", "behavior",
        "motion_mode", "click_detection",
    }

    restored = PetInstanceConfig.from_dict(serialized)

    assert restored.pet_id == original.pet_id
    assert restored.package == original.package
    assert restored.primary == original.primary
    assert restored.position == original.position
    assert restored.screen_index == original.screen_index
    assert restored.size == original.size
    assert restored.actions == original.actions
    assert restored.rest_reminder == original.rest_reminder
    assert restored.movement == original.movement
    assert restored.behavior == original.behavior
    assert restored.motion_mode == original.motion_mode
    assert restored.click_detection == original.click_detection


def test_to_dict_is_json_serializable(sample_package: PetPackage):
    """to_dict 的结果应可被 json.dumps 序列化。"""
    config = PetInstanceConfig.from_package_defaults(sample_package, pet_id="json0001")
    data = config.to_dict()

    # 不应抛出异常
    text = json.dumps(data, ensure_ascii=False)
    restored = json.loads(text)

    assert restored["pet_id"] == "json0001"
    assert restored["actions"]["sit"]["animation_files"] == ["animations/sit/sit.gif"]


def test_to_dict_does_not_share_mutable_refs(sample_package: PetPackage):
    """to_dict 返回的嵌套结构修改后不应影响原对象。"""
    original = PetInstanceConfig.from_package_defaults(sample_package, pet_id="isolate1")
    serialized = original.to_dict()

    serialized["position"]["x"] = 999
    serialized["actions"]["sit"]["weight"] = 999
    serialized["rest_reminder"]["interval_minutes"] = 1

    assert original.position["x"] == 100
    assert original.actions["sit"]["weight"] == 1
    assert original.rest_reminder["interval_minutes"] == 55


def test_from_dict_does_not_share_mutable_refs(sample_package: PetPackage):
    """from_dict 构建的对象修改后不应影响输入 dict。"""
    data = PetInstanceConfig.from_package_defaults(sample_package, pet_id="iso2").to_dict()

    config = PetInstanceConfig.from_dict(data)

    config.position["x"] = 888
    config.actions["sit"]["weight"] = 888

    assert data["position"]["x"] == 100
    assert data["actions"]["sit"]["weight"] == 1


# ---------------------------------------------------------------------------
# from_dict 默认值兜底
# ---------------------------------------------------------------------------
def test_from_dict_uses_defaults_for_missing_fields():
    """from_dict 缺失字段时应使用默认值填充。"""
    minimal = {"pet_id": "min00001", "package": "default"}

    config = PetInstanceConfig.from_dict(minimal)

    assert config.pet_id == "min00001"
    assert config.package == "default"
    assert config.primary is False
    assert config.position == {"x": 100, "y": 100}
    assert config.screen_index is None
    assert config.size == 200
    assert config.actions == {}
    assert config.rest_reminder == _DEFAULT_REST_REMINDER
    assert config.movement == _DEFAULT_MOVEMENT
    assert config.behavior == _DEFAULT_BEHAVIOR
    assert config.motion_mode == _DEFAULT_MOTION_MODE
    assert config.click_detection == _DEFAULT_CLICK_DETECTION


def test_from_dict_rejects_missing_pet_id():
    """Persisted records must not silently generate a replacement pet_id."""
    with pytest.raises(InstanceConfigError, match="pet_id"):
        PetInstanceConfig.from_dict({"package": "default"})


@pytest.mark.parametrize(
    "data",
    [
        {"pet_id": "pet00001"},
        {"pet_id": "pet00001", "package": "default", "primary": "false"},
        {"pet_id": "pet00001", "package": "default", "size": "200"},
        {"pet_id": "pet00001", "package": "default", "position": []},
        {"pet_id": "pet00001", "package": "default", "actions": []},
    ],
)
def test_from_dict_rejects_invalid_persisted_structure(data):
    with pytest.raises(InstanceConfigError):
        PetInstanceConfig.from_dict(data)

def test_from_dict_preserves_screen_index_zero():
    """screen_index=0 应被正确保留（不与 None 混淆）。"""
    config = PetInstanceConfig.from_dict({"pet_id": "zero0001", "package": "default", "screen_index": 0})

    assert config.screen_index == 0


# ---------------------------------------------------------------------------
# generate_pet_id
# ---------------------------------------------------------------------------
def test_generate_pet_id_returns_unique_ids():
    """generate_pet_id 应生成唯一 ID。"""
    ids = {generate_pet_id() for _ in range(2000)}

    # 8 位十六进制（32 位），2000 个样本冲突概率极低
    assert len(ids) == 2000
    assert all(len(pid) == 8 for pid in ids)


def test_generate_pet_id_is_hex():
    """pet_id 应为 8 位十六进制字符串。"""
    pid = generate_pet_id("default")

    assert len(pid) == 8
    int(pid, 16)  # 校验十六进制


def test_generate_pet_id_static_method_matches_module_function():
    """静态方法形式应与模块级函数行为一致。"""
    a = PetInstanceConfig.generate_pet_id("default")
    b = generate_pet_id("default")

    assert len(a) == 8
    assert len(b) == 8
    int(a, 16)
    int(b, 16)


# ---------------------------------------------------------------------------
# dataclass 默认值
# ---------------------------------------------------------------------------
def test_default_values_when_constructed_directly():
    """直接构造时 dataclass 默认值应正确。"""
    config = PetInstanceConfig(pet_id="direct01", package="default")

    assert config.primary is False
    assert config.position == {"x": 100, "y": 100}
    assert config.screen_index is None
    assert config.size == 200
    assert config.actions == {}
    assert config.rest_reminder == {}
    assert config.movement == {}
    assert config.behavior == {}
    assert config.motion_mode == {}
    assert config.click_detection == {}


def test_default_position_is_independent_per_instance():
    """默认 position 不应在多个实例间共享（default_factory 隔离）。"""
    a = PetInstanceConfig(pet_id="aaaa0001", package="default")
    b = PetInstanceConfig(pet_id="bbbb0002", package="default")

    a.position["x"] = 500

    assert b.position["x"] == 100
    assert a.position is not b.position

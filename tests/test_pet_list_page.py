"""Tests for pet list preview selection and instance creation interaction."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# 在导入 PyQt6 QWidget 之前确保使用 offscreen 平台，避免无显示器环境下失败
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton

from desktop_pet.settings_pages.pet_list_page import (
    PetListPage,
    resolve_pet_preview_path,
)


# ---------------------------------------------------------------------------
# Qt 应用 fixture（单实例）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_pet(tmp_path: Path, preview: str = "preview.png", regular: str = "idle.png"):
    animations_dir = tmp_path / "animations"
    animations_dir.mkdir()
    return SimpleNamespace(
        animations_dir=animations_dir,
        meta=SimpleNamespace(preview=preview, regular_image=regular),
    )


# ---------------------------------------------------------------------------
# 原有测试：resolve_pet_preview_path
# ---------------------------------------------------------------------------
def test_resolve_pet_preview_path_uses_declared_preview_when_it_exists(tmp_path: Path):
    pet = make_pet(tmp_path)
    preview_path = pet.animations_dir / "preview.png"
    preview_path.write_bytes(b"preview")
    (pet.animations_dir / "idle.png").write_bytes(b"idle")

    assert resolve_pet_preview_path(pet) == preview_path


def test_resolve_pet_preview_path_falls_back_to_regular_image(tmp_path: Path):
    pet = make_pet(tmp_path)
    idle_path = pet.animations_dir / "idle.png"
    idle_path.write_bytes(b"idle")

    assert resolve_pet_preview_path(pet) == idle_path


def test_resolve_pet_preview_path_returns_none_when_no_preview_assets_exist(tmp_path: Path):
    pet = make_pet(tmp_path)

    assert resolve_pet_preview_path(pet) is None


# ---------------------------------------------------------------------------
# 新增测试：创建实例按钮交互
# ---------------------------------------------------------------------------
def _make_platform(num_instances: int = 0):
    """构造一个 mock PetPlatform。"""
    platform = MagicMock()
    platform.list_instances.return_value = [object() for _ in range(num_instances)]
    platform.create_instance.return_value = "pet12345"
    platform.pet_packages = {}
    return platform


def _make_config_manager():
    cm = MagicMock()
    cm.get_current_pet_name.return_value = ""
    return cm


def _make_pet_loader(pets=None):
    loader = MagicMock()
    loader.scan_pets.return_value = pets or []
    return loader


def test_create_instance_button_disabled_when_platform_is_none(qapp, tmp_path: Path):
    """platform=None 时按钮应禁用。"""
    pet = make_pet(tmp_path)
    pet.name = "demo"
    pet.meta = SimpleNamespace(
        preview="preview.png",
        regular_image="idle.png",
        name="demo",
        author="tester",
    )
    page = PetListPage(
        config_manager=_make_config_manager(),
        pet_loader=_make_pet_loader(pets=[pet]),
        platform=None,
    )
    # 找到第一张卡片中的「创建实例」按钮
    create_btns = page.findChildren(QPushButton, "")
    create_btns = [b for b in create_btns if b.text() == "创建实例"]
    assert create_btns, "应至少有一个创建实例按钮"
    assert all(not b.isEnabled() for b in create_btns), "platform 为 None 时按钮应禁用"


def test_create_instance_button_enabled_when_platform_provided(qapp, tmp_path: Path):
    """platform 提供时按钮应启用。"""
    # 准备一个宠物包
    pet = make_pet(tmp_path)
    pet.name = "demo"
    pet.meta = SimpleNamespace(
        preview="preview.png",
        regular_image="idle.png",
        name="demo",
        author="tester",
    )

    page = PetListPage(
        config_manager=_make_config_manager(),
        pet_loader=_make_pet_loader(pets=[pet]),
        platform=_make_platform(),
    )
    create_btns = [b for b in page.findChildren(QPushButton, "") if b.text() == "创建实例"]
    assert create_btns, "应至少有一个创建实例按钮"
    assert all(b.isEnabled() for b in create_btns), "platform 提供时按钮应启用"


def test_clicking_create_instance_calls_platform_and_emits_signal(qapp, tmp_path: Path):
    """点击「创建实例」按钮：调用 platform.create_instance 并发出 instance_created 信号。"""
    pet = make_pet(tmp_path)
    pet.name = "demo"
    pet.meta = SimpleNamespace(
        preview="preview.png",
        regular_image="idle.png",
        name="demo",
        author="tester",
    )

    platform = _make_platform(num_instances=1)
    page = PetListPage(
        config_manager=_make_config_manager(),
        pet_loader=_make_pet_loader(pets=[pet]),
        platform=platform,
    )

    received: list[str] = []
    page.instance_created.connect(lambda pid: received.append(pid))

    # 找到创建实例按钮并点击
    create_btn = next(
        b for b in page.findChildren(QPushButton, "") if b.text() == "创建实例"
    )
    create_btn.click()

    platform.create_instance.assert_called_once_with("demo")
    assert received == ["pet12345"], "应发出 instance_created 信号携带 pet_id"


def test_instance_count_label_reflects_running_instances(qapp, tmp_path: Path):
    """宠物库页面顶部应显示已运行实例数。"""
    platform = _make_platform(num_instances=2)
    page = PetListPage(
        config_manager=_make_config_manager(),
        pet_loader=_make_pet_loader(),
        platform=platform,
    )
    assert page.instance_count_label.text() == "已有 2 个实例"

    # 模拟实例被关闭后刷新
    platform.list_instances.return_value = [object()]
    page._refresh_instance_count()
    assert page.instance_count_label.text() == "已有 1 个实例"


def test_no_instance_count_label_when_platform_is_none(qapp, tmp_path: Path):
    """platform=None 时不应显示实例计数。"""
    page = PetListPage(
        config_manager=_make_config_manager(),
        pet_loader=_make_pet_loader(),
        platform=None,
    )
    assert page.instance_count_label.text() == ""

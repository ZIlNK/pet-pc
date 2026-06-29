"""Tests for the multi-screen ScreenManager."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtWidgets import QApplication

from desktop_pet.screen_manager import ScreenInfo, ScreenManager


# === 辅助 ===
def make_qscreen(name: str, x: int, y: int, w: int, h: int, primary: bool = False):
    """构造一个 mock QScreen,提供 geometry() / availableGeometry() / name()"""
    s = MagicMock()
    s.name.return_value = name
    s.geometry.return_value = QRect(x, y, w, h)
    s.availableGeometry.return_value = QRect(x, y, w, h)
    return s


def make_app_with_screens(screens, primary_index: int = 0):
    """构造一个 mock QApplication"""
    app = MagicMock(spec=QApplication)
    app.screens.return_value = screens
    if screens:
        app.primaryScreen.return_value = screens[primary_index]
    else:
        app.primaryScreen.return_value = None
    return app


# === ScreenInfo ===
def test_screen_info_to_dict_contains_all_fields():
    info = ScreenInfo(
        index=0, name="HDMI-1",
        geometry=QRect(0, 0, 1920, 1080),
        available_geometry=QRect(0, 0, 1920, 1040),
        is_primary=True,
    )
    d = info.to_dict()
    assert d["index"] == 0
    assert d["name"] == "HDMI-1"
    assert d["x"] == 0 and d["y"] == 0
    assert d["width"] == 1920 and d["height"] == 1080
    assert d["available"]["height"] == 1040
    assert d["primary"] is True


# === all_screens / primary_screen ===
def test_all_screens_returns_ordered_list():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2], primary_index=0)

    sm = ScreenManager(app)
    screens = sm.all_screens()
    assert len(screens) == 2
    assert screens[0].name == "Primary"
    assert screens[0].is_primary is True
    assert screens[1].name == "Secondary"
    assert screens[1].is_primary is False


def test_primary_screen_returns_marked_one():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2], primary_index=0)

    sm = ScreenManager(app)
    primary = sm.primary_screen()
    assert primary is not None
    assert primary.name == "Primary"
    assert primary.is_primary is True


def test_screen_by_index_returns_correct():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])

    sm = ScreenManager(app)
    assert sm.screen_by_index(0).name == "Primary"
    assert sm.screen_by_index(1).name == "Secondary"
    assert sm.screen_by_index(2) is None
    assert sm.screen_by_index(-1) is None


# === screen_at ===
def test_screen_at_returns_containing_screen():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])

    # 让 screenAt 返回 Primary
    app.screenAt = MagicMock(return_value=s1)
    sm = ScreenManager(app)
    info = sm.screen_at(100, 100)
    assert info is not None
    assert info.name == "Primary"


def test_screen_at_falls_back_to_nearest_when_point_in_gap():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])
    # 点在间隙(返回 None)
    app.screenAt = MagicMock(return_value=None)

    sm = ScreenManager(app)
    # 离 Primary 中心更近
    info = sm.screen_at(1500, 500)
    assert info is not None
    assert info.name == "Primary"


# === virtual_bounds ===
def test_virtual_bounds_encompasses_all_screens():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])

    sm = ScreenManager(app)
    bounds = sm.virtual_bounds()
    assert bounds.x() == 0
    assert bounds.right() == 3839  # 1920 + 1920 - 1
    assert bounds.bottom() == 1079


# === clamp_to_screen ===
def test_clamp_to_screen_keeps_inside():
    s1 = ScreenInfo(0, "P", QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1080), True)
    x, y = ScreenManager(MagicMock()).clamp_to_screen(s1, 100, 100, 200, 159)
    assert x == 100
    assert y == 100


def test_clamp_to_screen_caps_to_bounds():
    s1 = ScreenInfo(0, "P", QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1080), True)
    x, y = ScreenManager(MagicMock()).clamp_to_screen(s1, 9999, 9999, 200, 159)
    assert x == 1720  # 1920 - 200
    assert y == 921   # 1080 - 159


# === cross_screen_destination ===
def test_cross_screen_destination_finds_right_neighbor():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])

    sm = ScreenManager(app)
    primary = sm.screen_by_index(0)
    dest = sm.cross_screen_destination(primary, "right")
    assert dest is not None
    assert dest.name == "Secondary"


def test_cross_screen_destination_finds_left_neighbor():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])

    sm = ScreenManager(app)
    secondary = sm.screen_by_index(1)
    dest = sm.cross_screen_destination(secondary, "left")
    assert dest is not None
    assert dest.name == "Primary"


def test_cross_screen_destination_returns_none_when_no_neighbor():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    app = make_app_with_screens([s1])

    sm = ScreenManager(app)
    primary = sm.screen_by_index(0)
    assert sm.cross_screen_destination(primary, "right") is None
    assert sm.cross_screen_destination(primary, "left") is None


def test_cross_screen_destination_no_vertical_overlap_excluded():
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Far", 1920, 2000, 1920, 1080)  # y 不重叠
    app = make_app_with_screens([s1, s2])

    sm = ScreenManager(app)
    primary = sm.screen_by_index(0)
    dest = sm.cross_screen_destination(primary, "right")
    assert dest is None


# === opposite_edge_x ===
def test_opposite_edge_x_right_means_enter_from_left():
    s1 = ScreenInfo(1, "S", QRect(1920, 0, 1920, 1080), QRect(1920, 0, 1920, 1080), False)
    sm = ScreenManager(MagicMock())
    # 从右跨到 s1(从左侧进入)
    x = sm.opposite_edge_x(s1, "right", pet_width=200)
    assert x == 1920  # s1 左侧 x


def test_opposite_edge_x_left_means_enter_from_right():
    s1 = ScreenInfo(1, "S", QRect(1920, 0, 1920, 1080), QRect(1920, 0, 1920, 1080), False)
    sm = ScreenManager(MagicMock())
    # 从左跨到 s1(从右侧进入)
    x = sm.opposite_edge_x(s1, "left", pet_width=200)
    assert x == 3640  # 1920 + 1920 - 200


# === _on_screens_changed 模拟热插拔 ===
def test_hot_plug_migrates_pet_when_current_screen_removed():
    """模拟副屏断连:宠物原本在副屏,断连后被迁到主屏"""
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])

    sm = ScreenManager(app)

    # mock pet:几何中心需要能正常返回坐标,不能是 MagicMock
    pet = MagicMock()
    pet.width.return_value = 200
    pet.height.return_value = 159
    # 用真实 QRect 作为 geometry 返回值
    pet.geometry.return_value.center.return_value = QPoint(2600, 579)
    # 模拟:主屏移除后,只剩主屏
    s1_only = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    app.screens.return_value = [s1_only]
    app.primaryScreen.return_value = s1_only
    # screenAt 在新拓扑中找不到 (宠物中心 2600,579 已不在主屏内)
    app.screenAt = MagicMock(return_value=None)

    sm.set_pet(pet)
    sm._on_screens_changed()

    # 验证 pet.move 被调用
    assert pet.move.called
    args, _ = pet.move.call_args
    new_x, new_y = args
    # x 应该在主屏内(0..1720)
    assert 0 <= new_x <= 1720
    # y 应该接近主屏底部
    assert new_y == 1080 - 159

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
def test_hot_plug_migrates_only_pet_on_removed_screen():
    """A hot-plug event migrates only the instance on the removed screen."""
    s1 = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    s2 = make_qscreen("Secondary", 1920, 0, 1920, 1080)
    app = make_app_with_screens([s1, s2])
    app.screenAt = MagicMock(
        side_effect=lambda point: s1 if point.x() < 1920 else s2
    )
    sm = ScreenManager(app)

    primary_pet = MagicMock()
    primary_pet.width.return_value = 200
    primary_pet.height.return_value = 159
    primary_pet.geometry.return_value.center.return_value = QPoint(500, 579)

    removed_pet = MagicMock()
    removed_pet.width.return_value = 200
    removed_pet.height.return_value = 159
    removed_pet.geometry.return_value.center.return_value = QPoint(2600, 579)

    sm.register_pet("primary-pet", primary_pet)
    sm.register_pet("removed-pet", removed_pet)

    s1_only = make_qscreen("Primary", 0, 0, 1920, 1080, primary=True)
    app.screens.return_value = [s1_only]
    app.primaryScreen.return_value = s1_only
    app.screenAt = MagicMock(
        side_effect=lambda point: s1_only if point.x() < 1920 else None
    )
    changes = []
    sm.current_screen_changed.connect(
        lambda pet_id, index: changes.append((pet_id, index))
    )

    sm._on_screens_changed()

    primary_pet.move.assert_not_called()
    removed_pet.move.assert_called_once()
    new_x, new_y = removed_pet.move.call_args.args
    assert 0 <= new_x <= 1720
    assert new_y == 1080 - 159
    assert ("removed-pet", 0) in changes
    assert not any(pet_id == "primary-pet" for pet_id, _ in changes)


def test_notify_pet_screen_tracks_instances_independently():
    sm = ScreenManager(make_app_with_screens([]))
    changes = []
    sm.current_screen_changed.connect(
        lambda pet_id, index: changes.append((pet_id, index))
    )

    sm.notify_pet_screen("pet-a", 1)
    sm.notify_pet_screen("pet-b", 0)
    sm.notify_pet_screen("pet-a", 1)

    assert changes == [("pet-a", 1), ("pet-b", 0)]

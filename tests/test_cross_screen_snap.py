"""Tests for cross-screen snap-to-bottom and DPI scaling fix.

根因: Windows per-monitor DPI 缩放把跨屏 widget 撑大(300x159 -> 1013x539),
导致用 self.height() 算屏底 Y 时出错(顶部贴到屏中,视觉飘空)。

修复: 引入 _natural_pet_size 固定逻辑尺寸,所有贴底算法用自然尺寸而非
self.height();resizeEvent 检测 DPI 缩放并强制还原。
"""
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QRect

from desktop_pet.screen_manager import ScreenInfo
from desktop_pet.states import PetState


def _make_screen_info(index=0, x=0, y=0, w=1920, h=1080, name="Primary", primary=True):
    return ScreenInfo(
        index=index, name=name,
        geometry=QRect(x, y, w, h),
        available_geometry=QRect(x, y, w, h),
        is_primary=primary,
    )


def _make_pet(*, x=1500, y=500, width=200, height=159,
              current_screen=None, primary_screen=None):
    pet = MagicMock()
    pet.x.return_value = x
    pet.y.return_value = y
    pet.width.return_value = width
    pet.height.return_value = height
    pet.geometry.return_value = QRect(x, y, width, height)
    pet._natural_pet_size = (width, height)
    pet._in_size_reset = False

    sm = MagicMock()
    sm.screen_for_widget.return_value = current_screen
    sm.primary_screen.return_value = primary_screen
    sm.virtual_bounds.return_value = QRect(0, 0, 3840, 1080)
    pet.screen_manager = sm

    pet.state = PetState.IDLE
    pet.regular_pixmap = MagicMock()
    pet.flying_pixmap = MagicMock()
    pet.inertia_timer = MagicMock()
    pet.gravity_timer = MagicMock()
    pet.animation_timer = MagicMock()
    pet.inertia_velocity_x = 0.0
    pet.inertia_velocity_y = 0.0
    pet.current_fall_speed = 0.0
    pet.start_gravity_fall = MagicMock()
    pet.snap_to_edge = MagicMock()
    pet.start_random_movement_timer = MagicMock()
    pet.switch_to_static = MagicMock()
    pet.motion_controller = MagicMock()
    pet.motion_controller.get_mode.return_value = "random"

    from desktop_pet.pet import DesktopPet
    pet._safe_current_screen_info = lambda: DesktopPet._safe_current_screen_info(pet)
    pet._snap_to_current_bottom = lambda: DesktopPet._snap_to_current_bottom(pet)
    pet.apply_inertia = lambda: DesktopPet.apply_inertia(pet)
    pet.apply_gravity = lambda: DesktopPet.apply_gravity(pet)
    pet._current_screen_info = lambda: DesktopPet._current_screen_info(pet)
    pet._post_release_safety_check = lambda: DesktopPet._post_release_safety_check(pet)
    return pet


class TestSafeCurrentScreenInfo:
    def test_returns_current_screen_when_present(self):
        a = _make_screen_info(index=0)
        b = _make_screen_info(index=1, x=1920, name="Secondary", primary=False)
        pet = _make_pet(current_screen=a, primary_screen=b)
        assert pet._safe_current_screen_info() is a

    def test_falls_back_to_primary_when_current_is_none(self):
        primary = _make_screen_info(index=0)
        pet = _make_pet(current_screen=None, primary_screen=primary)
        result = pet._safe_current_screen_info()
        assert result is primary
        assert result.is_primary is True


class TestSnapToCurrentBottom:
    def test_snaps_to_primary_bottom_when_current_unknown(self):
        primary = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=500, current_screen=None, primary_screen=primary)
        pet._snap_to_current_bottom()
        args, _ = pet.move.call_args
        assert args[1] == 921

    def test_clamps_x_within_current_screen(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=5000, y=500, current_screen=a, primary_screen=a)
        pet._snap_to_current_bottom()
        args, _ = pet.move.call_args
        new_x, new_y = args
        assert 0 <= new_x <= 1920 - 200
        assert new_y == 1080 - 159

    def test_does_nothing_when_no_screen_available(self):
        pet = _make_pet(current_screen=None, primary_screen=None)
        pet._snap_to_current_bottom()
        pet.move.assert_not_called()

    def test_uses_natural_size_not_dpi_scaled(self):
        """DPI 缩放后 widget 变大,但贴底仍用自然尺寸算 Y。"""
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        # 模拟 widget 被 DPI 撑大到 1013x539,但自然尺寸仍是 200x159
        pet = _make_pet(x=1500, y=500, width=1013, height=539,
                        current_screen=a, primary_screen=a)
        pet._natural_pet_size = (200, 159)  # 自然尺寸不变
        pet._snap_to_current_bottom()
        args, _ = pet.move.call_args
        # Y 应按自然高度 159 算: 1080 - 159 = 921,而非 1080 - 539 = 541
        assert args[1] == 921


class TestApplyInertiaSnapsToBottom:
    def test_low_velocity_in_upper_half_triggers_gravity_fall(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=300, current_screen=a, primary_screen=a)
        pet.inertia_velocity_x = 0.1
        pet.inertia_velocity_y = 0.1
        pet.apply_inertia()
        pet.inertia_timer.stop.assert_called()
        pet.start_gravity_fall.assert_called()

    def test_low_velocity_in_lower_half_snaps_directly(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=800, current_screen=a, primary_screen=a)
        pet.inertia_velocity_x = 0.1
        pet.inertia_velocity_y = 0.1
        pet.apply_inertia()
        pet.inertia_timer.stop.assert_called()
        pet.start_gravity_fall.assert_not_called()
        assert pet.move.called
        last_args = pet.move.call_args[0]
        assert last_args[1] == 1080 - 159

    def test_does_not_freeze_when_screen_for_widget_returns_none(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=5000, y=500, current_screen=None, primary_screen=a)
        pet.inertia_velocity_x = 0.1
        pet.inertia_velocity_y = 0.1
        pet.apply_inertia()
        pet.inertia_timer.stop.assert_called()
        assert pet.start_gravity_fall.called or pet.move.called

    def test_no_call_to_old_snap_to_edge_in_end_branch(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=800, current_screen=a, primary_screen=a)
        pet.inertia_velocity_x = 0.1
        pet.inertia_velocity_y = 0.1
        pet.apply_inertia()
        pet.snap_to_edge.assert_not_called()


class TestApplyGravityFallback:
    def test_falls_back_to_primary_when_current_unknown(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=500, current_screen=None, primary_screen=a)
        pet.current_fall_speed = 5.0
        pet.apply_gravity()
        assert pet.move.called
        args, _ = pet.move.call_args
        assert args[1] == 500 + 5


class TestPostReleaseSafetyCheck:
    def test_snaps_to_bottom_when_pet_is_floating(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=500, current_screen=a, primary_screen=a)
        pet.is_dragging = False
        pet._post_release_safety_check()
        assert pet.move.called
        last_args = pet.move.call_args[0]
        assert last_args[1] == 1080 - 159

    def test_no_op_when_already_at_bottom(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=921, current_screen=a, primary_screen=a)
        pet.is_dragging = False
        pet._post_release_safety_check()
        pet.move.assert_not_called()

    def test_no_op_when_motion_mode(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=1500, y=500, current_screen=a, primary_screen=a)
        pet.is_dragging = False
        pet.motion_controller.get_mode.return_value = "motion"
        pet._post_release_safety_check()
        pet.move.assert_not_called()


class TestApplyInertiaNoScreenFallback:
    def test_snaps_to_primary_bottom_when_no_screen(self):
        a = _make_screen_info(index=0, x=0, y=0, w=1920, h=1080)
        pet = _make_pet(x=5000, y=500, current_screen=None, primary_screen=a)
        pet.inertia_velocity_x = 0.1
        pet.inertia_velocity_y = 0.1
        pet.apply_inertia()
        pet.inertia_timer.stop.assert_called()
        assert pet.move.called
        last_args = pet.move.call_args[0]
        assert last_args[1] == 1080 - 159
        assert 0 <= last_args[0] <= 1920 - 200

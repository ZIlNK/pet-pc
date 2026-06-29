"""Tests for motion mode controller behavior."""

from desktop_pet.motion_controller import MotionModeController


class MockPet:
    current_pet_package = None
    state_value = "idle"

    def x(self):
        return 10

    def y(self):
        return 20

    class MockState:
        value = "idle"

    state = MockState()


def test_set_mode_updates_controller_mode_immediately():
    """Controller mode should update even before UI slots react."""
    controller = MotionModeController(MockPet())

    assert controller.set_mode("motion") is True

    assert controller.get_mode() == "motion"


def test_set_mode_rejects_invalid_mode_without_changing_current_mode():
    """Invalid modes should not mutate controller state."""
    controller = MotionModeController(MockPet())

    assert controller.set_mode("motion") is True
    assert controller.set_mode("bad") is False

    assert controller.get_mode() == "motion"


def test_move_to_carries_screen_index_in_signal():
    """move_to(..., screen_index=N) 应当把 screen_index 透传到 signal 负载中。"""
    pet = MockPet()
    controller = MotionModeController(pet)
    controller.set_mode("motion")

    captured = []

    def on_move(x, y, screen):
        captured.append((x, y, screen))

    controller.move_to_requested.connect(on_move)
    assert controller.move_to(100, 200, screen_index=1) is True
    assert captured == [(100, 200, 1)]
    # 不传 screen 时为 None
    assert controller.move_to(50, 60) is True
    assert captured == [(100, 200, 1), (50, 60, None)]


def test_move_to_edge_carries_screen_index_in_signal():
    pet = MockPet()
    controller = MotionModeController(pet)
    controller.set_mode("motion")

    captured = []

    def on_edge(edge, screen):
        captured.append((edge, screen))

    controller.move_to_edge_requested.connect(on_edge)
    assert controller.move_to_edge("right", screen_index=0) is True
    assert captured == [("right", 0)]
    assert controller.move_to_edge("left") is True
    assert captured == [("right", 0), ("left", None)]


def test_play_walk_carries_screen_index_in_signal():
    pet = MockPet()
    controller = MotionModeController(pet)
    controller.set_mode("motion")

    captured = []

    def on_walk(direction, screen):
        captured.append((direction, screen))

    controller.play_walk_requested.connect(on_walk)
    assert controller.play_walk("left", screen_index=2) is True
    assert captured == [("left", 2)]


def test_get_position_includes_screen_field_when_screen_manager_present():
    """当 pet 上有 screen_manager, get_position() 返回的 dict 应含 screen 字段。"""
    pet = MockPet()
    pet.screen_manager = _FakeScreenManager(current_index=2)
    controller = MotionModeController(pet)

    pos = controller.get_position()
    assert pos == {"x": 10, "y": 20, "screen": 2}


def test_get_position_screen_defaults_to_minus_one_without_screen_manager():
    pet = MockPet()
    controller = MotionModeController(pet)

    pos = controller.get_position()
    assert pos == {"x": 10, "y": 20, "screen": -1}


class _FakeScreenManager:
    def __init__(self, current_index: int):
        self._current_index = current_index

    def screen_for_widget(self, _widget):
        if self._current_index < 0:
            return None
        from PyQt6.QtCore import QRect
        return ScreenInfoStub(self._current_index)

    def all_screens(self):
        return []


class ScreenInfoStub:
    def __init__(self, index):
        self.index = index

from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtCore import QRect

from desktop_pet.pet import DesktopPet


def _movement_stub(speed: int):
    timer = MagicMock()
    pet = SimpleNamespace(
        screen_manager=SimpleNamespace(virtual_bounds=lambda: QRect(0, 0, 1920, 1080)),
        height=lambda: 200,
        motion_controller=SimpleNamespace(movement_speed=speed),
        animation_timer=timer,
    )
    return pet, timer


def test_default_movement_speed_preserves_legacy_pace():
    pet, timer = _movement_stub(speed=5)

    DesktopPet.start_smooth_move(pet, 0, 100, 0)

    assert pet.animation_total_steps == 100
    timer.start.assert_called_once_with(20)


def test_movement_speed_scales_from_default_pace():
    pet, _ = _movement_stub(speed=10)

    DesktopPet.start_smooth_move(pet, 0, 100, 0)

    assert pet.animation_total_steps == 50

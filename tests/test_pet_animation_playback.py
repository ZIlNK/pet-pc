"""Regression tests for reliable one-shot animation startup."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtGui import QMovie

from desktop_pet.pet import DesktopPet
from desktop_pet.states import PetState


class _SignalStub:
    def connect(self, callback):
        self.callback = callback


class _MovieStub:
    def __init__(self, pet):
        self._pet = pet
        self.finished = _SignalStub()
        self.frameChanged = _SignalStub()
        self.started_with = None

    def isValid(self):
        return True

    def start(self):
        self.started_with = (self._pet.current_gif, self._pet.state)


def test_animation_publishes_new_movie_before_starting_it():
    pet = SimpleNamespace()
    old_movie = MagicMock()
    old_movie.state.return_value = QMovie.MovieState.Running
    new_movie = _MovieStub(pet)
    pet.state = PetState.IDLE
    pet.movement_timer = MagicMock()
    pet._disconnect_current_gif_signals = MagicMock()
    pet.current_gif = old_movie
    pet._load_pet_animation = MagicMock(return_value=new_movie)
    pet.label = MagicMock()
    pet.current_animation_type = None
    pet.current_action = None
    pet._on_animation_finished = MagicMock()
    pet._check_gif_finished = MagicMock()
    pet.previous_frame = 123
    pet.gif_played_once = True
    action = SimpleNamespace(name="write")

    DesktopPet.play_animation_action(pet, action)

    assert new_movie.started_with == (new_movie, PetState.ANIMATING)
    assert pet.previous_frame == -1
    assert pet.gif_played_once is False
    old_movie.stop.assert_called_once_with()


def test_random_move_ignores_queued_timeout_while_animation_is_running():
    pet = SimpleNamespace(
        state=PetState.ANIMATING,
        motion_controller=SimpleNamespace(get_mode=lambda: "random"),
        current_pet_package=object(),
        behavior_scheduler=MagicMock(),
        effective_actions=[],
    )

    DesktopPet.random_move(pet)

    pet.behavior_scheduler.choose_next_action.assert_not_called()

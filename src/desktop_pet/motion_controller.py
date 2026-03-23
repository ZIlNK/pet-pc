import random
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from .motion_listener import MotionModeListener


class MotionModeController(QObject):
    mode_changed = pyqtSignal(str, str)
    movement_started = pyqtSignal(str)
    movement_finished = pyqtSignal(tuple)
    animation_started = pyqtSignal(str)
    animation_finished = pyqtSignal(str)
    move_to_requested = pyqtSignal(int, int)
    move_by_requested = pyqtSignal(int, int)
    move_to_edge_requested = pyqtSignal(str)
    play_animation_requested = pyqtSignal(str)
    play_walk_requested = pyqtSignal(str)
    stop_animation_requested = pyqtSignal()
    set_mode_requested = pyqtSignal(str)

    def __init__(self, pet):
        super().__init__()
        self._pet = pet
        self._mode = "random"
        self._listeners: list[MotionModeListener] = []
        self._animation_wait = True

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> bool:
        if mode not in ("random", "motion"):
            return False

        if self._mode == mode:
            return True

        self._notify_mode_changed(self._mode, mode)
        self.mode_changed.emit(self._mode, mode)
        self.set_mode_requested.emit(mode)
        return True

    def get_mode(self) -> str:
        return self._mode

    def move_to(self, x: int, y: int) -> bool:
        if self._mode != "motion":
            return False

        self.move_to_requested.emit(x, y)
        return True

    def move_by(self, dx: int, dy: int) -> bool:
        if self._mode != "motion":
            return False

        self.move_by_requested.emit(dx, dy)
        return True

    def move_to_edge(self, edge: str) -> bool:
        if self._mode != "motion":
            return False

        self.move_to_edge_requested.emit(edge)
        return True

    def play_animation(self, name: str) -> bool:
        if self._mode != "motion":
            return False

        action = self._pet.current_pet_package.actions if self._pet.current_pet_package else []
        found_action = None
        for a in action:
            if a.name == name:
                found_action = a
                break

        if not found_action:
            return False

        self._notify_animation_started(name)
        self.animation_started.emit(name)
        self.play_animation_requested.emit(name)
        return True

    def play_walk(self, direction: str) -> bool:
        if self._mode != "motion":
            return False

        if direction not in ("left", "right"):
            return False

        self.play_walk_requested.emit(direction)
        return True

    def stop_animation(self) -> bool:
        if self._mode != "motion":
            return False

        self.stop_animation_requested.emit()
        return True

    def get_position(self) -> dict:
        return {"x": self._pet.x(), "y": self._pet.y()}

    def get_state(self) -> str:
        return self._pet.state.value

    def get_available_animations(self) -> list:
        if not self._pet.current_pet_package:
            return []
        return [a.name for a in self._pet.current_pet_package.actions if a.type == "animation" and a.enabled]

    def add_listener(self, listener: MotionModeListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: MotionModeListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_movement_started(self, direction: str) -> None:
        for listener in self._listeners:
            listener.on_movement_started(direction)

    def _notify_movement_finished(self, position: tuple[int, int]) -> None:
        for listener in self._listeners:
            listener.on_movement_finished(position)

    def _notify_animation_started(self, animation_name: str) -> None:
        for listener in self._listeners:
            listener.on_animation_started(animation_name)

    def _notify_animation_finished(self, animation_name: str) -> None:
        for listener in self._listeners:
            listener.on_animation_finished(animation_name)

    def _notify_mode_changed(self, old_mode: str, new_mode: str) -> None:
        for listener in self._listeners:
            listener.on_mode_changed(old_mode, new_mode)

    def pause_motion(self) -> None:
        if hasattr(self._pet, 'animation_timer') and self._pet.animation_timer.isActive():
            self._pet.animation_timer.stop()
        if self._pet.current_gif and self._pet.current_gif.state() == 1:
            self._pet.current_gif.stop()

    def resume_motion(self) -> None:
        self._pet.state = self._pet.state.MOTION_MODE

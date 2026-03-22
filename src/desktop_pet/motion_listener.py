from abc import ABC, abstractmethod
from typing import Optional


class MotionModeListener(ABC):
    @abstractmethod
    def on_movement_started(self, direction: str) -> None:
        pass

    @abstractmethod
    def on_movement_finished(self, position: tuple[int, int]) -> None:
        pass

    @abstractmethod
    def on_animation_started(self, animation_name: str) -> None:
        pass

    @abstractmethod
    def on_animation_finished(self, animation_name: str) -> None:
        pass

    @abstractmethod
    def on_mode_changed(self, old_mode: str, new_mode: str) -> None:
        pass

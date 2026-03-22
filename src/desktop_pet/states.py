from enum import Enum


class PetState(Enum):
    IDLE = "idle"
    FALLING = "falling"
    DRAGGING = "dragging"
    INERTIA = "inertia"
    MOVING = "moving"
    REST_REMINDER = "rest_reminder"
    MOTION_MODE = "motion_mode"
    ANIMATING = "animating"

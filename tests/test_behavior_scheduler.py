"""Tests for pet behavior scheduling rules."""

from desktop_pet.behavior_scheduler import BehaviorScheduler
from desktop_pet.pet_loader import PetAction


def action(name, action_type="animation", weight=1, enabled=True):
    return PetAction(name=name, type=action_type, weight=weight, enabled=enabled)


def test_quiet_mode_prefers_calm_animation_over_movement():
    """Quiet mode should reduce distracting movement."""
    scheduler = BehaviorScheduler(quiet_mode_enabled=True)

    selected = scheduler.choose_next_action([
        action("walk", "movement", weight=20),
        action("read", "animation", weight=1),
    ])

    assert selected.name == "read"


def test_quiet_mode_returns_none_when_only_movement_is_available():
    """Quiet mode should stay still instead of forcing movement."""
    scheduler = BehaviorScheduler(quiet_mode_enabled=True)

    selected = scheduler.choose_next_action([
        action("walk", "movement", weight=20),
    ])

    assert selected is None


def test_regular_mode_uses_weighted_action_pool():
    """Regular mode should still include movement and animation actions."""
    scheduler = BehaviorScheduler(quiet_mode_enabled=False)

    selected = scheduler.choose_next_action([
        action("walk", "movement", weight=0),
        action("sit", "animation", weight=10),
    ])

    assert selected.name == "sit"


def test_default_click_action_maps_upper_half_to_head_action():
    """A click in the upper half should prefer head feedback."""
    scheduler = BehaviorScheduler()

    assert scheduler.default_click_action(0.5, 0.2, ["head", "body_tap"]) == "head"


def test_default_click_action_maps_lower_half_to_body_action():
    """A click in the lower half should prefer body feedback."""
    scheduler = BehaviorScheduler()

    assert scheduler.default_click_action(0.5, 0.8, ["head", "body_tap"]) == "body_tap"

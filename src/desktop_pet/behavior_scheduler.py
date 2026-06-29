"""Small behavior rules for choosing pet actions."""

import random
from collections.abc import Sequence

from .pet_loader import PetAction


class BehaviorScheduler:
    def __init__(
        self,
        quiet_mode_enabled: bool = False,
        default_head_action: str = "head",
        default_body_action: str = "body_tap",
    ):
        self.quiet_mode_enabled = quiet_mode_enabled
        self.default_head_action = default_head_action
        self.default_body_action = default_body_action

    def choose_next_action(self, actions: Sequence[PetAction]) -> PetAction | None:
        enabled_actions = [action for action in actions if action.enabled]
        if self.quiet_mode_enabled:
            enabled_actions = [
                action for action in enabled_actions
                if action.type == "animation" and action.weight > 0
            ]
        if not enabled_actions:
            return None

        total_weight = sum(max(0, action.weight) for action in enabled_actions)
        if total_weight <= 0:
            return random.choice(enabled_actions)

        target = random.uniform(0, total_weight)
        current_weight = 0
        for action in enabled_actions:
            current_weight += max(0, action.weight)
            if target <= current_weight:
                return action
        return enabled_actions[-1]

    def default_click_action(self, x: float, y: float, available_actions: Sequence[str]) -> str | None:
        preferred = self.default_head_action if y < 0.5 else self.default_body_action
        if preferred in available_actions:
            return preferred

        fallback = self.default_body_action if preferred == self.default_head_action else self.default_head_action
        if fallback in available_actions:
            return fallback
        return None

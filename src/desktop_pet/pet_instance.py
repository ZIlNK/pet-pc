"""Per-instance configuration model and validation helpers."""
from __future__ import annotations

import copy
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from .pet_loader import PetAction, PetPackage

_DEFAULT_REST_REMINDER: dict[str, Any] = {"enabled": True, "interval_minutes": 55, "countdown_seconds": 300, "intensity": "normal"}
_DEFAULT_MOVEMENT: dict[str, Any] = {"random_interval_min_ms": 3000, "random_interval_max_ms": 15000}
_DEFAULT_BEHAVIOR: dict[str, Any] = {"quiet_mode_enabled": False, "default_head_action": "head", "default_body_action": "body_tap"}
_DEFAULT_MOTION_MODE: dict[str, Any] = {"enabled": True, "default_mode": "random", "movement_speed": 5, "animation_wait": True}
_DEFAULT_CLICK_DETECTION: dict[str, Any] = {"enabled": False, "zones": []}

class InstanceConfigError(ValueError):
    pass

class InstanceNotFoundError(LookupError):
    pass

class InstanceConflictError(RuntimeError):
    pass

class PackageNotFoundError(ValueError):
    pass

def generate_pet_id(package: str = "") -> str:
    del package
    return uuid.uuid4().hex[:8]

def _deep_copy_or_default(value: Any, default: Any) -> Any:
    return copy.deepcopy(default if value is None else value)

def _action_to_dict(action: PetAction) -> dict[str, Any]:
    return {"enabled": action.enabled, "weight": action.weight, "type": action.type, "description": "", "config": copy.deepcopy(action.config), "animation_files": list(action.animation_files), "zone_actions": copy.deepcopy(action.zone_actions)}

def build_effective_actions(pet_package: PetPackage, overrides: Mapping[str, Any] | None) -> list[PetAction]:
    """Return per-instance action copies without mutating the shared package."""
    overrides = overrides or {}
    result: list[PetAction] = []
    for base in pet_package.actions:
        action = copy.deepcopy(base)
        raw = overrides.get(base.name)
        if isinstance(raw, Mapping):
            for key in ("enabled", "weight", "type", "config", "animation_files", "zone_actions"):
                if key in raw:
                    setattr(action, key, copy.deepcopy(raw[key]))
        result.append(action)
    return result

@dataclass
class PetInstanceConfig:
    pet_id: str
    package: str
    primary: bool = False
    position: dict = field(default_factory=lambda: {"x": 100, "y": 100})
    screen_index: int | None = None
    size: int = 200
    actions: dict = field(default_factory=dict)
    rest_reminder: dict = field(default_factory=dict)
    movement: dict = field(default_factory=dict)
    behavior: dict = field(default_factory=dict)
    motion_mode: dict = field(default_factory=dict)
    click_detection: dict = field(default_factory=dict)

    @classmethod
    def from_package_defaults(cls, pet_package: PetPackage, pet_id: str | None = None) -> "PetInstanceConfig":
        return cls(pet_id=pet_id or generate_pet_id(pet_package.name), package=pet_package.name, actions={a.name: _action_to_dict(a) for a in pet_package.actions}, rest_reminder=copy.deepcopy(_DEFAULT_REST_REMINDER), movement=copy.deepcopy(_DEFAULT_MOVEMENT), behavior=copy.deepcopy(_DEFAULT_BEHAVIOR), motion_mode=copy.deepcopy(_DEFAULT_MOTION_MODE), click_detection=copy.deepcopy(_DEFAULT_CLICK_DETECTION))

    def clone(self) -> "PetInstanceConfig":
        return PetInstanceConfig.from_dict(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"pet_id": self.pet_id, "package": self.package, "primary": self.primary, "position": copy.deepcopy(self.position), "screen_index": self.screen_index, "size": self.size, "actions": copy.deepcopy(self.actions), "rest_reminder": copy.deepcopy(self.rest_reminder), "movement": copy.deepcopy(self.movement), "behavior": copy.deepcopy(self.behavior), "motion_mode": copy.deepcopy(self.motion_mode), "click_detection": copy.deepcopy(self.click_detection)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PetInstanceConfig":
        """Deserialize one persisted record without silently coercing bad data."""
        if not isinstance(data, dict):
            raise InstanceConfigError("instance record must be an object")
        pet_id = data.get("pet_id")
        package = data.get("package")
        if not isinstance(pet_id, str) or not pet_id.strip():
            raise InstanceConfigError("pet_id must be a non-empty string")
        if not isinstance(package, str) or not package.strip():
            raise InstanceConfigError("package must be a non-empty string")
        primary = data.get("primary", False)
        if type(primary) is not bool:
            raise InstanceConfigError("primary must be a boolean")
        size = data.get("size", 200)
        if type(size) is not int:
            raise InstanceConfigError("size must be an integer")
        screen_index = data.get("screen_index")
        if screen_index is not None and type(screen_index) is not int:
            raise InstanceConfigError("screen_index must be null or an integer")

        mapping_fields = {
            "position": {"x": 100, "y": 100},
            "actions": {},
            "rest_reminder": _DEFAULT_REST_REMINDER,
            "movement": _DEFAULT_MOVEMENT,
            "behavior": _DEFAULT_BEHAVIOR,
            "motion_mode": _DEFAULT_MOTION_MODE,
            "click_detection": _DEFAULT_CLICK_DETECTION,
        }
        values: dict[str, dict[str, Any]] = {}
        for name, default in mapping_fields.items():
            value = data.get(name, default)
            if not isinstance(value, dict):
                raise InstanceConfigError(f"{name} must be an object")
            values[name] = copy.deepcopy(value)

        return cls(
            pet_id=pet_id,
            package=package,
            primary=primary,
            position=values["position"],
            screen_index=screen_index,
            size=size,
            actions=values["actions"],
            rest_reminder=values["rest_reminder"],
            movement=values["movement"],
            behavior=values["behavior"],
            motion_mode=values["motion_mode"],
            click_detection=values["click_detection"],
        )

    @staticmethod
    def generate_pet_id(package: str = "") -> str:
        return generate_pet_id(package)

_TOP_LEVEL_FIELDS = {"package", "primary", "position", "screen_index", "size", "actions", "rest_reminder", "movement", "behavior", "motion_mode", "click_detection"}
_ACTION_FIELDS = {"enabled", "weight", "type", "description", "config", "animation_files", "zone_actions"}

def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InstanceConfigError(f"{name} must be an object")
    return value

def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise InstanceConfigError(f"{name} must be a boolean")
    return value

def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int:
        raise InstanceConfigError(f"{name} must be an integer")
    if not low <= value <= high:
        raise InstanceConfigError(f"{name} must be between {low} and {high}")
    return value

def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise InstanceConfigError(f"{name} must be a finite number")
    return float(value)

def validate_instance_config(config: PetInstanceConfig, pet_package: PetPackage, *, screen_count: int | None = None) -> PetInstanceConfig:
    if not isinstance(config.pet_id, str) or not config.pet_id.strip():
        raise InstanceConfigError("pet_id must be a non-empty string")
    if config.package != pet_package.name:
        raise InstanceConfigError("package does not match the selected package")
    _boolean(config.primary, "primary")
    pos = _mapping(config.position, "position")
    if set(pos) != {"x", "y"}:
        raise InstanceConfigError("position must contain exactly x and y")
    config.position = {"x": _integer(pos["x"], "position.x", -10000, 10000), "y": _integer(pos["y"], "position.y", -10000, 10000)}
    config.size = _integer(config.size, "size", 50, 1000)
    if config.screen_index is not None:
        if type(config.screen_index) is not int or config.screen_index < 0:
            raise InstanceConfigError("screen_index must be null or a non-negative integer")
        if screen_count is not None and config.screen_index >= screen_count:
            raise InstanceConfigError("screen_index is outside the available screen range")

    rr = {**_DEFAULT_REST_REMINDER, **_mapping(config.rest_reminder, "rest_reminder")}
    if set(rr) - set(_DEFAULT_REST_REMINDER): raise InstanceConfigError("unknown rest_reminder fields")
    rr["enabled"] = _boolean(rr["enabled"], "rest_reminder.enabled")
    rr["interval_minutes"] = _integer(rr["interval_minutes"], "rest_reminder.interval_minutes", 1, 180)
    rr["countdown_seconds"] = _integer(rr["countdown_seconds"], "rest_reminder.countdown_seconds", 30, 1800)
    if rr["intensity"] not in {"gentle", "normal", "strong"}: raise InstanceConfigError("invalid rest_reminder.intensity")
    config.rest_reminder = rr

    movement = {**_DEFAULT_MOVEMENT, **_mapping(config.movement, "movement")}
    if set(movement) - set(_DEFAULT_MOVEMENT): raise InstanceConfigError("unknown movement fields")
    movement["random_interval_min_ms"] = _integer(movement["random_interval_min_ms"], "movement.random_interval_min_ms", 1000, 60000)
    movement["random_interval_max_ms"] = _integer(movement["random_interval_max_ms"], "movement.random_interval_max_ms", 1000, 60000)
    if movement["random_interval_min_ms"] > movement["random_interval_max_ms"]: raise InstanceConfigError("movement minimum interval cannot exceed maximum interval")
    config.movement = movement

    behavior = {**_DEFAULT_BEHAVIOR, **_mapping(config.behavior, "behavior")}
    if set(behavior) - set(_DEFAULT_BEHAVIOR): raise InstanceConfigError("unknown behavior fields")
    behavior["quiet_mode_enabled"] = _boolean(behavior["quiet_mode_enabled"], "behavior.quiet_mode_enabled")
    for key in ("default_head_action", "default_body_action"):
        if not isinstance(behavior[key], str) or not behavior[key]: raise InstanceConfigError(f"behavior.{key} must be a non-empty string")
    config.behavior = behavior

    motion = {**_DEFAULT_MOTION_MODE, **_mapping(config.motion_mode, "motion_mode")}
    if set(motion) - set(_DEFAULT_MOTION_MODE): raise InstanceConfigError("unknown motion_mode fields")
    motion["enabled"] = _boolean(motion["enabled"], "motion_mode.enabled")
    motion["animation_wait"] = _boolean(motion["animation_wait"], "motion_mode.animation_wait")
    if motion["default_mode"] not in {"random", "motion"}: raise InstanceConfigError("motion_mode.default_mode must be random or motion")
    motion["movement_speed"] = _integer(motion["movement_speed"], "motion_mode.movement_speed", 1, 20)
    config.motion_mode = motion

    click = {**copy.deepcopy(_DEFAULT_CLICK_DETECTION), **_mapping(config.click_detection, "click_detection")}
    if set(click) - {"enabled", "zones"}: raise InstanceConfigError("unknown click_detection fields")
    click["enabled"] = _boolean(click["enabled"], "click_detection.enabled")
    if not isinstance(click["zones"], list): raise InstanceConfigError("click_detection.zones must be an array")
    zones = []
    for index, raw in enumerate(click["zones"]):
        zone = _mapping(raw, f"click_detection.zones[{index}]")
        required = {"name", "x", "y", "width", "height", "action"}
        if not required.issubset(zone) or set(zone) - required: raise InstanceConfigError(f"click zone {index} has invalid fields")
        if not isinstance(zone["name"], str) or not isinstance(zone["action"], str): raise InstanceConfigError(f"click zone {index} name/action must be strings")
        x, y, width, height = (_number(zone[k], f"click zone {index}.{k}") for k in ("x", "y", "width", "height"))
        if min(x, y, width, height) < 0 or x + width > 1 or y + height > 1: raise InstanceConfigError(f"click zone {index} is outside normalized bounds")
        zones.append({**copy.deepcopy(zone), "x": x, "y": y, "width": width, "height": height})
    click["zones"] = zones
    config.click_detection = click

    actions = _mapping(config.actions, "actions")
    defaults = {a.name: _action_to_dict(a) for a in pet_package.actions}
    unknown_actions = set(actions) - set(defaults)
    if unknown_actions: raise InstanceConfigError(f"unknown actions: {', '.join(sorted(unknown_actions))}")
    normalized = {}
    for name, base in defaults.items():
        raw = _mapping(actions.get(name, {}), f"actions.{name}")
        unknown = set(raw) - _ACTION_FIELDS
        if unknown: raise InstanceConfigError(f"unknown fields for action {name}: {', '.join(sorted(unknown))}")
        merged = {**copy.deepcopy(base), **copy.deepcopy(raw)}
        merged["enabled"] = _boolean(merged["enabled"], f"actions.{name}.enabled")
        merged["weight"] = _integer(merged["weight"], f"actions.{name}.weight", 0, 1000000)
        if not isinstance(merged["type"], str) or not merged["type"]: raise InstanceConfigError(f"actions.{name}.type must be a string")
        if not isinstance(merged["config"], dict): raise InstanceConfigError(f"actions.{name}.config must be an object")
        if not isinstance(merged["animation_files"], list) or not all(isinstance(v, str) for v in merged["animation_files"]): raise InstanceConfigError(f"actions.{name}.animation_files must be strings")
        if not isinstance(merged["zone_actions"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in merged["zone_actions"].items()): raise InstanceConfigError(f"actions.{name}.zone_actions must map strings")
        normalized[name] = merged
    config.actions = normalized
    return config

def apply_instance_patch(current: PetInstanceConfig, updates: Mapping[str, Any], pet_package: PetPackage, *, screen_count: int | None = None) -> PetInstanceConfig:
    if not isinstance(updates, Mapping): raise InstanceConfigError("request body must be an object")
    if "pet_id" in updates: raise InstanceConfigError("pet_id cannot be changed")
    unknown = set(updates) - _TOP_LEVEL_FIELDS
    if unknown: raise InstanceConfigError(f"unknown instance fields: {', '.join(sorted(unknown))}")
    candidate = current.clone()
    for key, value in updates.items():
        if key in {"position", "rest_reminder", "movement", "behavior", "motion_mode", "click_detection"}:
            value = {**copy.deepcopy(getattr(candidate, key)), **copy.deepcopy(_mapping(value, key))}
        elif key == "actions":
            patch = _mapping(value, key)
            value = copy.deepcopy(candidate.actions)
            for action_name, action_patch in patch.items():
                existing = value.get(action_name, {})
                value[action_name] = {**copy.deepcopy(existing), **copy.deepcopy(_mapping(action_patch, f"actions.{action_name}"))}
        setattr(candidate, key, copy.deepcopy(value))
    return validate_instance_config(candidate, pet_package, screen_count=screen_count)

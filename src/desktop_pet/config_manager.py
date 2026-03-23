import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QMovie


@dataclass
class AnimationConfig:
    path: str
    width: int = 200
    height: int = 159


@dataclass
class ActionConfig:
    name: str
    enabled: bool = True
    weight: int = 1
    action_type: str = "animation"
    description: str = ""
    config: dict = field(default_factory=dict)
    animations: list[AnimationConfig] = field(default_factory=list)


@dataclass
class RestReminderConfig:
    enabled: bool = True
    interval_minutes: int = 55
    countdown_seconds: int = 300
    animation: AnimationConfig | None = None


@dataclass
class MovementConfig:
    random_interval_min_ms: int = 3000
    random_interval_max_ms: int = 15000


@dataclass
class PetConfig:
    size: int = 200
    regular_image: str = "images/pet_user_image.png"
    flying_image: str = "images/pet_flying.png"


@dataclass
class AppConfig:
    current_pet: str = "default"


@dataclass
class MotionModeConfig:
    enabled: bool = True
    default_mode: str = "random"
    movement_speed: int = 5
    animation_wait: bool = True


class ConfigManager:
    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = Path(config_dir)
        self.default_config_path = self.config_dir / "default_config.json"
        self.user_config_path = self.config_dir / "user_config.json"

        self._raw_config: dict[str, Any] = {}
        self._actions: dict[str, ActionConfig] = {}
        self._rest_reminder: RestReminderConfig | None = None
        self._movement: MovementConfig | None = None
        self._pet: PetConfig | None = None
        self._app_config: AppConfig | None = None
        self._motion_mode: MotionModeConfig | None = None

        self.load_config()
    
    def load_config(self) -> None:
        default_config = self._load_json(self.default_config_path)
        user_config = self._load_json(self.user_config_path)
        
        self._raw_config = self._deep_merge(default_config, user_config)
        self._parse_config()
    
    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "_comment" in data:
                    del data["_comment"]
                if "_instructions" in data:
                    del data["_instructions"]
                return data
        except (json.JSONDecodeError, IOError) as e:
            print(f"加载配置文件失败 {path}: {e}")
            return {}
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _parse_config(self) -> None:
        self._actions = {}
        actions_data = self._raw_config.get("actions", {})
        for name, data in actions_data.items():
            animations = []
            for anim_data in data.get("animations", []):
                animations.append(AnimationConfig(
                    path=anim_data.get("path", ""),
                    width=anim_data.get("width", 200),
                    height=anim_data.get("height", 159)
                ))
            
            self._actions[name] = ActionConfig(
                name=name,
                enabled=data.get("enabled", True),
                weight=data.get("weight", 1),
                action_type=data.get("type", "animation"),
                description=data.get("description", ""),
                config=data.get("config", {}),
                animations=animations
            )
        
        rest_data = self._raw_config.get("rest_reminder", {})
        anim_data = rest_data.get("animation", {})
        rest_animation = None
        if anim_data:
            rest_animation = AnimationConfig(
                path=anim_data.get("path", ""),
                width=anim_data.get("width", 200),
                height=anim_data.get("height", 159)
            )
        self._rest_reminder = RestReminderConfig(
            enabled=rest_data.get("enabled", True),
            interval_minutes=rest_data.get("interval_minutes", 55),
            countdown_seconds=rest_data.get("countdown_seconds", 300),
            animation=rest_animation
        )
        
        movement_data = self._raw_config.get("movement", {})
        self._movement = MovementConfig(
            random_interval_min_ms=movement_data.get("random_interval_min_ms", 3000),
            random_interval_max_ms=movement_data.get("random_interval_max_ms", 15000)
        )
        
        pet_data = self._raw_config.get("pet", {})
        self._pet = PetConfig(
            size=pet_data.get("size", 200),
            regular_image=pet_data.get("regular_image", "images/pet_user_image.png"),
            flying_image=pet_data.get("flying_image", "images/pet_flying.png")
        )

        app_data = self._raw_config.get("app", {})
        self._app_config = AppConfig(
            current_pet=app_data.get("current_pet", "default")
        )

        motion_data = self._raw_config.get("motion_mode", {})
        self._motion_mode = MotionModeConfig(
            enabled=motion_data.get("enabled", True),
            default_mode=motion_data.get("default_mode", "random"),
            movement_speed=motion_data.get("movement_speed", 5),
            animation_wait=motion_data.get("animation_wait", True)
        )
    
    @property
    def actions(self) -> dict[str, ActionConfig]:
        return self._actions
    
    @property
    def rest_reminder(self) -> RestReminderConfig:
        return self._rest_reminder
    
    @property
    def movement(self) -> MovementConfig:
        return self._movement
    
    @property
    def pet(self) -> PetConfig:
        return self._pet

    @property
    def app_config(self) -> AppConfig:
        return self._app_config

    @property
    def motion_mode(self) -> MotionModeConfig:
        return self._motion_mode

    @property
    def config(self) -> dict[str, Any]:
        return self._raw_config

    def get_current_pet_name(self) -> str:
        return self._app_config.current_pet

    def set_current_pet(self, pet_name: str) -> None:
        self._app_config.current_pet = pet_name
        self._save_app_config()

    def _save_app_config(self) -> None:
        user_config_path = self.user_config_path
        existing_config = {}
        if user_config_path.exists():
            try:
                with open(user_config_path, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        if "app" not in existing_config:
            existing_config["app"] = {}
        existing_config["app"]["current_pet"] = self._app_config.current_pet

        with open(user_config_path, "w", encoding="utf-8") as f:
            json.dump(existing_config, f, ensure_ascii=False, indent=2)
    
    def get_enabled_actions(self) -> list[ActionConfig]:
        return [action for action in self._actions.values() if action.enabled]
    
    def get_weighted_random_action(self) -> ActionConfig | None:
        enabled_actions = self.get_enabled_actions()
        if not enabled_actions:
            return None
        
        total_weight = sum(action.weight for action in enabled_actions)
        if total_weight <= 0:
            return random.choice(enabled_actions)
        
        r = random.uniform(0, total_weight)
        current_weight = 0
        for action in enabled_actions:
            current_weight += action.weight
            if r <= current_weight:
                return action
        
        return enabled_actions[-1]
    
    def reload_config(self) -> None:
        self.load_config()

    def save_user_config(self) -> None:
        """保存用户配置到user_config.json"""
        actions_data = {}
        for name, action in self._actions.items():
            action_dict = {
                "enabled": action.enabled,
                "weight": action.weight,
                "type": action.action_type,
                "description": action.description,
            }

            if action.config:
                action_dict["config"] = action.config

            if action.animations:
                action_dict["animations"] = [
                    {
                        "path": anim.path,
                        "width": anim.width,
                        "height": anim.height
                    }
                    for anim in action.animations
                ]

            actions_data[name] = action_dict

        user_config = {
            "actions": actions_data
        }

        with open(self.user_config_path, "w", encoding="utf-8") as f:
            json.dump(user_config, f, ensure_ascii=False, indent=2)


class ActionManager:
    def __init__(self, config_manager: ConfigManager, assets_path: Path):
        self.config_manager = config_manager
        self.assets_path = assets_path
        self._loaded_movies: dict[str, list[QMovie]] = {}
    
    def load_animation_movies(self, action: ActionConfig) -> list[QMovie]:
        cache_key = action.name
        if cache_key in self._loaded_movies:
            return self._loaded_movies[cache_key]
        
        movies = []
        for anim_config in action.animations:
            full_path = self.assets_path / anim_config.path
            if full_path.exists():
                try:
                    movie = QMovie(str(full_path))
                    movie.setScaledSize(QSize(anim_config.width, anim_config.height))
                    movies.append(movie)
                except Exception as e:
                    print(f"加载动画失败 {full_path}: {e}")
        
        self._loaded_movies[cache_key] = movies
        return movies
    
    def get_random_movie(self, action: ActionConfig) -> QMovie | None:
        movies = self.load_animation_movies(action)
        if not movies:
            return None
        return random.choice(movies)
    
    def load_rest_reminder_movie(self) -> QMovie | None:
        rest_config = self.config_manager.rest_reminder
        if not rest_config.animation:
            return None
        
        full_path = self.assets_path / rest_config.animation.path
        if not full_path.exists():
            return None
        
        try:
            movie = QMovie(str(full_path))
            movie.setScaledSize(QSize(
                rest_config.animation.width,
                rest_config.animation.height
            ))
            return movie
        except Exception as e:
            print(f"加载休息提醒动画失败 {full_path}: {e}")
            return None
    
    def clear_cache(self) -> None:
        self._loaded_movies.clear()

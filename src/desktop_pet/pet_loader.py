import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import get_pets_path


@dataclass
class PetMeta:
    name: str
    author: str
    version: str
    description: str = ""
    preview: str = ""
    regular_image: str = "idle.png"
    flying_image: str = "flying.png"
    rest_animation: str = "hui.webp"


@dataclass
class PetAction:
    name: str
    type: str
    weight: int
    animation_files: list[str] = field(default_factory=list)
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    zone_actions: dict[str, str] = field(default_factory=dict)


@dataclass
class PetPackage:
    name: str
    path: Path
    meta: PetMeta
    actions: list[PetAction]
    animations_dir: Path
    config_dir: Path


class PetLoader:
    def __init__(self, pets_dir: Path | None = None):
        if pets_dir is None:
            pets_dir = get_pets_path()
        self.pets_dir = Path(pets_dir)
        self._current_pet: PetPackage | None = None

    def scan_pets(self) -> list[PetPackage]:
        pets = []
        if not self.pets_dir.exists():
            return pets

        for item in self.pets_dir.iterdir():
            if item.is_dir() and self.validate_pet(item):
                pet_package = self.load_pet(item.name)
                if pet_package:
                    pets.append(pet_package)
        return pets

    def validate_pet(self, pet_path: Path) -> bool:
        meta_path = pet_path / "meta.json"
        if not meta_path.exists():
            return False

        animations_dir = pet_path / "animations"
        if not animations_dir.exists():
            return False

        animation_files = list(animations_dir.glob("*.gif")) + list(animations_dir.glob("*.png")) + list(animations_dir.glob("*.webp")) + list(animations_dir.glob("*.apng"))
        if not animation_files:
            return False

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                if "name" not in meta or "author" not in meta or "version" not in meta:
                    return False
        except (json.JSONDecodeError, IOError):
            return False

        return True

    def load_pet(self, pet_name: str) -> PetPackage | None:
        pet_path = self.pets_dir / pet_name
        if not pet_path.exists() or not pet_path.is_dir():
            return None

        if not self.validate_pet(pet_path):
            return None

        meta = self._load_meta(pet_path)
        if not meta:
            return None

        actions = self._load_actions(pet_path)

        animations_dir = pet_path / "animations"
        config_dir = pet_path / "config"

        return PetPackage(
            name=pet_name,
            path=pet_path,
            meta=meta,
            actions=actions,
            animations_dir=animations_dir,
            config_dir=config_dir
        )

    def _load_meta(self, pet_path: Path) -> PetMeta | None:
        meta_path = pet_path / "meta.json"
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return PetMeta(
                    name=data.get("name", ""),
                    author=data.get("author", ""),
                    version=data.get("version", ""),
                    description=data.get("description", ""),
                    preview=data.get("preview", ""),
                    regular_image=data.get("regular_image", "idle.png"),
                    flying_image=data.get("flying_image", "flying.png"),
                    rest_animation=data.get("rest_animation", "hui.webp")
                )
        except (json.JSONDecodeError, IOError):
            return None

    def _load_actions(self, pet_path: Path) -> list[PetAction]:
        actions = []
        actions_path = pet_path / "config" / "actions.json"

        if not actions_path.exists():
            return actions

        try:
            with open(actions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                actions_data = data.get("actions", [])

                for action_data in actions_data:
                    action = PetAction(
                        name=action_data.get("name", ""),
                        type=action_data.get("type", "animation"),
                        weight=action_data.get("weight", 1),
                        animation_files=action_data.get("animation_files", []),
                        enabled=action_data.get("enabled", True),
                        config=action_data.get("config", {}),
                        zone_actions=action_data.get("zone_actions", {})
                    )
                    actions.append(action)
        except (json.JSONDecodeError, IOError):
            pass

        return actions

    def get_current_pet(self) -> PetPackage | None:
        return self._current_pet

    def set_current_pet(self, pet_package: PetPackage | None) -> None:
        self._current_pet = pet_package

    def get_pet_by_name(self, pet_name: str) -> PetPackage | None:
        return self.load_pet(pet_name)

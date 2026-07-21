"""Tests for one-time migration from the removed standalone config manager."""
import json
from pathlib import Path
from unittest.mock import patch

from desktop_pet.pet_loader import PetAction, PetMeta, PetPackage
from desktop_pet.pet_platform import PetPlatform


def make_package(tmp_path: Path) -> PetPackage:
    package_path = tmp_path / "pets" / "default"
    return PetPackage(
        name="default",
        path=package_path,
        meta=PetMeta(
            name="default",
            author="tester",
            version="1.0",
            description="test",
            regular_image="idle.png",
            flying_image="flying.png",
            rest_animation="rest.webp",
        ),
        actions=[
            PetAction(
                name="sit",
                type="animation",
                weight=1,
                animation_files=["animations/sit.webp"],
                enabled=True,
                config={"base": True},
                zone_actions={},
            )
        ],
        animations_dir=package_path / "animations",
        config_dir=package_path / "config",
    )


def test_legacy_config_migrates_supported_instance_fields_once(tmp_path: Path):
    package = make_package(tmp_path)
    legacy = {
        "app": {"current_pet": "default"},
        "pet": {"size": 260},
        "rest_reminder": {"enabled": False, "interval_minutes": 30},
        "movement": {"random_interval_min_ms": 4000},
        "behavior": {"quiet_mode_enabled": True},
        "motion_mode": {"default_mode": "motion", "movement_speed": 8},
        "click_detection": {
            "enabled": True,
            "zones": [
                {
                    "name": "head", "x": 0.1, "y": 0.1,
                    "width": 0.2, "height": 0.2, "action": "sit"
                }
            ],
        },
        "display": {"last_screen_index": 2},
        "actions": {
            "sit": {
                "enabled": False, "weight": 7, "type": "animation",
                "config": {"legacy": True},
                "animation_files": ["C:/legacy/unsafe.gif"],
            },
            "unknown": {"enabled": True},
        },
    }
    (tmp_path / "user_config.json").write_text(json.dumps(legacy), encoding="utf-8")

    with patch("desktop_pet.pet_platform.PetLoader") as loader_cls:
        loader_cls.return_value.scan_pets.return_value = [package]
        loader_cls.return_value.load_pet.return_value = package
        platform = PetPlatform(config_dir=tmp_path)
        platform.start()

    instances = platform.list_instances()
    assert len(instances) == 1
    config = instances[0]
    assert config.primary is True
    assert config.package == "default"
    assert config.size == 260
    assert config.screen_index == 2
    assert config.rest_reminder["interval_minutes"] == 30
    assert config.movement["random_interval_min_ms"] == 4000
    assert config.behavior["quiet_mode_enabled"] is True
    assert config.motion_mode["default_mode"] == "motion"
    assert config.click_detection["zones"][0]["action"] == "sit"
    assert config.actions["sit"]["enabled"] is False
    assert config.actions["sit"]["weight"] == 7
    assert config.actions["sit"]["config"] == {"legacy": True}
    assert config.actions["sit"]["animation_files"] == ["animations/sit.webp"]
    assert "unknown" not in config.actions

    legacy["pet"]["size"] = 500
    (tmp_path / "user_config.json").write_text(json.dumps(legacy), encoding="utf-8")
    with patch("desktop_pet.pet_platform.PetLoader") as loader_cls:
        loader_cls.return_value.scan_pets.return_value = [package]
        loader_cls.return_value.load_pet.return_value = package
        restarted = PetPlatform(config_dir=tmp_path)
        restarted.start()
    assert restarted.list_instances()[0].size == 260

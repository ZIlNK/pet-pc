"""Tests for ConfigManager."""
import json
import pytest
from pathlib import Path
from desktop_pet.config_manager import ConfigManager, ActionConfig, RestReminderConfig


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with test configs."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    default_config = {
        "app": {"current_pet": "default"},
        "pet": {
            "size": 200,
            "regular_image": "images/pet.png",
            "flying_image": "images/pet_flying.png"
        },
        "rest_reminder": {
            "enabled": True,
            "interval_minutes": 55,
            "countdown_seconds": 300
        },
        "movement": {
            "random_interval_min_ms": 3000,
            "random_interval_max_ms": 15000
        },
        "actions": {
            "sit": {
                "enabled": True,
                "weight": 1,
                "type": "animation",
                "description": "Sit animation"
            }
        }
    }

    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump(default_config, f)

    return config_dir


def test_config_manager_loads_default_config(temp_config_dir: Path):
    """Test that ConfigManager loads default configuration."""
    manager = ConfigManager(config_dir=temp_config_dir)

    assert manager.pet.size == 200
    assert manager.rest_reminder.enabled is True
    assert manager.rest_reminder.interval_minutes == 55
    assert manager.movement.random_interval_min_ms == 3000


def test_config_manager_merges_user_config(temp_config_dir: Path):
    """Test that user config overrides default config."""
    user_config = {
        "pet": {"size": 300},
        "rest_reminder": {"interval_minutes": 30}
    }

    with open(temp_config_dir / "user_config.json", "w", encoding="utf-8") as f:
        json.dump(user_config, f)

    manager = ConfigManager(config_dir=temp_config_dir)

    assert manager.pet.size == 300  # overridden
    assert manager.rest_reminder.interval_minutes == 30  # overridden
    assert manager.movement.random_interval_min_ms == 3000  # from default


def test_config_manager_get_enabled_actions(temp_config_dir: Path):
    """Test getting enabled actions."""
    manager = ConfigManager(config_dir=temp_config_dir)
    enabled = manager.get_enabled_actions()

    assert len(enabled) == 1
    assert enabled[0].name == "sit"


def test_config_manager_set_current_pet(temp_config_dir: Path):
    """Test setting current pet."""
    manager = ConfigManager(config_dir=temp_config_dir)

    manager.set_current_pet("custom_pet")

    assert manager.get_current_pet_name() == "custom_pet"

    # Verify it's saved to user config
    with open(temp_config_dir / "user_config.json", encoding="utf-8") as f:
        saved = json.load(f)

    assert saved["app"]["current_pet"] == "custom_pet"


def test_config_manager_get_weighted_random_action(temp_config_dir: Path):
    """Test weighted random action selection."""
    # Add multiple actions with different weights
    config = {
        "actions": {
            "action1": {"enabled": True, "weight": 1, "type": "animation"},
            "action2": {"enabled": True, "weight": 9, "type": "animation"},
            "disabled": {"enabled": False, "weight": 100, "type": "animation"}
        }
    }

    with open(temp_config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f)

    manager = ConfigManager(config_dir=temp_config_dir)

    # Run multiple times and check that action2 is selected more often
    results = {"action1": 0, "action2": 0}
    for _ in range(100):
        action = manager.get_weighted_random_action()
        if action:
            results[action.name] += 1

    # action2 has 9x weight, should be selected ~90% of the time
    assert results["action2"] > results["action1"] * 5
    assert results.get("disabled", 0) == 0
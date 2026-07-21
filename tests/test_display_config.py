"""Tests for global display configuration."""
import json
from pathlib import Path

import pytest

from desktop_pet.config_manager import DisplayConfig, GlobalConfigManager


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default_config.json").write_text(
        json.dumps({
            "display": {
                "cross_screen_drag": True,
                "cross_screen_random_walk": False,
                "cross_screen_walk_probability": 0.5,
                "remember_last_screen": True,
                "default_screen_index": 1,
                "last_screen_index": 2,
            }
        }),
        encoding="utf-8",
    )
    return config_dir


def test_display_config_defaults_when_section_missing(tmp_path: Path):
    manager = GlobalConfigManager(config_dir=tmp_path)
    assert manager.display == DisplayConfig()


def test_display_config_loaded_from_default(temp_config_dir: Path):
    display = GlobalConfigManager(config_dir=temp_config_dir).display
    assert display.cross_screen_drag is True
    assert display.cross_screen_random_walk is False
    assert display.cross_screen_walk_probability == 0.5
    assert display.remember_last_screen is True
    assert display.default_screen_index == 1
    assert display.last_screen_index == 2


@pytest.mark.parametrize(("value", "expected"), [(5.0, 1.0), (-2.0, 0.0), ("abc", 0.3)])
def test_display_probability_is_normalized(tmp_path: Path, value, expected):
    (tmp_path / "default_config.json").write_text(
        json.dumps({"display": {"cross_screen_walk_probability": value}}),
        encoding="utf-8",
    )
    assert GlobalConfigManager(config_dir=tmp_path).display.cross_screen_walk_probability == expected


def test_display_updates_use_global_settings_store(tmp_path: Path):
    manager = GlobalConfigManager(config_dir=tmp_path)
    manager.save_global_settings({"display": {"last_screen_index": 1}})

    assert manager.display.last_screen_index == 1
    saved = json.loads((tmp_path / "user_config.json").read_text(encoding="utf-8"))
    assert saved["display"]["last_screen_index"] == 1

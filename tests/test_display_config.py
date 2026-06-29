"""Tests for ConfigManager display config (multi-monitor)."""
import json
from pathlib import Path

import pytest

from desktop_pet.config_manager import ConfigManager, DisplayConfig


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default_config = {
        "app": {"current_pet": "default"},
        "display": {
            "cross_screen_drag": True,
            "cross_screen_random_walk": False,
            "cross_screen_walk_probability": 0.5,
            "remember_last_screen": True,
            "default_screen_index": 1,
            "last_screen_index": 2,
        }
    }
    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump(default_config, f)
    return config_dir


def test_display_config_defaults_when_section_missing(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    manager = ConfigManager(config_dir=config_dir)
    d = manager.display
    assert d.cross_screen_drag is True
    assert d.cross_screen_random_walk is True
    assert d.cross_screen_walk_probability == 0.3
    assert d.remember_last_screen is True
    assert d.default_screen_index is None
    assert d.last_screen_index is None


def test_display_config_loaded_from_default(temp_config_dir: Path):
    manager = ConfigManager(config_dir=temp_config_dir)
    d = manager.display
    assert d.cross_screen_drag is True
    assert d.cross_screen_random_walk is False
    assert d.cross_screen_walk_probability == 0.5
    assert d.remember_last_screen is True
    assert d.default_screen_index == 1
    assert d.last_screen_index == 2


def test_display_config_probability_clamped(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump({"display": {"cross_screen_walk_probability": 5.0}}, f)

    manager = ConfigManager(config_dir=config_dir)
    assert manager.display.cross_screen_walk_probability == 1.0


def test_display_config_probability_handles_bad_type(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump({"display": {"cross_screen_walk_probability": "abc"}}, f)

    manager = ConfigManager(config_dir=config_dir)
    assert manager.display.cross_screen_walk_probability == 0.3


def test_set_last_screen_index_persists(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    manager = ConfigManager(config_dir=config_dir)
    manager.set_last_screen_index(1)

    # 验证内存中的值
    assert manager.display.last_screen_index == 1

    # 验证持久化
    with open(config_dir / "user_config.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["display"]["last_screen_index"] == 1


def test_set_last_screen_index_idempotent(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    manager = ConfigManager(config_dir=config_dir)
    manager.set_last_screen_index(2)
    manager.set_last_screen_index(2)  # 重复,不应重复写
    assert manager.display.last_screen_index == 2

"""Tests for pet list preview selection."""

from pathlib import Path
from types import SimpleNamespace

from desktop_pet.settings_pages.pet_list_page import resolve_pet_preview_path


def make_pet(tmp_path: Path, preview: str = "preview.png", regular: str = "idle.png"):
    animations_dir = tmp_path / "animations"
    animations_dir.mkdir()
    return SimpleNamespace(
        animations_dir=animations_dir,
        meta=SimpleNamespace(preview=preview, regular_image=regular),
    )


def test_resolve_pet_preview_path_uses_declared_preview_when_it_exists(tmp_path: Path):
    pet = make_pet(tmp_path)
    preview_path = pet.animations_dir / "preview.png"
    preview_path.write_bytes(b"preview")
    (pet.animations_dir / "idle.png").write_bytes(b"idle")

    assert resolve_pet_preview_path(pet) == preview_path


def test_resolve_pet_preview_path_falls_back_to_regular_image(tmp_path: Path):
    pet = make_pet(tmp_path)
    idle_path = pet.animations_dir / "idle.png"
    idle_path.write_bytes(b"idle")

    assert resolve_pet_preview_path(pet) == idle_path


def test_resolve_pet_preview_path_returns_none_when_no_preview_assets_exist(tmp_path: Path):
    pet = make_pet(tmp_path)

    assert resolve_pet_preview_path(pet) is None

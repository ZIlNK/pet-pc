"""Tests for aspect-ratio-preserving pet animation scaling."""
from pathlib import Path
from types import SimpleNamespace

from desktop_pet.pet import DesktopPet


class _PetSizingStub:
    _animation_canvas_size = DesktopPet._animation_canvas_size
    _scaled_animation_size = DesktopPet._scaled_animation_size


def _make_pet(size: int = 200) -> _PetSizingStub:
    animations_dir = Path(__file__).parents[1] / "pets" / "default" / "animations"
    pet = _PetSizingStub()
    pet.pet_config = SimpleNamespace(size=size, regular_image="fallback.png")
    pet.assets_path = animations_dir
    pet.current_pet_package = SimpleNamespace(
        animations_dir=animations_dir,
        meta=SimpleNamespace(regular_image="idle.png"),
    )
    return pet


def test_animation_canvas_matches_aspect_preserved_regular_image():
    pet = _make_pet()

    canvas = pet._animation_canvas_size()

    assert (canvas.width(), canvas.height()) == (200, 159)


def test_animation_is_fitted_inside_canvas_without_distortion():
    pet = _make_pet()
    animation_path = pet.current_pet_package.animations_dir / "walk_left.webp"

    scaled = pet._scaled_animation_size(animation_path)

    assert (scaled.width(), scaled.height()) == (180, 159)
    assert scaled.width() <= 200
    assert scaled.height() <= 159


def test_matching_animation_uses_full_canvas():
    pet = _make_pet()
    animation_path = pet.current_pet_package.animations_dir / "sit.webp"

    scaled = pet._scaled_animation_size(animation_path)

    assert (scaled.width(), scaled.height()) == (200, 159)
